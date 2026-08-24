"""Tests for the seed_test_data management command.

The safety guarantees matter more than the data itself, so most of this file is
about what --clear must refuse to touch.
"""

import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.conf import settings
from django.db.models import F
from django.test import TestCase, override_settings

from .models import (
    ActivityEvent,
    Badge,
    Bookmark,
    BookmarkCollection,
    Category,
    Comment,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Follow,
    Leaderboard,
    Like,
    Notification,
    Profile,
    Project,
)
from .management.commands.seed_test_data import SEED_EMAIL_DOMAIN


def seed(**kwargs):
    options = {
        "users": 8,
        "min_projects": 1,
        "max_projects": 4,
        "no_media": True,
        "verbosity": 0,
    }
    options.update(kwargs)
    call_command("seed_test_data", stdout=StringIO(), **options)


class SeederIsolationMixin:
    """Keep the seeder off the real filesystem.

    Two things escape the test database and would otherwise hit the developer's
    working copy:

    * the manifest file, which the seeder writes next to manage.py, and
    * MEDIA_ROOT - `--clear` calls remove_seeded_media(), which globs and
      deletes seed_* files from the real media directory regardless of which
      database the test is using.

    Both are redirected into a temporary directory for the duration of a test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)

        manifest_patch = mock.patch(
            "core.management.commands.seed_test_data.MANIFEST_PATH",
            root / "seed_manifest.json",
        )
        manifest_patch.start()
        self.addCleanup(manifest_patch.stop)

        media_override = override_settings(MEDIA_ROOT=str(root / "media"))
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.addCleanup(self._tmp.cleanup)
        super().setUp()

    def test_media_root_is_isolated_from_the_real_project(self):
        """Guard: a regression here silently deletes a developer's media."""
        self.assertNotEqual(
            Path(settings.MEDIA_ROOT).resolve(),
            (Path(settings.BASE_DIR) / "media").resolve(),
            "seed tests must not run against the real MEDIA_ROOT",
        )


