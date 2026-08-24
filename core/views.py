from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME, authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Q, Count, F, Max, Sum
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.models import User

from .forms import (
    RegisterForm,
    CategoryForm,
    CommentForm,
    ProfileForm,
    ProjectForm,
    ProjectImageForm,
    UserRegistrationForm,
    BookmarkCollectionForm,
    AddBookmarkToCollectionForm,
    ContestForm,
    ContestSubmissionForm,
    ReportForm,

)

from .models import (
    Category,
    Project,
    Profile,
    Like,
    Comment,
    Bookmark,
    BookmarkCollection,
    Follow,
    Notification,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Certificate,
    Badge,
    UserBadge,
    Achievement,
    Leaderboard,
    ProjectView,
    ProfileVisit,
    ActivityEvent,
    Report,
)


def create_notification(*, recipient, notification_type, message, sender=None, project=None):
    if sender is not None and recipient == sender:
        return None
    return Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        message=message,
        project=project,
    )


def record_activity(*, user, event_type, points=0, actor=None, project=None, contest=None, metadata=None):
    return ActivityEvent.objects.create(
        user=user,
        actor=actor,
        event_type=event_type,
        points=points,
        project=project,
        contest=contest,
        metadata=metadata or {},
    )


def revoke_activity(*, user, event_type, actor=None, project=None):
    """Remove one ledger entry for an action that has just been undone.

    Points are never subtracted by hand. The ActivityEvent ledger is the source
    of truth and refresh_leaderboards() recomputes every total from it, so
    deleting the row is what removes the points.

    Exactly one row is deleted - the most recent match - so undoing one action
    cannot take away points earned from a different one.
    """
    event = ActivityEvent.objects.filter(
        user=user,
        actor=actor,
        event_type=event_type,
        project=project,
    ).order_by("-created_at", "-id").first()

    if event is None:
        return False

    event.delete()
    return True


def record_project_published(request, project):
    """Record the one-off reward for a project entering the published state.

    Called from both create_project and edit_project so a project published by
    editing a draft earns exactly what one published at creation does - and,
    because both go through here, never twice.
    """
    record_activity(
        user=request.user,
        actor=request.user,
        project=project,
        event_type="project_published",
        points=10,
    )

    if request.user.projects.filter(status="published").count() == 1:
        award_badge(
            request.user,
            "First Project",
            "Published your first LaunchPad project.",
            10,
        )


def save_project_images(project, image_forms):
    for image_form in image_forms:
        project_image = image_form.save(commit=False)
        project_image.project = project
        project_image.save()


def home(request):
    public_projects = Project.objects.filter(
        status="published", visibility="public",
    ).select_related("owner", "category")
    projects = public_projects.order_by("-created_at")[:6]
    featured_projects = public_projects.filter(featured=True).order_by("-featured_at", "-created_at")[:3]
    trending_projects = public_projects.annotate(like_total=Count("likes")).order_by("-views_count", "-like_total", "-created_at")[:3]
    categories = Category.objects.all().order_by("name")
    contest_highlights = Contest.objects.filter(status__in=["upcoming", "active"]).order_by("registration_deadline")[:3]
    return render(
        request,
        "core/home.html",
        {
            "projects": projects,
            "featured_projects": featured_projects,
            "trending_projects": trending_projects,
            "contest_highlights": contest_highlights,
            "categories": categories,
        },
    )


def project_list(request):
    from django.core.paginator import Paginator

    public_projects = Q(status="published", visibility="public")
    if request.user.is_authenticated:
        projects = Project.objects.filter(public_projects | Q(owner=request.user))
    else:
        projects = Project.objects.filter(public_projects)

    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    technology = request.GET.get("technology", "").strip()
    tag = request.GET.get("tag", "").strip()
    sort = request.GET.get("sort", "latest")

    if query:
        projects = projects.filter(
            Q(title__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(technologies__icontains=query)
            | Q(tags__icontains=query)
            | Q(owner__username__icontains=query)
            | Q(owner__profile__skills__icontains=query)
            | Q(owner__profile__college__icontains=query)
            | Q(category__name__icontains=query)
        )
    if category:
        projects = projects.filter(category__name__iexact=category)
    if technology:
        projects = projects.filter(technologies__icontains=technology)
    if tag:
        projects = projects.filter(tags__icontains=tag)

    ordering = {
        "latest": "-created_at",
        "trending": "-views_count",
        "most_viewed": "-views_count",
        "most_liked": "-like_total",
        "featured": "-featured_at",
    }.get(sort, "-created_at")
    # select_related covers the owner/category shown on every card; prefetching
    # images lets the template read the thumbnail from cache instead of issuing
    # a query per card.
    projects = projects.select_related(
        "owner",
        "category",
    ).prefetch_related(
        "images",
    ).annotate(like_total=Count("likes")).order_by(ordering, "-created_at")
    paginator = Paginator(projects, 12)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/project_list.html",
        {
            "projects": page,
            "page_obj": page,
            "categories": Category.objects.all().order_by("name"),
            "query": query,
            "category": category,
            "technology": technology,
            "tag": tag,
            "sort": sort,
        },
    )


