from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),

    path(
        "projects/",
        views.project_list,
        name="project_list",
    ),

    path(
        "projects/<int:pk>/",
        views.project_detail,
        name="project_detail",
    ),

    path(
        "projects/create/",
        views.create_project,
        name="create_project",
    ),

    path(
        "projects/<int:pk>/edit/",
        views.edit_project,
        name="edit_project",
    ),

    path(
        "projects/<int:pk>/delete/",
        views.delete_project,
        name="delete_project",
    ),

    path(
        "profile/edit/",
        views.edit_profile,
        name="edit_profile",
    ),

    path(
        "register/",
        views.register,
        name="register",
    ),

    path(
        "login/",
        views.login_view,
        name="login",
    ),

    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),
]