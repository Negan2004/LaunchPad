"""Regression coverage for the six P1 cleanup fixes.

Each class pins one fix and is written to fail against the pre-fix code.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    ActivityEvent,
    Category,
    Comment,
    Follow,
    Leaderboard,
    Like,
    Notification,
    Profile,
    Project,
    ProjectView,
    Report,
)
from .views import refresh_leaderboards


# ---------------------------------------------------------------------------
# P1 #1 - notification ordering
# ---------------------------------------------------------------------------


class NotificationOrderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notif-user", password="pw-p1-1")
        self.other = User.objects.create_user("notif-other", password="pw-p1-1")

    def make(self, message, days_ago):
        notification = Notification.objects.create(
            recipient=self.user,
            sender=self.other,
            notification_type="like",
            message=message,
        )
        # created_at is auto_now_add, so backdate it explicitly.
        Notification.objects.filter(pk=notification.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return notification

    def test_the_model_declares_a_deterministic_ordering(self):
        self.assertEqual(
            Notification._meta.ordering,
            ["-created_at", "-id"],
        )

    def test_the_default_queryset_is_newest_first(self):
        self.make("oldest", 30)
        self.make("middle", 10)
        self.make("newest", 1)

        messages = list(
            Notification.objects.filter(recipient=self.user).values_list(
                "message", flat=True
            )
        )

        self.assertEqual(messages, ["newest", "middle", "oldest"])

    def test_the_inbox_view_shows_newest_first(self):
        self.make("oldest", 30)
        self.make("newest", 1)
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications"))

        body = response.content.decode()
        self.assertLess(
            body.index("newest"),
            body.index("oldest"),
            "the inbox is not rendering newest-first",
        )

    def test_the_first_hundred_are_the_newest_hundred(self):
        """The view slices [:100]; those must be the 100 most recent."""
        for index in range(130):
            self.make(f"note-{index:03d}", days_ago=200 - index)

        self.client.force_login(self.user)
        shown = list(self.client.get(reverse("notifications")).context["notifications"])

        self.assertEqual(len(shown), 100)
        newest_expected = {f"note-{index:03d}" for index in range(30, 130)}
        self.assertEqual({n.message for n in shown}, newest_expected)

    def test_ordering_is_deterministic_for_identical_timestamps(self):
        stamp = timezone.now()
        for index in range(5):
            notification = Notification.objects.create(
                recipient=self.user,
                notification_type="like",
                message=f"same-{index}",
            )
            Notification.objects.filter(pk=notification.pk).update(created_at=stamp)

        first = list(
            Notification.objects.filter(recipient=self.user).values_list("pk", flat=True)
        )
        second = list(
            Notification.objects.filter(recipient=self.user).values_list("pk", flat=True)
        )

        self.assertEqual(first, second)
        self.assertEqual(first, sorted(first, reverse=True))

    def test_the_inbox_is_still_scoped_to_its_recipient(self):
        self.make("mine", 1)
        Notification.objects.create(
            recipient=self.other, notification_type="like", message="not mine"
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("notifications"))

        self.assertContains(response, "mine")
        self.assertNotContains(response, "not mine")

    def test_marking_read_and_clearing_still_work(self):
        notification = self.make("readable", 1)
        self.client.force_login(self.user)

        self.client.post(reverse("mark_notification_read", args=[notification.pk]))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

        self.client.post(reverse("clear_notifications"))
        self.assertFalse(Notification.objects.filter(recipient=self.user).exists())


# ---------------------------------------------------------------------------
# P1 #2 - profile creation
# ---------------------------------------------------------------------------


class ProfileCreationTests(TestCase):
    def test_registration_creates_a_profile(self):
        self.client.post(
            reverse("register"),
            {
                "username": "signup-user",
                "email": "signup@example.test",
                "password1": "Str0ng-Pass-9xz",
                "password2": "Str0ng-Pass-9xz",
            },
        )

        user = User.objects.get(username="signup-user")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_create_user_creates_a_profile(self):
        user = User.objects.create_user("direct-user", password="pw-p1-1")

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_create_superuser_creates_a_profile(self):
        user = User.objects.create_superuser(
            "super-user", "super@example.test", "pw-p1-1"
        )

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_plain_user_objects_create_creates_a_profile(self):
        """Covers the admin's own save path, which does not use create_user."""
        user = User.objects.create(username="plain-user")

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_exactly_one_profile_is_created(self):
        user = User.objects.create_user("single-user", password="pw-p1-1")

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_resaving_a_user_does_not_create_a_second_profile(self):
        user = User.objects.create_user("resave-user", password="pw-p1-1")
        user.first_name = "Changed"
        user.save()
        user.save()

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_an_existing_profile_is_not_overwritten(self):
        user = User.objects.create_user("keep-user", password="pw-p1-1")
        profile = Profile.objects.get(user=user)
        profile.bio = "Written by the user."
        profile.save()

        user.last_name = "Edited"
        user.save()

        profile.refresh_from_db()
        self.assertEqual(profile.bio, "Written by the user.")

    def test_a_brand_new_user_can_load_pages_that_read_the_profile(self):
        User.objects.create_user("fresh-user", password="pw-p1-1")
        self.client.login(username="fresh-user", password="pw-p1-1")

        for name in ["home", "dashboard", "edit_profile"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

        self.assertEqual(
            self.client.get(
                reverse("public_profile", args=["fresh-user"])
            ).status_code,
            200,
        )

    def test_deleting_a_user_removes_their_profile(self):
        user = User.objects.create_user("gone-user", password="pw-p1-1")
        user_id = user.pk
        user.delete()

        self.assertFalse(Profile.objects.filter(user_id=user_id).exists())


# ---------------------------------------------------------------------------
# P1 #3 - publish activity
# ---------------------------------------------------------------------------


class PublishActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("pub-user", password="pw-p1-1")
        self.category = Category.objects.get(name="Other")
        self.client.force_login(self.user)

    def make(self, title, status):
        return Project.objects.create(
            owner=self.user,
            category=self.category,
            title=title,
            description="d",
            status=status,
            visibility="public",
        )

    def edit(self, project, status):
        return self.client.post(
            reverse("edit_project", args=[project.pk]),
            {
                "title": project.title,
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": status,
                "stage": "prototype",
            },
        )

    def publish_events(self, project):
        return ActivityEvent.objects.filter(
            project=project, event_type="project_published"
        ).count()

    def test_draft_to_published_records_one_event(self):
        project = self.make("Transitions", "draft")

        self.edit(project, "published")

        self.assertEqual(self.publish_events(project), 1)

    def test_published_to_published_records_nothing_further(self):
        project = self.make("Stable", "draft")
        self.edit(project, "published")

        self.edit(project, "published")
        self.edit(project, "published")

        self.assertEqual(
            self.publish_events(project),
            1,
            "editing an already-published project created a duplicate event",
        )

    def test_published_to_draft_records_nothing(self):
        project = self.make("Unpublish", "draft")
        self.edit(project, "published")

        self.edit(project, "draft")

        self.assertEqual(self.publish_events(project), 1)

    def test_draft_to_draft_records_nothing(self):
        project = self.make("Still Draft", "draft")

        self.edit(project, "draft")

        self.assertEqual(self.publish_events(project), 0)

    def test_republishing_after_unpublishing_records_a_second_event(self):
        project = self.make("Cycle", "draft")
        self.edit(project, "published")
        self.edit(project, "draft")

        self.edit(project, "published")

        self.assertEqual(self.publish_events(project), 2)

    def test_creating_a_published_project_still_records_an_event(self):
        self.client.post(
            reverse("create_project"),
            {
                "title": "Born Published",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "published",
                "stage": "prototype",
            },
        )

        project = Project.objects.get(title="Born Published")
        self.assertEqual(self.publish_events(project), 1)

    def test_creating_a_draft_project_records_nothing(self):
        self.client.post(
            reverse("create_project"),
            {
                "title": "Born Draft",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "draft",
                "stage": "prototype",
            },
        )

        project = Project.objects.get(title="Born Draft")
        self.assertEqual(self.publish_events(project), 0)

    def test_publishing_by_edit_awards_the_first_project_badge(self):
        project = self.make("First By Edit", "draft")

        self.edit(project, "published")

        self.assertTrue(
            self.user.badges.filter(badge__name="First Project").exists()
        )


# ---------------------------------------------------------------------------
# P1 #4 - view and report deduplication
# ---------------------------------------------------------------------------


class ProjectViewDeduplicationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("view-owner", password="pw-p1-1")
        self.viewer = User.objects.create_user("view-viewer", password="pw-p1-1")
        self.second = User.objects.create_user("view-second", password="pw-p1-1")
        self.project = Project.objects.create(
            owner=self.owner,
            category=Category.objects.get(name="Other"),
            title="Viewed Project",
            description="d",
            status="published",
            visibility="public",
        )

    def open_it(self):
        return self.client.get(reverse("project_detail", args=[self.project.pk]))

    def rows(self):
        return ProjectView.objects.filter(project=self.project).count()

    def test_repeated_anonymous_visits_in_one_session_count_once(self):
        for _ in range(5):
            self.open_it()

        self.project.refresh_from_db()
        self.assertEqual(self.rows(), 1)
        self.assertEqual(self.project.views_count, 1)

    def test_repeated_visits_by_the_same_signed_in_user_count_once(self):
        self.client.force_login(self.viewer)
        for _ in range(5):
            self.open_it()

        self.project.refresh_from_db()
        self.assertEqual(self.rows(), 1)
        self.assertEqual(self.project.views_count, 1)

    def test_a_signed_in_viewer_is_not_recounted_in_a_new_session(self):
        self.client.force_login(self.viewer)
        self.open_it()
        self.client.logout()
        self.client.force_login(self.viewer)
        self.open_it()

        self.project.refresh_from_db()
        self.assertEqual(
            self.rows(), 1, "the same account was counted twice across sessions"
        )

    def test_different_users_are_counted_separately(self):
        self.client.force_login(self.viewer)
        self.open_it()
        self.client.force_login(self.second)
        self.open_it()

        self.project.refresh_from_db()
        self.assertEqual(self.rows(), 2)
        self.assertEqual(self.project.views_count, 2)

    def test_different_anonymous_sessions_are_counted_separately(self):
        self.open_it()
        self.client.cookies.clear()
        self.open_it()

        self.project.refresh_from_db()
        self.assertEqual(self.rows(), 2)

    def test_views_of_different_projects_are_independent(self):
        other = Project.objects.create(
            owner=self.owner,
            category=Category.objects.get(name="Other"),
            title="Second Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.viewer)
        self.open_it()
        self.client.get(reverse("project_detail", args=[other.pk]))

        self.assertEqual(ProjectView.objects.filter(project=self.project).count(), 1)
        self.assertEqual(ProjectView.objects.filter(project=other).count(), 1)

    def test_the_page_still_renders_on_a_repeat_visit(self):
        self.client.force_login(self.viewer)
        self.open_it()

        self.assertEqual(self.open_it().status_code, 200)

    def test_hidden_projects_still_reject_anonymous_viewers(self):
        hidden = Project.objects.create(
            owner=self.owner,
            category=Category.objects.get(name="Other"),
            title="Hidden",
            description="d",
            status="draft",
            visibility="private",
        )

        response = self.client.get(reverse("project_detail", args=[hidden.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectView.objects.filter(project=hidden).exists())


class ReportDeduplicationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("rep-owner", password="pw-p1-1")
        self.reporter = User.objects.create_user("rep-reporter", password="pw-p1-1")
        self.second = User.objects.create_user("rep-second", password="pw-p1-1")
        self.category = Category.objects.get(name="Other")
        self.project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Reported Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.reporter)

    def report(self, project=None):
        return self.client.post(
            reverse("report_project", args=[(project or self.project).pk]),
            {"reason": "spam", "description": "Looks like spam."},
        )

    def count(self, project=None):
        return Report.objects.filter(project=project or self.project).count()

    def test_a_first_report_is_accepted(self):
        self.report()

        self.assertEqual(self.count(), 1)

    def test_a_second_report_from_the_same_user_is_refused(self):
        self.report()
        self.report()
        self.report()

        self.assertEqual(self.count(), 1)

    def test_the_duplicate_attempt_explains_why(self):
        self.report()

        response = self.client.post(
            reverse("report_project", args=[self.project.pk]),
            {"reason": "spam", "description": "again"},
            follow=True,
        )

        self.assertIn(
            "You have already reported this project. Moderators are looking at it.",
            [str(m) for m in response.context["messages"]],
        )

    def test_a_different_user_can_still_report_the_same_project(self):
        self.report()
        self.client.force_login(self.second)
        self.report()

        self.assertEqual(self.count(), 2)

    def test_the_same_user_can_report_a_different_project(self):
        other = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Another Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.report()
        self.report(other)

        self.assertEqual(self.count(), 1)
        self.assertEqual(self.count(other), 1)

    def test_a_resolved_report_allows_a_fresh_one(self):
        self.report()
        Report.objects.filter(project=self.project).update(status="resolved")

        self.report()

        self.assertEqual(self.count(), 2)

    def test_a_dismissed_report_allows_a_fresh_one(self):
        self.report()
        Report.objects.filter(project=self.project).update(status="dismissed")

        self.report()

        self.assertEqual(self.count(), 2)

    def test_a_report_under_review_still_blocks_a_duplicate(self):
        self.report()
        Report.objects.filter(project=self.project).update(status="reviewing")

        self.report()

        self.assertEqual(self.count(), 1)

    def test_anonymous_users_still_cannot_report(self):
        self.client.logout()

        response = self.report()

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        self.assertEqual(self.count(), 0)

    def test_hidden_projects_still_cannot_be_reported(self):
        hidden = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Hidden",
            description="d",
            status="draft",
            visibility="private",
        )

        response = self.report(hidden)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.count(hidden), 0)


# ---------------------------------------------------------------------------
# P1 #5 - leaderboard point revocation
# ---------------------------------------------------------------------------


class PointRevocationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("pts-owner", password="pw-p1-1")
        self.actor = User.objects.create_user("pts-actor", password="pw-p1-1")
        self.third = User.objects.create_user("pts-third", password="pw-p1-1")
        self.category = Category.objects.get(name="Other")
        self.project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Points Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.actor)

    def points(self, user=None):
        """Read the total from the real ledger, not a hand-kept tally."""
        return (
            ActivityEvent.objects.filter(user=user or self.owner).aggregate(
                total=Sum("points")
            )["total"]
            or 0
        )

    def leaderboard_points(self, user=None):
        refresh_leaderboards()
        return Leaderboard.objects.get(
            user=user or self.owner, period="overall"
        ).points

    def like(self):
        return self.client.post(reverse("toggle_like", args=[self.project.pk]))

    def follow(self):
        return self.client.post(
            reverse("toggle_follow", args=[self.owner.username])
        )

    # ---- likes ----

    def test_a_like_grants_points_and_an_unlike_removes_them(self):
        before = self.points()

        self.like()
        granted = self.points()
        self.assertEqual(granted, before + 1)

        self.like()
        self.assertEqual(self.points(), before, "unliking did not revoke the point")
        self.assertFalse(
            Like.objects.filter(user=self.actor, project=self.project).exists()
        )

    def test_relike_restores_the_points(self):
        self.like()
        self.like()
        self.like()

        self.assertEqual(self.points(), 1)
        self.assertEqual(
            ActivityEvent.objects.filter(event_type="like_received").count(), 1
        )

    def test_like_unlike_cycles_cannot_farm_points(self):
        for _ in range(12):
            self.like()
            self.like()

        self.assertEqual(self.points(), 0)
        self.assertEqual(self.leaderboard_points(), 0)

    def test_unliking_does_not_remove_another_users_like_points(self):
        self.like()
        self.client.force_login(self.third)
        self.like()
        self.assertEqual(self.points(), 2)

        # the third user withdraws theirs
        self.like()

        self.assertEqual(self.points(), 1, "revoking one like removed another's")
        self.assertTrue(
            Like.objects.filter(user=self.actor, project=self.project).exists()
        )

    # ---- follows ----

    def test_a_follow_grants_points_and_an_unfollow_removes_them(self):
        self.follow()
        self.assertEqual(self.points(), 2)

        self.follow()

        self.assertEqual(self.points(), 0)
        self.assertFalse(
            Follow.objects.filter(follower=self.actor, following=self.owner).exists()
        )

    def test_unfollowing_does_not_remove_another_followers_points(self):
        self.follow()
        self.client.force_login(self.third)
        self.follow()
        self.assertEqual(self.points(), 4)

        self.follow()

        self.assertEqual(self.points(), 2)

    # ---- comments ----

    def test_deleting_a_comment_removes_its_points(self):
        self.client.post(
            reverse("add_comment", args=[self.project.pk]), {"content": "hello"}
        )
        comment = Comment.objects.get(project=self.project, user=self.actor)
        self.assertEqual(self.points(), 1)

        self.client.post(reverse("delete_comment", args=[comment.pk]))

        self.assertEqual(self.points(), 0)

    def test_deleting_one_comment_leaves_the_others_points(self):
        for text in ["first", "second", "third"]:
            self.client.post(
                reverse("add_comment", args=[self.project.pk]), {"content": text}
            )
        self.assertEqual(self.points(), 3)
        one = Comment.objects.filter(project=self.project).first()

        self.client.post(reverse("delete_comment", args=[one.pk]))

        self.assertEqual(self.points(), 2)

    def test_deleting_a_reply_does_not_revoke_points(self):
        """add_reply records no activity, so removing one must revoke none."""
        self.client.post(
            reverse("add_comment", args=[self.project.pk]), {"content": "parent"}
        )
        parent = Comment.objects.get(project=self.project, user=self.actor)
        self.client.post(
            reverse("add_reply", args=[parent.pk]), {"content": "a reply"}
        )
        before = self.points()
        reply = Comment.objects.get(parent=parent)

        self.client.post(reverse("delete_comment", args=[reply.pk]))

        self.assertEqual(self.points(), before)

    # ---- independence across action types ----

    def test_undoing_a_like_does_not_touch_follow_or_comment_points(self):
        self.like()
        self.follow()
        self.client.post(
            reverse("add_comment", args=[self.project.pk]), {"content": "hi"}
        )
        self.assertEqual(self.points(), 1 + 2 + 1)

        self.like()

        self.assertEqual(self.points(), 3)
        self.assertEqual(
            ActivityEvent.objects.filter(event_type="follow_received").count(), 1
        )
        self.assertEqual(
            ActivityEvent.objects.filter(event_type="comment_received").count(), 1
        )

    def test_publish_points_survive_engagement_being_undone(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("create_project"),
            {
                "title": "Published Work",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "published",
                "stage": "prototype",
            },
        )
        publish_points = self.points()
        self.assertGreaterEqual(publish_points, 10)

        self.client.force_login(self.actor)
        self.like()
        self.like()

        self.assertEqual(self.points(), publish_points)

    def test_the_leaderboard_reflects_the_revocation(self):
        self.like()
        self.follow()
        granted = self.leaderboard_points()
        self.assertEqual(granted, 3)

        self.like()
        self.follow()

        self.assertEqual(self.leaderboard_points(), 0)