class SeedCommandTests(SeederIsolationMixin, TestCase):
    def test_it_creates_users_with_profiles(self):
        seed(users=10)

        seeded = User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}")
        self.assertEqual(seeded.count(), 10)
        for person in seeded:
            self.assertTrue(Profile.objects.filter(user=person).exists())

    def test_usernames_are_unique(self):
        seed(users=30)

        usernames = list(User.objects.values_list("username", flat=True))
        self.assertEqual(len(usernames), len(set(usernames)))

    def test_profiles_are_populated_with_real_fields(self):
        seed(users=6)

        profile = Profile.objects.first()
        self.assertTrue(profile.display_name)
        self.assertTrue(profile.bio)
        self.assertTrue(profile.college)
        self.assertTrue(profile.education)
        self.assertTrue(profile.skills)

    def test_project_count_respects_the_requested_range(self):
        seed(users=12, min_projects=2, max_projects=5)

        for person in User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}"):
            count = person.projects.count()
            self.assertGreaterEqual(count, 2)
            self.assertLessEqual(count, 5)

    def test_projects_use_a_mix_of_states(self):
        seed(users=40, min_projects=3, max_projects=6)

        combos = set(Project.objects.values_list("status", "visibility"))
        self.assertIn(("published", "public"), combos)
        self.assertIn(("draft", "private"), combos)
        self.assertIn(("published", "private"), combos)
        self.assertGreater(
            len(combos), 2, "visibility enforcement needs a varied dataset"
        )

    def test_most_projects_are_public_but_not_all(self):
        seed(users=40, min_projects=3, max_projects=6)

        total = Project.objects.count()
        public = Project.objects.filter(status="published", visibility="public").count()
        share = public / total

        self.assertGreater(share, 0.5)
        self.assertLess(share, 0.9, "some projects must stay hidden")

    def test_project_descriptions_are_not_all_identical(self):
        seed(users=15, min_projects=2, max_projects=5)

        descriptions = set(Project.objects.values_list("description", flat=True))
        self.assertGreater(len(descriptions), 10)

    def test_it_reuses_existing_categories_rather_than_inventing_them(self):
        before = set(Category.objects.values_list("name", flat=True))

        seed(users=10)

        self.assertEqual(set(Category.objects.values_list("name", flat=True)), before)

    def test_no_self_follows_are_created(self):
        seed(users=20)

        self.assertFalse(
            Follow.objects.filter(follower=F("following")).exists(),
            "the seeder created a self-follow",
        )

    def test_no_duplicate_follows_are_created(self):
        seed(users=20)

        pairs = list(Follow.objects.values_list("follower_id", "following_id"))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_no_duplicate_likes_are_created(self):
        seed(users=20, min_projects=2, max_projects=4)

        pairs = list(Like.objects.values_list("user_id", "project_id"))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_no_duplicate_bookmarks_are_created(self):
        seed(users=20, min_projects=2, max_projects=4)

        pairs = list(Bookmark.objects.values_list("user_id", "project_id"))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_nobody_likes_their_own_project(self):
        seed(users=20, min_projects=2, max_projects=4)

        self.assertFalse(
            any(
                like.user_id == like.project.owner_id
                for like in Like.objects.select_related("project")
            )
        )

    def test_likes_only_land_on_discoverable_projects(self):
        seed(users=20, min_projects=2, max_projects=4)

        for like in Like.objects.select_related("project"):
            self.assertEqual(like.project.status, "published")
            self.assertEqual(like.project.visibility, "public")

    def test_some_bookmarks_are_left_unfiled(self):
        """Keeps the null-collection path that used to 500 covered by real data."""
        seed(users=25, min_projects=2, max_projects=4)

        self.assertTrue(Bookmark.objects.filter(collection__isnull=True).exists())
        self.assertTrue(Bookmark.objects.filter(collection__isnull=False).exists())

    def test_bookmark_collections_belong_to_the_bookmark_owner(self):
        seed(users=20, min_projects=2, max_projects=4)

        for bookmark in Bookmark.objects.select_related("collection").exclude(
            collection__isnull=True
        ):
            self.assertEqual(bookmark.collection.user_id, bookmark.user_id)

    def test_replies_are_attached_to_the_same_project_as_their_parent(self):
        seed(users=20, min_projects=2, max_projects=4)

        for reply in Comment.objects.exclude(parent__isnull=True).select_related("parent"):
            self.assertEqual(reply.project_id, reply.parent.project_id)

    def test_contests_cover_several_statuses(self):
        seed(users=15, min_projects=2, max_projects=4)

        statuses = set(Contest.objects.values_list("status", flat=True))
        self.assertIn("draft", statuses)
        self.assertIn("active", statuses)
        self.assertGreaterEqual(len(statuses), 3)

    def test_draft_contests_have_no_participants(self):
        seed(users=15, min_projects=2, max_projects=4)

        for contest in Contest.objects.filter(status="draft"):
            self.assertEqual(contest.participants.count(), 0)

    def test_submitted_projects_are_public_and_published(self):
        """The seeder must not depend on the open private-submission defect."""
        seed(users=25, min_projects=2, max_projects=5)

        for submission in ContestSubmission.objects.select_related("project"):
            self.assertEqual(submission.project.status, "published")
            self.assertEqual(submission.project.visibility, "public")

    def test_a_submission_belongs_to_its_participant(self):
        seed(users=20, min_projects=2, max_projects=4)

        for submission in ContestSubmission.objects.select_related("participant"):
            self.assertEqual(submission.contest_id, submission.participant.contest_id)
            self.assertEqual(submission.project.owner_id, submission.participant.user_id)

    def test_leaderboards_are_computed_by_the_real_logic(self):
        seed(users=15, min_projects=2, max_projects=4)

        self.assertTrue(Leaderboard.objects.exists())
        for period in ["overall", "weekly", "monthly"]:
            self.assertTrue(Leaderboard.objects.filter(period=period).exists())

    def test_leaderboard_points_match_the_underlying_events(self):
        """Nothing is fabricated: overall points must equal events + badges."""
        from django.db.models import Sum

        seed(users=12, min_projects=2, max_projects=4)

        entry = Leaderboard.objects.filter(period="overall").order_by("rank").first()
        events = (
            ActivityEvent.objects.filter(user=entry.user).aggregate(t=Sum("points"))["t"]
            or 0
        )
        badges = (
            entry.user.badges.aggregate(t=Sum("badge__points"))["t"] or 0
        )

        self.assertEqual(entry.points, events + badges)

    def test_notifications_are_addressed_to_a_real_recipient(self):
        seed(users=20, min_projects=2, max_projects=4)

        self.assertTrue(Notification.objects.exists())
        for notification in Notification.objects.select_related("recipient")[:50]:
            self.assertIsNotNone(notification.recipient_id)

    def test_activity_events_use_declared_event_types(self):
        seed(users=15, min_projects=2, max_projects=4)

        allowed = {choice[0] for choice in ActivityEvent.EVENT_CHOICES}
        used = set(ActivityEvent.objects.values_list("event_type", flat=True))
        self.assertTrue(used)
        self.assertTrue(used.issubset(allowed))

    def test_seeding_is_reproducible_for_a_given_seed(self):
        seed(users=8, seed=1234)
        first = list(Project.objects.order_by("pk").values_list("title", flat=True))

        Project.objects.all().delete()
        User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").delete()

        seed(users=8, seed=1234)
        second = list(Project.objects.order_by("pk").values_list("title", flat=True))

        self.assertEqual(first, second)

    def test_it_rejects_an_invalid_project_range(self):
        with self.assertRaises(CommandError):
            seed(min_projects=5, max_projects=2)

    def test_it_rejects_a_zero_user_count(self):
        with self.assertRaises(CommandError):
            seed(users=0)

    def test_it_refuses_to_run_without_categories(self):
        Category.objects.all().delete()

        with self.assertRaises(CommandError):
            seed(users=5)

    def test_the_password_is_never_written_to_stdout(self):
        from .management.commands.seed_test_data import TEST_PASSWORD

        out = StringIO()
        call_command(
            "seed_test_data",
            users=5, min_projects=1, max_projects=2, no_media=True,
            stdout=out,
        )

        self.assertNotIn(TEST_PASSWORD, out.getvalue())

    def test_seeded_accounts_can_actually_log_in(self):
        from .management.commands.seed_test_data import TEST_PASSWORD
        from django.urls import reverse

        seed(users=5)
        person = User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").first()

        response = self.client.post(
            reverse("login"),
            {"username": person.username, "password": TEST_PASSWORD},
        )

        self.assertRedirects(response, reverse("dashboard"))

    def test_seeded_accounts_are_never_staff_or_superusers(self):
        seed(users=20)

        seeded = User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}")
        self.assertFalse(seeded.filter(is_staff=True).exists())
        self.assertFalse(seeded.filter(is_superuser=True).exists())


