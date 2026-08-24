"""Feedback messages: every mutating action should confirm itself."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Bookmark, BookmarkCollection, Category, Comment, Project


class MessageFeedbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("msg-user", password="pw-msg-1")
        self.other = User.objects.create_user("msg-other", password="pw-msg-1")
        self.category = Category.objects.get(name="Other")
        self.project = Project.objects.create(
            owner=self.other,
            category=self.category,
            title="Message Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.user)

    def message_texts(self, response):
        return [str(m) for m in response.context["messages"]]

    def post_and_follow(self, url, data=None):
        return self.client.post(url, data or {}, follow=True)

    # ---- rendering ----

    def test_the_base_template_renders_the_message_stack(self):
        response = self.post_and_follow(
            reverse("toggle_like", args=[self.project.pk])
        )

        self.assertContains(response, "message-stack")
        self.assertContains(response, "message--success")

    def test_pages_without_messages_do_not_render_an_empty_stack(self):
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "message-stack")

    def test_messages_carry_a_level_tag_class(self):
        response = self.post_and_follow(
            reverse("toggle_like", args=[self.project.pk])
        )
        self.post_and_follow(reverse("toggle_like", args=[self.project.pk]))

        self.assertContains(response, "message--success")

    # ---- projects ----

    def test_creating_a_project_confirms_itself(self):
        response = self.post_and_follow(
            reverse("create_project"),
            {
                "title": "Fresh Project",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "published",
                "stage": "prototype",
            },
        )

        self.assertIn("'Fresh Project' was created.", self.message_texts(response))

    def test_updating_a_project_confirms_itself(self):
        mine = Project.objects.create(
            owner=self.user,
            category=self.category,
            title="Mine",
            description="d",
        )

        response = self.post_and_follow(
            reverse("edit_project", args=[mine.pk]),
            {
                "title": "Mine Renamed",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "published",
                "stage": "prototype",
            },
        )

        self.assertIn("'Mine Renamed' was updated.", self.message_texts(response))

    def test_deleting_a_project_confirms_itself(self):
        mine = Project.objects.create(
            owner=self.user,
            category=self.category,
            title="Doomed",
            description="d",
        )

        response = self.post_and_follow(reverse("delete_project", args=[mine.pk]))

        self.assertIn("'Doomed' was deleted.", self.message_texts(response))

    # ---- profile ----

    def test_updating_a_profile_confirms_itself(self):
        response = self.post_and_follow(
            reverse("edit_profile"),
            {
                "display_name": "Msg User",
                "bio": "",
                "college": "",
                "education": "",
                "skills": "",
                "portfolio_url": "",
                "github_url": "",
                "linkedin_url": "",
                "twitter_url": "",
            },
        )

        self.assertIn("Your profile was updated.", self.message_texts(response))

    # ---- engagement ----

    def test_liking_and_unliking_both_report_back(self):
        liked = self.post_and_follow(reverse("toggle_like", args=[self.project.pk]))
        self.assertIn(
            "You appreciated 'Message Project'.",
            self.message_texts(liked),
        )

        unliked = self.post_and_follow(reverse("toggle_like", args=[self.project.pk]))
        self.assertIn("Like removed.", self.message_texts(unliked))

    def test_bookmarking_and_unbookmarking_both_report_back(self):
        saved = self.post_and_follow(
            reverse("toggle_bookmark", args=[self.project.pk])
        )
        self.assertIn(
            "'Message Project' saved for later.",
            self.message_texts(saved),
        )

        removed = self.post_and_follow(
            reverse("toggle_bookmark", args=[self.project.pk])
        )
        self.assertIn("Removed from your saved work.", self.message_texts(removed))

    def test_following_and_unfollowing_both_report_back(self):
        followed = self.post_and_follow(
            reverse("toggle_follow", args=[self.other.username])
        )
        self.assertIn(
            f"You are now following {self.other.username}.",
            self.message_texts(followed),
        )

        unfollowed = self.post_and_follow(
            reverse("toggle_follow", args=[self.other.username])
        )
        self.assertIn(
            f"You no longer follow {self.other.username}.",
            self.message_texts(unfollowed),
        )

    # ---- comments ----

    def test_posting_a_comment_confirms_itself(self):
        response = self.post_and_follow(
            reverse("add_comment", args=[self.project.pk]),
            {"content": "Nice work."},
        )

        self.assertIn("Your comment was posted.", self.message_texts(response))

    def test_replying_confirms_itself(self):
        parent = Comment.objects.create(
            user=self.other,
            project=self.project,
            content="Parent",
        )

        response = self.post_and_follow(
            reverse("add_reply", args=[parent.pk]),
            {"content": "A reply."},
        )

        self.assertIn("Your reply was posted.", self.message_texts(response))

    def test_editing_a_comment_confirms_itself(self):
        comment = Comment.objects.create(
            user=self.user,
            project=self.project,
            content="Mine",
        )

        response = self.post_and_follow(
            reverse("edit_comment", args=[comment.pk]),
            {"content": "Mine, edited."},
        )

        self.assertIn("Your comment was updated.", self.message_texts(response))

    def test_deleting_a_comment_confirms_itself(self):
        comment = Comment.objects.create(
            user=self.user,
            project=self.project,
            content="Mine",
        )

        response = self.post_and_follow(
            reverse("delete_comment", args=[comment.pk])
        )

        self.assertIn("Comment deleted.", self.message_texts(response))

    # ---- collections ----

    def test_creating_a_collection_confirms_itself(self):
        response = self.post_and_follow(
            reverse("create_collection"),
            {"name": "AI Inspiration", "description": ""},
        )

        self.assertIn(
            "Collection 'AI Inspiration' was created.",
            self.message_texts(response),
        )

    def test_assigning_a_bookmark_to_a_collection_confirms_itself(self):
        self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))
        bookmark = Bookmark.objects.get(user=self.user, project=self.project)
        collection = BookmarkCollection.objects.create(
            user=self.user,
            name="Shortlist",
        )

        response = self.post_and_follow(
            reverse("add_bookmark_to_collection", args=[bookmark.pk]),
            {"collection": collection.pk},
        )

        self.assertIn("Saved to 'Shortlist'.", self.message_texts(response))

    def test_clearing_a_collection_assignment_explains_what_happened(self):
        self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))
        bookmark = Bookmark.objects.get(user=self.user, project=self.project)

        response = self.post_and_follow(
            reverse("add_bookmark_to_collection", args=[bookmark.pk]),
            {"collection": ""},
        )

        self.assertIn("Removed from all collections.", self.message_texts(response))

    # ---- reports ----

    def test_reporting_a_project_confirms_itself(self):
        response = self.post_and_follow(
            reverse("report_project", args=[self.project.pk]),
            {"reason": "spam", "description": "Looks like spam."},
        )

        self.assertIn(
            "Thanks - your report has been sent to the moderators.",
            self.message_texts(response),
        )

    # ---- notifications ----

    def test_clearing_the_inbox_confirms_itself(self):
        response = self.post_and_follow(reverse("clear_notifications"))

        self.assertIn("Your inbox was cleared.", self.message_texts(response))
