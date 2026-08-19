from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [
    path(
        "",
        views.home,
        name="home",
    ),

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
        "projects/<int:pk>/like/",
        views.toggle_like,
        name="toggle_like",
    ),

    path(
    "projects/<int:pk>/bookmark/",
    views.toggle_bookmark,
    name="toggle_bookmark",
),

path(
    "bookmarks/",
    views.my_bookmarks,
    name="my_bookmarks",
),



path(
    "collections/create/",
    views.create_collection,
    name="create_collection",
),

path(
    "collections/",
    views.my_collections,
    name="my_collections",
),

path(
    "collections/<int:pk>/",
    views.collection_detail,
    name="collection_detail",
),

path(
    "bookmarks/<int:pk>/add-to-collection/",
    views.add_bookmark_to_collection,
    name="add_bookmark_to_collection",
),

    path(
        "projects/<int:pk>/comment/",
        views.add_comment,
        name="add_comment",
    ),

    path(
        "comments/<int:comment_id>/reply/",
        views.add_reply,
        name="add_reply",
    ),

    path(
        "comments/<int:pk>/delete/",
        views.delete_comment,
        name="delete_comment",
    ),

    path(
        "comments/<int:pk>/edit/",
        views.edit_comment,
        name="edit_comment",
    ),
    path(
        "profile/edit/",
        views.edit_profile,
        name="edit_profile",
    ),

    path(
        "profile/<str:username>/follow/",
        views.toggle_follow,
        name="toggle_follow",
    ),
    path(
        "profile/<str:username>/followers/",
        views.followers_list,
        name="followers_list",
    ),
    path(
        "profile/<str:username>/following/",
        views.following_list,
        name="following_list",
    ),

    path(
        "profile/<str:username>/",
        views.public_profile,
        name="public_profile",
    ),


    path(
        "register/",
        views.register,
        name="register",
    ),
    path("password-reset/", auth_views.PasswordResetView.as_view(template_name="core/password_reset_form.html"), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="core/password_reset_done.html"), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(template_name="core/password_reset_confirm.html"), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="core/password_reset_complete.html"), name="password_reset_complete"),

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
    path(
        "notifications/",
        views.notifications,
        name="notifications",
    ),
    path(
        "notifications/<int:pk>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path(
        "notifications/read-all/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
        path(
        "notifications/clear/",
        views.clear_notifications,
        name="clear_notifications",
    ),
    path("contests/", views.contests, name="contests"),
    path("contests/create/", views.create_contest, name="create_contest"),
    path("contests/manage/", views.manage_contests, name="manage_contests"),
    path("contests/<int:pk>/", views.contest_detail, name="contest_detail"),
    path("contests/<int:pk>/register/", views.contest_register, name="contest_register"),
    path("contests/<int:pk>/submit/", views.contest_submit, name="contest_submit"),
    path("contests/<int:pk>/edit/", views.edit_contest, name="edit_contest"),
    path("submissions/<int:pk>/review/", views.review_submission, name="review_submission"),
    path("certificates/<int:pk>/", views.certificate_detail, name="certificate_detail"),
    path("projects/<int:pk>/report/", views.report_project, name="report_project"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("analytics/", views.analytics, name="analytics"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),


]
