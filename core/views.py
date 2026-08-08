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

from .models import Category, Project, Profile


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

    return render(
        request,
        "core/project_detail.html",
        {
            "project": project,
        },
    )


@login_required
def create_project(request):
    if request.method == "POST":
        form = ProjectForm(request.POST, request.FILES)

        if form.is_valid():
            project = form.save(commit=False)

            # Project model uses "owner", not "user"
            project.owner = request.user

            project.save()

            return redirect("project_detail", pk=project.pk)

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
            return redirect("project_detail", pk=project.pk)

    else:
        form = ProjectForm(instance=project)

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
    # Create the profile automatically if the user doesn't have one
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
        form = ProfileForm(instance=profile)

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

    return render(request, "core/login.html")


def logout_view(request):
    logout(request)
    return redirect("home")