def project_detail(request, pk):
    public_projects = Q(
        status="published",
        visibility="public",
    )

    if request.user.is_authenticated:
        project = get_object_or_404(
            Project,
            Q(pk=pk) & (public_projects | Q(owner=request.user)),
        )
    else:
        project = get_object_or_404(
            Project,
            Q(pk=pk) & public_projects,
        )

    user_has_liked = False
    user_has_bookmarked = False

    if request.user.is_authenticated:
        user_has_liked = Like.objects.filter(
            user=request.user,
            project=project
        ).exists()

        user_has_bookmarked = Bookmark.objects.filter(
            user=request.user,
            project=project
        ).exists()

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key or ""
    visitor = request.user if request.user.is_authenticated else None

    # One view per viewer per project. A signed-in viewer is identified by the
    # account, so their count does not grow with each new session; an anonymous
    # viewer is identified by the session, which is what session_key is for and
    # matches how analytics already defines a unique visitor.
    if visitor is not None:
        _, is_new_view = ProjectView.objects.get_or_create(
            project=project,
            visitor=visitor,
            defaults={"session_key": session_key},
        )
    else:
        _, is_new_view = ProjectView.objects.get_or_create(
            project=project,
            visitor=None,
            session_key=session_key,
        )

    if is_new_view:
        # F() so concurrent readers cannot lose an increment.
        Project.objects.filter(pk=project.pk).update(
            views_count=F("views_count") + 1
        )
        project.views_count += 1

    comments = Comment.objects.filter(
        project=project,
        parent__isnull=True
    ).select_related("user").prefetch_related(
        "replies__user"
    ).order_by("-created_at")

    comment_form = CommentForm()

    return render(
        request,
        "core/project_detail.html",
        {
            "project": project,
            "user_has_liked": user_has_liked,
            "user_has_bookmarked": user_has_bookmarked,
            "comments": comments,
            "comment_form": comment_form,
            "like_count": project.likes.count(),
            "comment_count": project.comments.count(),
            "view_count": project.views_count,
        },
    )


def is_htmx(request):
    """True when htmx issued this request and expects an HTML fragment back."""
    return request.headers.get("HX-Request") == "true"


def render_engagement_card(request, project):
    """The like/bookmark panel, re-rendered with current state."""
    return render(
        request,
        "core/partials/engagement_card.html",
        {
            "project": project,
            "user_has_liked": Like.objects.filter(
                user=request.user, project=project,
            ).exists(),
            "user_has_bookmarked": Bookmark.objects.filter(
                user=request.user, project=project,
            ).exists(),
            "like_count": project.likes.count(),
            "comment_count": project.comments.count(),
            "view_count": project.views_count,
        },
    )


def get_accessible_project(request, pk):
    public_projects = Q(
        status="published",
        visibility="public",
    )

    if request.user.is_authenticated:
        return get_object_or_404(
            Project,
            Q(pk=pk) & (public_projects | Q(owner=request.user)),
        )

    return get_object_or_404(
        Project,
        Q(pk=pk) & public_projects,
    )


def get_accessible_contest(request, pk):
    """Return a contest the requester is allowed to see.

    Mirrors get_accessible_project. Contests have no owner field - they are
    staff-managed, which is why create/edit/manage/review all gate on
    staff_required - so a draft is visible to staff only. Everyone else gets a
    404 rather than a 403, matching how hidden projects behave: the response
    must not confirm that the contest exists.
    """
    if request.user.is_authenticated and request.user.is_staff:
        return get_object_or_404(Contest, pk=pk)

    return get_object_or_404(
        Contest,
        Q(pk=pk) & ~Q(status="draft"),
    )


@login_required
def add_comment(request, pk):
    project = get_accessible_project(request, pk)

    if request.method == "POST":
        form = CommentForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.project = project
            comment.save()
            messages.success(request, "Your comment was posted.")
            create_notification(
                recipient=project.owner,
                sender=request.user,
                project=project,
                notification_type="comment",
                message=f"{request.user.username} commented on {project.title}.",
            )
            record_activity(user=project.owner, actor=request.user, project=project, event_type="comment_received", points=1)

    return redirect("project_detail", pk=project.pk)


