import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .forms import ProfileForm
from .models import Bookmark, BookmarkCollection, Category, Comment, Like, Profile, Project


class MediaAndProjectImageTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.media_settings = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_settings.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_settings.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user(
            username="project-owner",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="other-user",
            password="test-password",
        )
        self.category = Category.objects.create(name="Testing")

    def image_file(self, name):
        image_data = BytesIO()
        Image.new("RGB", (1, 1), "red").save(image_data, format="PNG")

        return SimpleUploadedFile(
            name,
            image_data.getvalue(),
            content_type="image/png",
        )

    def project_data(self, title="Image Project"):
        return {
            "title": title,
            "description": "A project with uploaded images.",
            "category": self.category.pk,
            "demo_url": "",
            "repository_url": "",
            "visibility": "public",
            "status": "published",
        }

    def test_avatar_upload_is_saved_and_shown_on_public_profile(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("edit_profile"),
            {
                "bio": "",
                "skills": "",
                "portfolio_url": "",
                "avatar": self.image_file("avatar.png"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        profile = Profile.objects.get(user=self.owner)
        self.assertTrue(profile.avatar.name.startswith("avatars/"))

        response = self.client.get(
            reverse("public_profile", args=[self.owner.username])
        )

        self.assertContains(response, profile.avatar.url)
        self.assertContains(self.client.get(reverse("home")), profile.avatar.url)

    def test_missing_avatar_and_null_profile_values_use_safe_fallbacks(self):
        profile = Profile.objects.create(
            user=self.owner,
            avatar="avatars/missing-avatar.png",
            bio="null",
            skills="NULL",
            portfolio_url="",
        )

        form = ProfileForm(instance=profile)
        self.assertEqual(form.initial["bio"], "")
        self.assertEqual(form.initial["skills"], "")
        self.assertIsNone(form.initial["avatar"])

        public_response = self.client.get(
            reverse("public_profile", args=[self.owner.username])
        )
        self.assertNotContains(public_response, "null")
        self.assertNotContains(
            public_response,
            'src="/media/avatars/missing-avatar.png"',
        )

        self.client.force_login(self.owner)
        navigation_response = self.client.get(reverse("home"))
        self.assertContains(navigation_response, "identity-avatar")
        self.assertContains(navigation_response, "View public profile")
        self.assertNotContains(
            navigation_response,
            'src="/media/avatars/missing-avatar.png"',
        )

        studio_response = self.client.get(reverse("edit_profile"))
        self.assertNotContains(
            studio_response,
            '/media/avatars/missing-avatar.png',
        )

    def test_project_creation_and_editing_keep_existing_images(self):
        self.client.force_login(self.owner)
        creation_data = self.project_data()
        creation_data["images"] = [
            self.image_file("first.png"),
            self.image_file("second.png"),
        ]

        response = self.client.post(reverse("create_project"), creation_data)

        project = Project.objects.get(title="Image Project")
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertEqual(project.images.count(), 2)
        original_images = set(project.images.values_list("image", flat=True))

        response = self.client.get(reverse("project_detail", args=[project.pk]))
        for image_name in original_images:
            self.assertContains(response, f"/media/{image_name}")

        edit_data = self.project_data()
        edit_data["images"] = [self.image_file("third.png")]
        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            edit_data,
        )

        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertEqual(project.images.count(), 3)
        self.assertTrue(
            original_images.issubset(
                set(project.images.values_list("image", flat=True))
            )
        )

    def test_other_user_cannot_add_images_through_project_edit(self):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Owner Project",
            description="Only the owner can edit this project.",
            visibility="public",
            status="published",
        )
        self.client.force_login(self.other_user)
        edit_data = self.project_data(title=project.title)
        edit_data["images"] = [self.image_file("blocked.png")]

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            edit_data,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(project.images.count(), 0)

    def test_project_deletion_still_works_for_the_owner(self):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Deletable Project",
            description="This checks the existing deletion workflow.",
        )
        self.client.force_login(self.owner)

        response = self.client.post(reverse("delete_project", args=[project.pk]))

        self.assertRedirects(response, reverse("project_list"))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_existing_engagement_and_collection_actions_still_work(self):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Engagement Project",
            description="This checks existing project actions.",
            visibility="public",
            status="published",
        )
        self.client.force_login(self.owner)

        self.client.post(reverse("toggle_like", args=[project.pk]))
        self.client.post(
            reverse("add_comment", args=[project.pk]),
            {"content": "A comment that should still save."},
        )
        self.client.post(reverse("toggle_bookmark", args=[project.pk]))
        self.client.post(
            reverse("create_collection"),
            {"name": "Image ideas", "description": "Existing collection flow."},
        )

        bookmark = Bookmark.objects.get(user=self.owner, project=project)
        collection = BookmarkCollection.objects.get(user=self.owner, name="Image ideas")
        self.client.post(
            reverse("add_bookmark_to_collection", args=[bookmark.pk]),
            {"collection": collection.pk},
        )

        self.assertTrue(Like.objects.filter(user=self.owner, project=project).exists())
        self.assertTrue(
            Comment.objects.filter(user=self.owner, project=project).exists()
        )
        bookmark.refresh_from_db()
        self.assertEqual(bookmark.collection, collection)

    def test_existing_page_routes_render_with_redesigned_templates(self):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Route Project",
            description="This checks the existing page routes.",
            visibility="public",
            status="published",
        )
        comment = Comment.objects.create(
            user=self.owner,
            project=project,
            content="A route test comment.",
        )
        collection = BookmarkCollection.objects.create(
            user=self.owner,
            name="Route Collection",
        )
        bookmark = Bookmark.objects.create(
            user=self.owner,
            project=project,
            collection=collection,
        )

        public_routes = [
            reverse("home"),
            reverse("project_list"),
            reverse("project_detail", args=[project.pk]),
            reverse("public_profile", args=[self.owner.username]),
            reverse("register"),
            reverse("login"),
        ]
        for route in public_routes:
            self.assertEqual(self.client.get(route).status_code, 200)

        self.client.force_login(self.owner)
        authenticated_routes = [
            reverse("create_project"),
            reverse("edit_project", args=[project.pk]),
            reverse("delete_project", args=[project.pk]),
            reverse("edit_profile"),
            reverse("my_bookmarks"),
            reverse("my_collections"),
            reverse("create_collection"),
            reverse("collection_detail", args=[collection.pk]),
            reverse("add_bookmark_to_collection", args=[bookmark.pk]),
            reverse("edit_comment", args=[comment.pk]),
        ]
        for route in authenticated_routes:
            self.assertEqual(self.client.get(route).status_code, 200)

        self.assertRedirects(self.client.get(reverse("logout")), reverse("home"))

    def test_collection_isolation_is_preserved(self):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Private Collection Project",
            description="This checks collection isolation.",
        )
        collection = BookmarkCollection.objects.create(
            user=self.owner,
            name="Owner Only",
        )
        bookmark = Bookmark.objects.create(
            user=self.owner,
            project=project,
            collection=collection,
        )
        self.client.force_login(self.other_user)

        self.assertEqual(
            self.client.get(reverse("collection_detail", args=[collection.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("add_bookmark_to_collection", args=[bookmark.pk])
            ).status_code,
            404,
        )

    def test_public_pages_only_render_public_published_projects(self):
        visible_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Visible Project",
            description="Public and published.",
            visibility="public",
            status="published",
        )
        Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Private Project",
            description="Not for public pages.",
            visibility="private",
            status="published",
        )
        Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Draft Project",
            description="Not for public pages.",
            visibility="public",
            status="draft",
        )

        for route in [
            reverse("home"),
            reverse("public_profile", args=[self.owner.username]),
        ]:
            response = self.client.get(route)
            self.assertContains(response, visible_project.title)
            self.assertNotContains(response, "Private Project")
            self.assertNotContains(response, "Draft Project")