# ---------------------------------------------------------------------------
# P1 #6 - POST-only logout
# ---------------------------------------------------------------------------


class LogoutMethodTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("logout-user", password="pw-p1-1")

    def signed_in(self):
        return "_auth_user_id" in self.client.session

    def test_get_does_not_log_the_user_out(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.signed_in(), "a GET ended the session")

    def test_post_logs_the_user_out(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(self.signed_in())

    def test_the_response_allows_only_post(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response["Allow"], "POST")

    def test_head_and_put_do_not_log_out(self):
        self.client.force_login(self.user)

        for method in [self.client.head, self.client.put, self.client.delete]:
            with self.subTest(method=method.__name__):
                self.assertEqual(method(reverse("logout")).status_code, 405)
                self.assertTrue(self.signed_in())

    def test_the_navigation_renders_a_post_form_with_a_csrf_token(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        body = response.content.decode()
        self.assertIn(f'action="{reverse("logout")}"', body)
        self.assertIn("identity-menu__signout-form", body)
        self.assertIn("csrfmiddlewaretoken", body)
        self.assertNotIn(f'href="{reverse("logout")}"', body)

    def test_logging_out_confirms_itself(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"), follow=True)

        self.assertIn(
            "You have been signed out.",
            [str(m) for m in response.context["messages"]],
        )

    def test_logging_out_while_anonymous_is_harmless(self):
        response = self.client.post(reverse("logout"))

        self.assertRedirects(response, reverse("home"))

    def test_csrf_is_enforced_on_the_logout_endpoint(self):
        from django.test import Client

        enforcing = Client(enforce_csrf_checks=True)
        enforcing.force_login(self.user)

        response = enforcing.post(reverse("logout"))

        self.assertEqual(response.status_code, 403)