class ClearSafetyTests(SeederIsolationMixin, TestCase):
    """--clear must only ever remove what the seeder made."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            "real-admin", "admin@realdomain.example", "pw-admin-1"
        )
        self.human = User.objects.create_user(
            "real-person", "person@realdomain.example", "pw-human-1"
        )
        self.human_project = Project.objects.create(
            owner=self.human,
            category=Category.objects.first(),
            title="A Real Person's Project",
            description="Must survive --clear.",
            status="published",
            visibility="public",
        )

    def clear(self):
        call_command("seed_test_data", clear=True, stdout=StringIO(), verbosity=0)

    def test_clear_removes_every_seeded_account(self):
        seed(users=10)
        self.assertEqual(
            User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").count(), 10
        )

        self.clear()

        self.assertEqual(
            User.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").count(), 0
        )

    def test_clear_never_deletes_the_superuser(self):
        seed(users=10)

        self.clear()

        self.admin.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        self.assertTrue(self.admin.is_superuser)

    def test_clear_never_deletes_a_manually_created_user(self):
        seed(users=10)

        self.clear()

        self.assertTrue(User.objects.filter(pk=self.human.pk).exists())

    def test_clear_never_deletes_a_manually_created_project(self):
        seed(users=10)

        self.clear()

        self.assertTrue(Project.objects.filter(pk=self.human_project.pk).exists())

    def test_clear_never_deletes_categories(self):
        seed(users=10)
        before = Category.objects.count()

        self.clear()

        self.assertEqual(Category.objects.count(), before)

    def test_clear_removes_seeded_projects_and_engagement(self):
        seed(users=15, min_projects=2, max_projects=4)
        self.assertTrue(Like.objects.exists())

        self.clear()

        # Only the human's project should remain.
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(Project.objects.first().pk, self.human_project.pk)
        self.assertFalse(Like.objects.exists())
        self.assertFalse(Follow.objects.exists())
        self.assertFalse(BookmarkCollection.objects.exists())
        self.assertFalse(ContestParticipant.objects.exists())

    def test_clear_removes_seeded_contests(self):
        seed(users=10)
        self.assertTrue(Contest.objects.exists())

        self.clear()

        self.assertFalse(Contest.objects.exists())

    def test_clear_keeps_a_contest_that_a_real_user_joined(self):
        seed(users=10)
        contest = Contest.objects.filter(status="active").first()
        ContestParticipant.objects.create(contest=contest, user=self.human)

        self.clear()

        self.assertTrue(
            Contest.objects.filter(pk=contest.pk).exists(),
            "a contest with a non-seeded participant must be preserved",
        )

    def test_clear_keeps_a_badge_still_awarded_to_a_real_user(self):
        seed(users=10)
        badge = Badge.objects.first()
        from .models import UserBadge

        UserBadge.objects.create(user=self.human, badge=badge)

        self.clear()

        self.assertTrue(Badge.objects.filter(pk=badge.pk).exists())

    def test_clear_on_an_unseeded_database_is_a_no_op(self):
        before = User.objects.count()

        self.clear()

        self.assertEqual(User.objects.count(), before)

    def test_clear_is_idempotent(self):
        seed(users=8)

        self.clear()
        self.clear()

        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.human.pk).exists())