@login_required
def add_reply(request, comment_id):
    parent_comment = get_object_or_404(
        Comment,
        pk=comment_id
    )
    get_accessible_project(request, parent_comment.project.pk)

    if request.method == "POST":
        form = CommentForm(request.POST)

        if form.is_valid():
            reply = form.save(commit=False)
            reply.user = request.user
            reply.project = parent_comment.project
            reply.parent = parent_comment
            reply.save()
            messages.success(request, "Your reply was posted.")
            create_notification(
                recipient=parent_comment.user,
                sender=request.user,
                project=parent_comment.project,
                notification_type="comment",
                message=f"{request.user.username} replied to your comment on {parent_comment.project.title}.",
            )

    return redirect(
        "project_detail",
        pk=parent_comment.project.pk
    )


@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    get_accessible_project(request, comment.project.pk)

    # Only the comment author OR project owner can delete
    if (
        request.user != comment.user
        and request.user != comment.project.owner
    ):
        return redirect(
            "project_detail",
            pk=comment.project.pk
        )

    if request.method == "POST":
        project_pk = comment.project.pk

        # Only top-level comments earn points - add_reply records no activity -
        # so only their removal revokes any.
        if comment.parent_id is None:
            revoke_activity(
                user=comment.project.owner,
                actor=comment.user,
                project=comment.project,
                event_type="comment_received",
            )

        comment.delete()
        messages.info(request, "Comment deleted.")

        return redirect(
            "project_detail",
            pk=project_pk
        )

    return redirect(
        "project_detail",
        pk=comment.project.pk
    )


