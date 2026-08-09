from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    RegisterForm,
    CategoryForm,
    CommentForm,
    ProfileForm,
    ProjectForm,
    UserRegistrationForm,
)

from .models import Category, Project, Profile, Like, Comment


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

    if request.user.is_authenticated:
        user_has_liked = Like.objects.filter(
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
def create_project(request):
    if request.method == "POST":
        form = ProjectForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            project = form.save(commit=False)

            project.owner = request.user

            project.save()

            return redirect(
                "project_detail",
                pk=project.pk
            )
    else:
        form = ProjectForm()

    return render(
        request,
        "core/project_form.html",
        {
            "form": form,
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

        if form.is_valid():
            form.save()

            return redirect(
                "project_detail",
                pk=project.pk
            )
    else:
        form = ProjectForm(
            instance=project
        )

    return render(
        request,
        "core/project_form.html",
        {
            "form": form,
            "edit_mode": True,
            "project": project,
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