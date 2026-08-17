from django.urls import path

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
    "profile/<str:username>/",
    views.public_profile,
    name="public_profile",
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