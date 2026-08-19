from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
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


def save_project_images(project, image_forms):
    for image_form in image_forms:
        project_image = image_form.save(commit=False)
        project_image.project = project
        project_image.save()


def home(request):
    public_projects = Project.objects.filter(status="published", visibility="public")
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
    projects = projects.annotate(like_total=Count("likes")).order_by(ordering, "-created_at")
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
    ProjectView.objects.create(
        project=project,
        visitor=request.user if request.user.is_authenticated else None,
        session_key=request.session.session_key or "",
    )
    Project.objects.filter(pk=project.pk).update(views_count=project.views_count + 1)
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
        comment.delete()

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
    else:
        Like.objects.create(
            user=request.user,
            project=project
        )
        create_notification(
            recipient=project.owner,
            sender=request.user,
            project=project,
            notification_type="like",
            message=f"{request.user.username} liked your project {project.title}.",
        )
        record_activity(user=project.owner, actor=request.user, project=project, event_type="like_received", points=1)

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
    else:
        Bookmark.objects.create(
            user=request.user,
            project=project
        )

    return redirect(
        "project_detail",
        pk=project.pk
    )

@login_required
def my_bookmarks(request):
    bookmarks = Bookmark.objects.filter(
        user=request.user
    ).select_related(
        "project"
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
        "project"
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
            if project.status == "published":
                record_activity(user=request.user, actor=request.user, project=project, event_type="project_published", points=10)
                if request.user.projects.filter(status="published").count() == 1:
                    award_badge(request.user, "First Project", "Published your first LaunchPad project.", 10)

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
        project.delete()

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
    else:
        Follow.objects.create(
            follower=request.user,
            following=target_user,
        )
        create_notification(
            recipient=target_user,
            sender=request.user,
            notification_type="follow",
            message=f"{request.user.username} started following you.",
        )
        record_activity(user=target_user, actor=request.user, event_type="follow_received", points=2)

    return redirect(
        "public_profile",
        username=target_user.username,
    )


def followers_list(request, username):
    profile_user = get_object_or_404(User, username=username)
    followers = User.objects.filter(
        following__following=profile_user,
    ).distinct().order_by("username")
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
    ).distinct().order_by("username")
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


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

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

            return redirect("dashboard")

        return render(
            request,
            "core/login.html",
            {
                "error": "Invalid username or password."
            }
        )

    return render(
        request,
        "core/login.html"
    )


def logout_view(request):
    logout(request)

    return redirect("home")



def contests(request):
    contest_list = Contest.objects.exclude(status="draft").order_by("registration_deadline")
    return render(request, "core/contests.html", {"contests": contest_list})


def contest_detail(request, pk):
    contest = get_object_or_404(Contest, pk=pk)
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
    contest = get_object_or_404(Contest, pk=pk)
    if request.method == "POST":
        now = timezone.now()
        if contest.status not in {"upcoming", "active"} or now > contest.registration_deadline:
            return redirect("contest_detail", pk=contest.pk)
        if contest.max_participants and contest.participants.count() >= contest.max_participants:
            return redirect("contest_detail", pk=contest.pk)
        ContestParticipant.objects.get_or_create(contest=contest, user=request.user)
    return redirect("contest_detail", pk=contest.pk)


@login_required
def contest_submit(request, pk):
    contest = get_object_or_404(Contest, pk=pk)
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
    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.project = project
            report.reported_user = project.owner
            report.save()
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


def refresh_leaderboards():
    users = User.objects.annotate(
        activity_points=Sum("activity_events__points"),
        badge_points=Sum("badges__badge__points"),
    ).order_by("-activity_points", "-badge_points", "username")
    today = timezone.localdate()
    period_starts = {
        "overall": None,
        "weekly": today - timedelta(days=today.weekday()),
        "monthly": today.replace(day=1),
    }
    for period, start in period_starts.items():
        if period == "overall":
            points_map = {user.pk: (user.activity_points or 0) + (user.badge_points or 0) for user in users}
        else:
            points_map = {
                user.pk: ActivityEvent.objects.filter(
                    user=user,
                    created_at__date__gte=start,
                ).aggregate(total=Sum("points"))["total"] or 0
                for user in users
            }
        ranked = sorted(points_map.items(), key=lambda item: (-item[1], User.objects.get(pk=item[0]).username))
        for rank, (user_id, points) in enumerate(ranked, start=1):
            Leaderboard.objects.update_or_create(
                user_id=user_id,
                period=period,
                period_start=start,
                period_end=None,
                defaults={"points": points, "rank": rank},
            )



def leaderboard(request):
    period = request.GET.get("period", "overall")
    refresh_leaderboards()
    entries = Leaderboard.objects.filter(period=period).select_related("user").order_by("rank")[:50]
    return render(request, "core/leaderboard.html", {"entries": entries, "period": period})


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
    projects = request.user.projects.all().annotate(
        likes_total=Count("likes"),
        comments_total=Count("comments"),
        views_total=Count("view_events"),
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
