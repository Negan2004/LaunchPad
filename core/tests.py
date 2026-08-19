import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .forms import ProfileForm
from .models import Bookmark, BookmarkCollection, Category, Comment, Contest, ContestParticipant, Follow, Like, Notification, Profile, Project


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

    def test_project_list_and_detail_enforce_visibility(self):
        visible_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Visible Project",
            description="Public and published.",
            visibility="public",
            status="published",
        )
        private_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Private Project",
            description="Owner only.",
            visibility="private",
            status="published",
        )
        draft_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Draft Project",
            description="Owner only until published.",
            visibility="public",
            status="draft",
        )

        # Anonymous users can only discover and open public/published work.
        list_response = self.client.get(reverse("project_list"))
        self.assertContains(list_response, visible_project.title)
        self.assertNotContains(list_response, private_project.title)
        self.assertNotContains(list_response, draft_project.title)

        self.assertEqual(
            self.client.get(reverse("project_detail", args=[visible_project.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("project_detail", args=[private_project.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("project_detail", args=[draft_project.pk])).status_code,
            404,
        )

        # The owner can still access their own private/draft work.
        self.client.force_login(self.owner)
        list_response = self.client.get(reverse("project_list"))
        self.assertContains(list_response, visible_project.title)
        self.assertContains(list_response, private_project.title)
        self.assertContains(list_response, draft_project.title)

        for project in [private_project, draft_project]:
            response = self.client.get(
                reverse("project_detail", args=[project.pk])
            )
            self.assertEqual(response.status_code, 200)

        # Another authenticated user must not access owner-only projects.
        self.client.force_login(self.other_user)
        list_response = self.client.get(reverse("project_list"))
        self.assertContains(list_response, visible_project.title)
        self.assertNotContains(list_response, private_project.title)
        self.assertNotContains(list_response, draft_project.title)

        for project in [private_project, draft_project]:
            response = self.client.get(
                reverse("project_detail", args=[project.pk])
            )
            self.assertEqual(response.status_code, 404)

    def test_project_engagement_endpoints_respect_visibility(self):
        private_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Private Engagement Project",
            description="Owner only.",
            visibility="private",
            status="published",
        )
        draft_project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Draft Engagement Project",
            description="Owner only.",
            visibility="public",
            status="draft",
        )

        self.client.force_login(self.other_user)
        for project in [private_project, draft_project]:
            for route_name in ["toggle_like", "toggle_bookmark", "add_comment"]:
                response = self.client.post(
                    reverse(route_name, args=[project.pk]),
                    {"content": "Should not be accepted."} if route_name == "add_comment" else {},
                )
                self.assertEqual(response.status_code, 404)

        self.assertFalse(Like.objects.filter(project=private_project).exists())
        self.assertFalse(Like.objects.filter(project=draft_project).exists())
        self.assertFalse(Bookmark.objects.filter(project=private_project).exists())
        self.assertFalse(Bookmark.objects.filter(project=draft_project).exists())
        self.assertFalse(Comment.objects.filter(project=private_project).exists())
        self.assertFalse(Comment.objects.filter(project=draft_project).exists())

        hidden_comment = Comment.objects.create(
            user=self.owner,
            project=private_project,
            content="Hidden comment.",
        )
        for route_name, args in [
            ("add_reply", [hidden_comment.pk]),
            ("delete_comment", [hidden_comment.pk]),
            ("edit_comment", [hidden_comment.pk]),
        ]:
            response = self.client.post(
                reverse(route_name, args=args),
                {"content": "Should not be accepted."} if route_name == "edit_comment" else {},
            )
            self.assertEqual(response.status_code, 404)

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


class FollowSystemTests(TestCase):
    def setUp(self):
        self.follower = User.objects.create_user(
            username="follower",
            password="test-password",
        )
        self.target = User.objects.create_user(
            username="target",
            password="test-password",
        )
        self.third_user = User.objects.create_user(
            username="third-user",
            password="test-password",
        )

    def follow_url(self, username=None):
        return reverse(
            "toggle_follow",
            args=[username or self.target.username],
        )

    def profile_url(self, username=None):
        return reverse(
            "public_profile",
            args=[username or self.target.username],
        )

    def test_authenticated_user_can_follow_and_unfollow(self):
        self.client.force_login(self.follower)

        response = self.client.post(self.follow_url())

        self.assertRedirects(response, self.profile_url())
        self.assertTrue(
            Follow.objects.filter(
                follower=self.follower,
                following=self.target,
            ).exists()
        )
        self.assertEqual(self.target.followers.count(), 1)
        self.assertEqual(self.follower.following.count(), 1)

        profile_response = self.client.get(self.profile_url())
        self.assertContains(profile_response, "1 Followers")
        self.assertContains(profile_response, "0 Following")
        self.assertContains(profile_response, ">Following</button>")

        response = self.client.post(self.follow_url())

        self.assertRedirects(response, self.profile_url())
        self.assertFalse(
            Follow.objects.filter(
                follower=self.follower,
                following=self.target,
            ).exists()
        )
        self.assertEqual(self.target.followers.count(), 0)
        self.assertEqual(self.follower.following.count(), 0)

        profile_response = self.client.get(self.profile_url())
        self.assertContains(profile_response, "0 Followers")
        self.assertContains(profile_response, "0 Following")
        self.assertContains(profile_response, ">Follow</button>")

    def test_follow_state_and_counts_are_correct_for_multiple_relationships(self):
        self.client.force_login(self.follower)
        Follow.objects.create(
            follower=self.follower,
            following=self.target,
        )
        Follow.objects.create(
            follower=self.third_user,
            following=self.target,
        )
        Follow.objects.create(
            follower=self.target,
            following=self.third_user,
        )

        target_profile = self.client.get(self.profile_url())
        self.assertContains(target_profile, "2 Followers")
        self.assertContains(target_profile, "1 Following")
        self.assertContains(target_profile, ">Following</button>")

        self.client.post(self.follow_url())
        self.assertEqual(self.target.followers.count(), 1)
        self.assertEqual(self.follower.following.count(), 0)

        target_profile = self.client.get(self.profile_url())
        self.assertContains(target_profile, "1 Followers")
        self.assertContains(target_profile, "1 Following")
        self.assertContains(target_profile, ">Follow</button>")

    def test_self_follow_is_prevented_and_own_profile_has_no_follow_action(self):
        self.client.force_login(self.follower)

        response = self.client.post(self.follow_url(self.follower.username))

        self.assertRedirects(
            response,
            self.profile_url(self.follower.username),
        )
        self.assertFalse(
            Follow.objects.filter(
                follower=self.follower,
                following=self.follower,
            ).exists()
        )
        self.assertEqual(self.follower.followers.count(), 0)
        self.assertEqual(self.follower.following.count(), 0)

        profile_response = self.client.get(
            self.profile_url(self.follower.username)
        )
        self.assertNotContains(profile_response, "toggle_follow")
        self.assertNotContains(profile_response, ">Follow</button>")
        self.assertNotContains(profile_response, ">Following</button>")

    def test_anonymous_follow_is_prevented(self):
        response = self.client.post(self.follow_url())

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.follow_url()}",
        )
        self.assertFalse(Follow.objects.exists())

    def test_follow_toggle_is_post_only(self):
        self.client.force_login(self.follower)

        response = self.client.get(self.follow_url())

        self.assertEqual(response.status_code, 405)
        self.assertFalse(Follow.objects.exists())

    def test_repeated_follow_requests_do_not_create_duplicates(self):
        self.client.force_login(self.follower)

        self.client.post(self.follow_url())
        self.client.post(self.follow_url())
        self.client.post(self.follow_url())

        self.assertEqual(
            Follow.objects.filter(
                follower=self.follower,
                following=self.target,
            ).count(),
            1,
        )
        self.assertEqual(self.target.followers.count(), 1)
        self.assertEqual(self.follower.following.count(), 1)

    def test_user_cannot_manipulate_another_users_follow_relationship(self):
        Follow.objects.create(
            follower=self.follower,
            following=self.target,
        )
        self.client.force_login(self.third_user)

        response = self.client.post(self.follow_url())

        self.assertRedirects(response, self.profile_url())
        self.assertTrue(
            Follow.objects.filter(
                follower=self.follower,
                following=self.target,
            ).exists()
        )
        self.assertTrue(
            Follow.objects.filter(
                follower=self.third_user,
                following=self.target,
            ).exists()
        )
        self.assertEqual(self.target.followers.count(), 2)

        self.client.post(self.follow_url())
        self.assertTrue(
            Follow.objects.filter(
                follower=self.follower,
                following=self.target,
            ).exists()
        )
        self.assertEqual(self.target.followers.count(), 1)


class PlatformFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("platform-user", password="password", email="platform@example.com")
        self.other = User.objects.create_user("platform-other", password="password", email="other@example.com")
        self.category = Category.objects.create(name="Platform")
        self.project = Project.objects.create(
            owner=self.other,
            category=self.category,
            title="Searchable Project",
            short_description="A searchable summary",
            description="A searchable platform project",
            technologies="Django Python",
            tags="education AI",
            status="published",
            visibility="public",
        )

    def test_discovery_contest_dashboard_and_password_reset_routes(self):
        contest = Contest.objects.create(
            title="Platform Contest",
            description="Build something useful.",
            rules="Be kind.",
            registration_deadline="2030-01-01T00:00:00Z",
            submission_deadline="2030-01-02T00:00:00Z",
            status="active",
        )
        self.assertEqual(self.client.get(reverse("project_list") + "?q=searchable").status_code, 200)
        self.assertContains(self.client.get(reverse("project_list") + "?technology=Django"), self.project.title)
        self.assertEqual(self.client.get(reverse("contests")).status_code, 200)
        self.assertEqual(self.client.get(reverse("contest_detail", args=[contest.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("password_reset")).status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("analytics")).status_code, 200)
        self.assertEqual(self.client.get(reverse("leaderboard")).status_code, 200)

    def test_notification_inbox_is_recipient_scoped_and_readable(self):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.other,
            notification_type="follow",
            message="A new connection.",
        )
        Notification.objects.create(
            recipient=self.other,
            sender=self.user,
            notification_type="follow",
            message="A different connection.",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications"))
        self.assertContains(response, "A new connection.")
        self.assertNotContains(response, "A different connection.")
        self.assertEqual(
            self.client.post(reverse("mark_notification_read", args=[notification.pk])).status_code,
            302,
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