@login_required
def edit_comment(request, pk):
    comment = get_object_or_404(
        Comment,
        pk=pk,
        user=request.user
    )
    get_accessible_project(request, comment.project.pk)

    if request.method == "POST":
        form = CommentForm(
            request.POST,
            instance=comment
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Your comment was updated.")

            return redirect(
                "project_detail",
                pk=comment.project.pk
            )
    else:
        form = CommentForm(instance=comment)

    return render(
        request,
        "core/comment_edit.html",
        {
            "form": form,
            "comment": comment,
        },
    )


@login_required
def toggle_like(request, pk):
    project = get_accessible_project(request, pk)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    like = Like.objects.filter(
        user=request.user,
        project=project
    ).first()

    if like:
        like.delete()
        revoke_activity(
            user=project.owner,
            actor=request.user,
            project=project,
            event_type="like_received",
        )
        if not is_htmx(request):
            messages.info(request, "Like removed.")
    else:
        Like.objects.create(
            user=request.user,
            project=project
        )
        # htmx swaps the panel in place, which is the feedback; a banner as
        # well would just be noise.
        if not is_htmx(request):
            messages.success(request, f"You appreciated '{project.title}'.")
        create_notification(
            recipient=project.owner,
            sender=request.user,
            project=project,
            notification_type="like",
            message=f"{request.user.username} liked your project {project.title}.",
        )
        record_activity(user=project.owner, actor=request.user, project=project, event_type="like_received", points=1)

    if is_htmx(request):
        return render_engagement_card(request, project)

    return redirect(
        "project_detail",
        pk=project.pk
    )

@login_required
def toggle_bookmark(request, pk):
    project = get_accessible_project(request, pk)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    bookmark = Bookmark.objects.filter(
        user=request.user,
        project=project
    ).first()

    if bookmark:
        bookmark.delete()
        if not is_htmx(request):
            messages.info(request, "Removed from your saved work.")
    else:
        Bookmark.objects.create(
            user=request.user,
            project=project
        )
        if not is_htmx(request):
            messages.success(request, f"'{project.title}' saved for later.")

    if is_htmx(request):
        return render_engagement_card(request, project)

    return redirect(
        "project_detail",
        pk=project.pk
    )

@login_required
def my_bookmarks(request):
    bookmarks = Bookmark.objects.filter(
        user=request.user
    ).select_related(
        "project", "project__owner", "project__category",
    ).prefetch_related(
        "project__images",
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "core/my_bookmarks.html",
        {
            "bookmarks": bookmarks,
        },
    )

@login_required
def create_collection(request):

    if request.method == "POST":
        form = BookmarkCollectionForm(request.POST)

        if form.is_valid():
            collection = form.save(commit=False)

            collection.user = request.user

            collection.save()
            messages.success(request, f"Collection '{collection.name}' was created.")

            return redirect("my_bookmarks")

    else:
        form = BookmarkCollectionForm()

    return render(
        request,
        "core/create_collection.html",
        {
            "form": form,
        },
    )

@login_required
def my_collections(request):
    collections = BookmarkCollection.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return render(
        request,
        "core/my_collections.html",
        {
            "collections": collections,
        },
    )

@login_required
def collection_detail(request, pk):
    collection = get_object_or_404(
        BookmarkCollection,
        pk=pk,
        user=request.user
    )

    bookmarks = collection.bookmarks.select_related(
        "project", "project__owner", "project__category",
    ).prefetch_related(
        "project__images",
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "core/collection_detail.html",
        {
            "collection": collection,
            "bookmarks": bookmarks,
        },
    )

@login_required
def add_bookmark_to_collection(request, pk):
    bookmark = get_object_or_404(
        Bookmark,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = AddBookmarkToCollectionForm(
            request.POST,
            instance=bookmark,
            user=request.user
        )

        if form.is_valid():
            form.save()

            # Bookmark.collection is nullable and the form field is optional, so
            # submitting it empty removes the bookmark from every collection.
            # There is no collection page to return to in that case.
            if bookmark.collection is None:
                messages.info(request, "Removed from all collections.")
                return redirect("my_bookmarks")

            messages.success(
                request,
                f"Saved to '{bookmark.collection.name}'.",
            )

            return redirect(
                "collection_detail",
                pk=bookmark.collection.pk
            )

    else:
        form = AddBookmarkToCollectionForm(
            instance=bookmark,
            user=request.user
        )

    return render(
        request,
        "core/add_bookmark_to_collection.html",
        {
            "form": form,
            "bookmark": bookmark,
        },
    )

@login_required
def create_project(request):
    if request.method == "POST":
        form = ProjectForm(
            request.POST,
            request.FILES
        )
        image_forms = [
            ProjectImageForm(files={"image": image})
            for image in request.FILES.getlist("images")
        ]

        if form.is_valid() and all(
            image_form.is_valid() for image_form in image_forms
        ):
            project = form.save(commit=False)

            project.owner = request.user

            project.save()
            save_project_images(project, image_forms)
            messages.success(request, f"'{project.title}' was created.")
            if project.status == "published":
                record_project_published(request, project)

            return redirect(
                "project_detail",
                pk=project.pk
            )
    else:
        form = ProjectForm()
        image_forms = []

    return render(
        request,
        "core/project_form.html",
        {
            "form": form,
            "image_forms": image_forms,
        },
    )


@login_required
def edit_project(request, pk):
    project = get_object_or_404(
        Project,
        pk=pk,
        owner=request.user
    )
    # Captured before the form binds: ProjectForm(instance=project) writes
    # cleaned_data onto the instance during validation, so reading it later
    # would report the new status, not the previous one.
    was_published = project.status == "published"

    if request.method == "POST":
        form = ProjectForm(
            request.POST,
            request.FILES,
            instance=project
        )
        image_forms = [
            ProjectImageForm(files={"image": image})
            for image in request.FILES.getlist("images")
        ]

        if form.is_valid() and all(
            image_form.is_valid() for image_form in image_forms
        ):
            form.save()
            save_project_images(project, image_forms)

            # Only a genuine transition into published earns the reward.
            # published -> published, published -> draft and draft -> draft all
            # record nothing.
            if not was_published and project.status == "published":
                record_project_published(request, project)

            messages.success(request, f"'{project.title}' was updated.")

            return redirect(
                "project_detail",
                pk=project.pk
            )
    else:
        form = ProjectForm(
            instance=project
        )
        image_forms = []

    return render(
        request,
        "core/project_form.html",
        {
            "form": form,
            "edit_mode": True,
            "project": project,
            "image_forms": image_forms,
        },
    )


@login_required
def delete_project(request, pk):
    project = get_object_or_404(
        Project,
        pk=pk,
        owner=request.user
    )

    if request.method == "POST":
        title = project.title
        project.delete()
        messages.success(request, f"'{title}' was deleted.")

        return redirect("project_list")

    return render(
        request,
        "core/project_delete.html",
        {
            "project": project,
        },
    )


@login_required
def edit_profile(request):
    profile, created = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was updated.")

            return redirect("home")
    else:
        form = ProfileForm(
            instance=profile
        )

    return render(
        request,
        "core/profile_form.html",
        {
            "form": form,
        },
    )


def public_profile(request, username):
    user = get_object_or_404(
        User,
        username=username,
    )

    profile, created = Profile.objects.get_or_create(
        user=user,
    )

    if not request.session.session_key:
        request.session.save()
    ProfileVisit.objects.create(
        profile_user=user,
        visitor=request.user if request.user.is_authenticated else None,
        session_key=request.session.session_key or "",
    )
    projects = Project.objects.filter(
        owner=user,
        status="published",
        visibility="public",
    ).select_related(
        "category",
    ).prefetch_related(
        "images",
    ).order_by(
        "-created_at",
    )

    is_following = (
        request.user.is_authenticated
        and request.user != user
        and Follow.objects.filter(
            follower=request.user,
            following=user,
        ).exists()
    )

    return render(
        request,
        "core/public_profile.html",
        {
            "profile_user": user,
            "profile": profile,
            "projects": projects,
            "follower_count": user.followers.count(),
            "following_count": user.following.count(),
            "is_following": is_following,
            "profile_badges": UserBadge.objects.filter(user=user).select_related("badge"),
            "achievements": Achievement.objects.filter(user=user).order_by("-achieved_at"),
        },
    )


@login_required
def toggle_follow(request, username):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    target_user = get_object_or_404(
        User,
        username=username,
    )

    if target_user == request.user:
        return redirect(
            "public_profile",
            username=target_user.username,
        )

    follow = Follow.objects.filter(
        follower=request.user,
        following=target_user,
    ).first()

    if follow:
        follow.delete()
        revoke_activity(
            user=target_user,
            actor=request.user,
            event_type="follow_received",
        )
        if not is_htmx(request):
            messages.info(request, f"You no longer follow {target_user.username}.")
    else:
        Follow.objects.create(
            follower=request.user,
            following=target_user,
        )
        if not is_htmx(request):
            messages.success(request, f"You are now following {target_user.username}.")
        create_notification(
            recipient=target_user,
            sender=request.user,
            notification_type="follow",
            message=f"{request.user.username} started following you.",
        )
        record_activity(user=target_user, actor=request.user, event_type="follow_received", points=2)

    if is_htmx(request):
        return render(
            request,
            "core/partials/follow_button.html",
            {
                "profile_user": target_user,
                "is_following": Follow.objects.filter(
                    follower=request.user,
                    following=target_user,
                ).exists(),
            },
        )

    return redirect(
        "public_profile",
        username=target_user.username,
    )


def followers_list(request, username):
    profile_user = get_object_or_404(User, username=username)
    # user_list.html reads person.profile.display_name and .college for every
    # row, so the profile has to come along or each row costs a query.
    followers = User.objects.filter(
        following__following=profile_user,
    ).select_related("profile").distinct().order_by("username")
    return render(
        request,
        "core/user_list.html",
        {
            "profile_user": profile_user,
            "people": followers,
            "list_title": "Followers",
        },
    )


def following_list(request, username):
    profile_user = get_object_or_404(User, username=username)
    following = User.objects.filter(
        followers__follower=profile_user,
    ).select_related("profile").distinct().order_by("username")
    return render(
        request,
        "core/user_list.html",
        {
            "profile_user": profile_user,
            "people": following,
            "list_title": "Following",
        },
    )


@login_required
def notifications(request):
    items = Notification.objects.filter(
        recipient=request.user,
    ).select_related("sender", "project")[:100]
    return render(
        request,
        "core/notifications.html",
        {"notifications": items},
    )


@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient=request.user,
    )
    if request.method == "POST":
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect("notifications")


@login_required
def mark_all_notifications_read(request):
    if request.method == "POST":
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True)
    return redirect("notifications")


