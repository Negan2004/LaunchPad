from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
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

)

from .models import (
    Category,
    Project,
    Profile,
    Like,
    Comment,
    Bookmark,
    BookmarkCollection,
)


def save_project_images(project, image_forms):
    for image_form in image_forms:
        project_image = image_form.save(commit=False)
        project_image.project = project
        project_image.save()


def home(request):
    projects = Project.objects.filter(
        status="published",
        visibility="public"
    ).order_by("-created_at")

    categories = Category.objects.all().order_by("name")

    return render(
        request,
        "core/home.html",
        {
            "projects": projects,
            "categories": categories,
        },
    )


def project_list(request):
    projects = Project.objects.all().order_by("-created_at")

    return render(
        request,
        "core/project_list.html",
        {
            "projects": projects,
        },
    )


def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)

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
        },
    )


@login_required
def add_comment(request, pk):
    project = get_object_or_404(Project, pk=pk)

    if request.method == "POST":
        form = CommentForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.project = project
            comment.save()

    return redirect("project_detail", pk=project.pk)


@login_required
def add_reply(request, comment_id):
    parent_comment = get_object_or_404(
        Comment,
        pk=comment_id
    )

    if request.method == "POST":
        form = CommentForm(request.POST)

        if form.is_valid():
            reply = form.save(commit=False)
            reply.user = request.user
            reply.project = parent_comment.project
            reply.parent = parent_comment
            reply.save()

    return redirect(
        "project_detail",
        pk=parent_comment.project.pk
    )


@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)

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
    project = get_object_or_404(Project, pk=pk)

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

    return redirect(
        "project_detail",
        pk=project.pk
    )

@login_required
def toggle_bookmark(request, pk):
    project = get_object_or_404(Project, pk=pk)

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
        username=username
    )

    profile, created = Profile.objects.get_or_create(
        user=user
    )

    projects = Project.objects.filter(
        owner=user,
        status="published",
        visibility="public"
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "core/public_profile.html",
        {
            "profile_user": user,
            "profile": profile,
            "projects": projects,
        },
    )

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

            return redirect("home")

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