@login_required
def clear_notifications(request):
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user).delete()
        messages.info(request, "Your inbox was cleared.")
    return redirect("notifications")


def register(request):

    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()

            return redirect("login")
    else:
        form = RegisterForm()

    return render(
        request,
        "core/register.html",
        {
            "form": form,
        },
    )


def get_safe_redirect_target(request):
    """Return the requested ?next= target, but only if it is safe.

    @login_required sends unauthenticated visitors to /login/?next=<page>, so
    honouring it is what returns them to where they were going. An unchecked
    value here would be an open redirect, so anything pointing off-site or at
    another scheme is discarded rather than followed.
    """
    target = request.POST.get(REDIRECT_FIELD_NAME) or request.GET.get(REDIRECT_FIELD_NAME) or ""

    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target

    return ""


def login_view(request):
    # Only ever the validated value: an unsafe target is dropped here rather
    # than echoed back into the form, so it cannot survive a failed attempt.
    safe_target = get_safe_redirect_target(request)

    if request.user.is_authenticated:
        return redirect(safe_target or "home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)

            return redirect(safe_target or "dashboard")

        return render(
            request,
            "core/login.html",
            {
                "error": "Invalid username or password.",
                "next": safe_target,
                "username": username or "",
            }
        )

    return render(
        request,
        "core/login.html",
        {
            "next": safe_target,
        }
    )


def logout_view(request):
    # POST only: a GET logout can be triggered by any third-party page with an
    # <img> tag, and by link prefetchers. Django's own LogoutView has been
    # POST-only since 4.1.
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    logout(request)
    messages.info(request, "You have been signed out.")

    return redirect("home")



def contests(request):
    contest_list = Contest.objects.exclude(status="draft").order_by("registration_deadline")
    return render(request, "core/contests.html", {"contests": contest_list})


def contest_detail(request, pk):
    contest = get_accessible_contest(request, pk)
    participant = None
    if request.user.is_authenticated:
        participant = ContestParticipant.objects.filter(contest=contest, user=request.user).first()
    submissions = contest.submissions.select_related("participant__user", "project").order_by("-submitted_at")
    return render(
        request,
        "core/contest_detail.html",
        {"contest": contest, "participant": participant, "submissions": submissions},
    )


@login_required
def contest_register(request, pk):
    contest = get_accessible_contest(request, pk)
    if request.method == "POST":
        now = timezone.now()
        if contest.status not in {"upcoming", "active"} or now > contest.registration_deadline:
            return redirect("contest_detail", pk=contest.pk)
        if contest.max_participants and contest.participants.count() >= contest.max_participants:
            return redirect("contest_detail", pk=contest.pk)
        _, joined = ContestParticipant.objects.get_or_create(
            contest=contest, user=request.user,
        )
        if joined:
            messages.success(request, f"You joined {contest.title}.")
    return redirect("contest_detail", pk=contest.pk)


@login_required
def contest_submit(request, pk):
    contest = get_accessible_contest(request, pk)
    participant = get_object_or_404(ContestParticipant, contest=contest, user=request.user)
    submission = ContestSubmission.objects.filter(participant=participant).first()
    now = timezone.now()
    if now > contest.submission_deadline or contest.status not in {"upcoming", "active"}:
        return redirect("contest_detail", pk=contest.pk)
    if request.method == "POST":
        form = ContestSubmissionForm(request.POST, instance=submission, user=request.user, contest=contest)
        if form.is_valid():
            value = form.save(commit=False)
            value.contest = contest
            value.participant = participant
            value.status = "submitted"
            value.save()
            messages.success(
                request,
                f"Your entry for {contest.title} was saved.",
            )
            return redirect("contest_detail", pk=contest.pk)
    else:
        form = ContestSubmissionForm(instance=submission, user=request.user, contest=contest)
    return render(request, "core/contest_submission_form.html", {"form": form, "contest": contest, "submission": submission})


def staff_required(request):
    return request.user.is_authenticated and request.user.is_staff


@login_required
def manage_contests(request):
    if not staff_required(request):
        return HttpResponseForbidden("Staff access required.")
    contest_list = Contest.objects.all().order_by("-created_at")
    return render(request, "core/manage_contests.html", {"contests": contest_list})


@login_required
def create_contest(request):
    if not staff_required(request):
        return HttpResponseForbidden("Staff access required.")
    if request.method == "POST":
        form = ContestForm(request.POST)
        if form.is_valid():
            contest = form.save()
            return redirect("contest_detail", pk=contest.pk)
    else:
        form = ContestForm()
    return render(request, "core/contest_form.html", {"form": form, "edit_mode": False})


@login_required
def edit_contest(request, pk):
    if not staff_required(request):
        return HttpResponseForbidden("Staff access required.")
    contest = get_object_or_404(Contest, pk=pk)
    if request.method == "POST":
        form = ContestForm(request.POST, instance=contest)
        if form.is_valid():
            form.save()
            return redirect("contest_detail", pk=contest.pk)
    else:
        form = ContestForm(instance=contest)
    return render(request, "core/contest_form.html", {"form": form, "contest": contest, "edit_mode": True})


@login_required
def review_submission(request, pk):
    if not staff_required(request):
        return HttpResponseForbidden("Staff access required.")
    submission = get_object_or_404(ContestSubmission, pk=pk)
    if request.method == "POST":
        submission.status = request.POST.get("status", submission.status)
        score = request.POST.get("score", "").strip()
        submission.score = score or None
        submission.save(update_fields=["status", "score", "updated_at"])
        if submission.status == "winner":
            Certificate.objects.get_or_create(
                submission=submission,
                defaults={"certificate_number": f"LP-{submission.pk:06d}"},
            )
            record_activity(
                user=submission.participant.user,
                actor=request.user,
                project=submission.project,
                contest=submission.contest,
                event_type="contest_winner",
                points=100,
            )
            award_badge(
                submission.participant.user,
                "Contest Winner",
                "Won a LaunchPad innovation contest.",
                100,
            )
            Project.objects.filter(pk=submission.project.pk).update(featured=True, featured_at=timezone.now())
            create_notification(
                recipient=submission.participant.user,
                sender=request.user,
                project=submission.project,
                notification_type="contest_result",
                message=f"Your submission won {submission.contest.title}.",
            )
    return redirect("contest_detail", pk=submission.contest.pk)


def certificate_detail(request, pk):
    certificate = get_object_or_404(Certificate, pk=pk)
    if not request.user.is_authenticated or request.user != certificate.submission.participant.user and not request.user.is_staff:
        return HttpResponseForbidden("Certificate access restricted.")
    return render(request, "core/certificate_detail.html", {"certificate": certificate})


@login_required
def report_project(request, pk):
    project = get_accessible_project(request, pk)

    # A reporter gets one live report per project. "open" and "reviewing" are
    # the unresolved statuses; once moderators resolve or dismiss one, the same
    # user may raise the issue again.
    if Report.objects.filter(
        reporter=request.user,
        project=project,
        status__in=["open", "reviewing"],
    ).exists():
        messages.info(
            request,
            "You have already reported this project. Moderators are looking at it.",
        )
        return redirect("project_detail", pk=project.pk)

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.project = project
            report.reported_user = project.owner
            report.save()
            messages.success(
                request,
                "Thanks - your report has been sent to the moderators.",
            )
            return redirect("project_detail", pk=project.pk)
    else:
        form = ReportForm()
    return render(request, "core/report_form.html", {"form": form, "project": project})



def award_badge(user, badge_name, description="", points=0):
    badge, _ = Badge.objects.get_or_create(
        name=badge_name,
        defaults={"description": description or badge_name, "points": points},
    )
    user_badge, created = UserBadge.objects.get_or_create(user=user, badge=badge)
    if created:
        record_activity(user=user, event_type="badge_awarded", points=badge.points)
        create_notification(
            recipient=user,
            notification_type="badge",
            message=f"You earned the {badge.name} badge.",
        )
    return user_badge


# How long a computed leaderboard is considered fresh. Recomputing on every
# request cost 462 queries for 19 users and grew with the user count.
LEADERBOARD_REFRESH_INTERVAL = timedelta(minutes=10)

LEADERBOARD_PERIODS = [choice[0] for choice in Leaderboard.PERIOD_CHOICES]


def leaderboard_period_starts(today=None):
    """First day counted for each period. 'overall' has no lower bound."""
    today = today or timezone.localdate()
    return {
        "overall": None,
        "weekly": today - timedelta(days=today.weekday()),
        "monthly": today.replace(day=1),
    }


def activity_points_by_user(since=None):
    """Total ActivityEvent points per user, as one grouped query."""
    events = ActivityEvent.objects.all()
    if since is not None:
        events = events.filter(created_at__date__gte=since)

    return {
        row["user"]: row["total"] or 0
        for row in events.values("user").annotate(total=Sum("points"))
    }


def badge_points_by_user():
    """Total badge points per user, as one grouped query."""
    return {
        row["user"]: row["total"] or 0
        for row in UserBadge.objects.values("user").annotate(total=Sum("badge__points"))
    }


def refresh_leaderboards():
    """Recompute every leaderboard period.

    Previously this annotated two multi-valued relations on the same queryset
    (activity_events and badges), which made the SQL joins multiply: a user with
    3 events worth 10 and 2 badges worth 5 scored 90 instead of 40. Summing each
    relation in its own grouped query is both correct and far cheaper - the cost
    is now a fixed handful of queries rather than one per user per period.
    """
    usernames = dict(User.objects.values_list("pk", "username"))
    badge_points = badge_points_by_user()
    now = timezone.now()

    for period, start in leaderboard_period_starts().items():
        event_points = activity_points_by_user(start)

        if period == "overall":
            points_map = {
                user_id: event_points.get(user_id, 0) + badge_points.get(user_id, 0)
                for user_id in usernames
            }
        else:
            points_map = {
                user_id: event_points.get(user_id, 0) for user_id in usernames
            }

        # Highest points first, ties broken alphabetically so ranks are stable.
        ranked = sorted(
            points_map.items(),
            key=lambda item: (-item[1], usernames[item[0]]),
        )

        existing = {
            entry.user_id: entry
            for entry in Leaderboard.objects.filter(
                period=period,
                period_start=start,
                period_end=None,
            )
        }

        to_create = []
        to_update = []

        for rank, (user_id, points) in enumerate(ranked, start=1):
            entry = existing.get(user_id)

            if entry is None:
                to_create.append(
                    Leaderboard(
                        user_id=user_id,
                        period=period,
                        period_start=start,
                        period_end=None,
                        points=points,
                        rank=rank,
                        updated_at=now,
                    )
                )
            elif entry.points != points or entry.rank != rank:
                entry.points = points
                entry.rank = rank
                entry.updated_at = now
                to_update.append(entry)

        if to_create:
            Leaderboard.objects.bulk_create(to_create)
        if to_update:
            Leaderboard.objects.bulk_update(
                to_update,
                ["points", "rank", "updated_at"],
            )

        # Mark the period as freshly computed even when no row changed.
        # leaderboards_are_stale() reads MAX(updated_at); without this touch a
        # settled leaderboard never looks fresh, so every request would pay for
        # a full recomputation forever.
        Leaderboard.objects.filter(
            period=period,
            period_start=start,
            period_end=None,
        ).update(updated_at=now)


def leaderboards_are_stale():
    """True when no leaderboard exists yet, or the newest one has aged out."""
    latest = Leaderboard.objects.aggregate(latest=Max("updated_at"))["latest"]

    return latest is None or timezone.now() - latest > LEADERBOARD_REFRESH_INTERVAL


def leaderboard(request):
    period = request.GET.get("period", "overall")
    if period not in LEADERBOARD_PERIODS:
        period = "overall"

    # Refresh on read only when the data has aged out, so a burst of visitors
    # does not each pay for a full recomputation. The management command
    # `refresh_leaderboards` forces one for scheduled runs.
    if leaderboards_are_stale():
        refresh_leaderboards()

    entries = Leaderboard.objects.filter(
        period=period,
    ).select_related("user", "user__profile").order_by("rank")[:50]

    return render(
        request,
        "core/leaderboard.html",
        {
            "entries": entries,
            "period": period,
            "periods": LEADERBOARD_PERIODS,
        },
    )


@login_required
def dashboard(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    project_count = request.user.projects.count()
    published_count = request.user.projects.filter(status="published").count()
    followers_count = request.user.followers.count()
    following_count = request.user.following.count()
    like_count = Like.objects.filter(project__owner=request.user).count()
    comment_count = Comment.objects.filter(project__owner=request.user).count()
    view_count = ProjectView.objects.filter(project__owner=request.user).count()
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    badges = UserBadge.objects.filter(user=request.user).select_related("badge")
    activities = ActivityEvent.objects.filter(user=request.user).select_related("actor", "project", "contest")[:10]
    completion_fields = [
        profile.display_name,
        profile.bio,
        profile.avatar,
        profile.college,
        profile.education,
        profile.skills,
        profile.portfolio_url,
    ]
    completion = round(sum(bool(value) for value in completion_fields) / len(completion_fields) * 100)
    participations = ContestParticipant.objects.filter(user=request.user).count()
    return render(
        request,
        "core/dashboard.html",
        {
            "profile": profile,
            "project_count": project_count,
            "published_count": published_count,
            "followers_count": followers_count,
            "following_count": following_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "view_count": view_count,
            "unread_count": unread_count,
            "badges": badges,
            "activities": activities,
            "completion": completion,
            "participations": participations,
        },
    )


@login_required
def analytics(request):
    # likes, comments and view_events are all multi-valued relations. Annotating
    # three of them in one queryset makes the SQL joins multiply, so without
    # distinct=True each count is inflated by the row count of the other two
    # (3 likes + 2 comments was reported as 6 and 6). Counting distinct related
    # primary keys gives the true total.
    projects = request.user.projects.select_related("category").annotate(
        likes_total=Count("likes", distinct=True),
        comments_total=Count("comments", distinct=True),
        views_total=Count("view_events", distinct=True),
    ).order_by("-views_total")
    profile_visits = ProfileVisit.objects.filter(profile_user=request.user).count()
    unique_profile_visitors = ProfileVisit.objects.filter(profile_user=request.user).values("visitor", "session_key").distinct().count()
    return render(
        request,
        "core/analytics.html",
        {
            "projects": projects,
            "profile_visits": profile_visits,
            "unique_profile_visitors": unique_profile_visitors,
            "follower_growth": request.user.followers.order_by("-created_at")[:30],
        },
    )


def public_stats(request):
    return {
        "platform_stats": {
            "students": User.objects.count(),
            "projects": Project.objects.filter(status="published", visibility="public").count(),
            "contests": Contest.objects.exclude(status="draft").count(),
            "connections": Follow.objects.count(),
        }
    }
