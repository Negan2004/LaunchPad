"""Query-count and correctness regressions for the performance work.

The ceilings below are deliberately loose - the point is to catch a
reintroduced N+1 (where cost grows with row count), not to freeze an exact
number that innocent refactoring would break.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import (
    ActivityEvent,
    Badge,
    Bookmark,
    BookmarkCollection,
    Category,
    Leaderboard,
    Project,
    ProjectImage,
    UserBadge,
)
from .views import refresh_leaderboards


class LeaderboardCorrectnessTests(TestCase):
    """The old annotate() summed two multi-valued relations at once."""

    def setUp(self):
        self.user = User.objects.create_user("lb-user", password="pw-perf-1")

    def test_activity_and_badge_points_are_not_multiplied_together(self):
        # 3 events worth 10 = 30, plus 2 badges worth 5 = 10. True total 40.
        for _ in range(3):
            ActivityEvent.objects.create(
                user=self.user,
                event_type="like_received",
                points=10,
            )
        for index in range(2):
            badge = Badge.objects.create(
                name=f"Perf Badge {index}",
                description="d",
                points=5,
            )
            UserBadge.objects.create(user=self.user, badge=badge)

        refresh_leaderboards()

        entry = Leaderboard.objects.get(user=self.user, period="overall")
        self.assertEqual(
            entry.points,
            40,
            "join fan-out has come back: activity and badge sums are multiplying",
        )

    def test_points_are_correct_with_only_activity_events(self):
        ActivityEvent.objects.create(
            user=self.user,
            event_type="project_published",
            points=10,
        )

        refresh_leaderboards()

        self.assertEqual(
            Leaderboard.objects.get(user=self.user, period="overall").points,
            10,
        )

    def test_points_are_correct_with_only_badges(self):
        badge = Badge.objects.create(name="Solo", description="d", points=25)
        UserBadge.objects.create(user=self.user, badge=badge)

        refresh_leaderboards()

        self.assertEqual(
            Leaderboard.objects.get(user=self.user, period="overall").points,
            25,
        )

    def test_a_user_with_no_activity_is_ranked_with_zero_points(self):
        refresh_leaderboards()

        entry = Leaderboard.objects.get(user=self.user, period="overall")
        self.assertEqual(entry.points, 0)
        self.assertEqual(entry.rank, 1)

    def test_ranking_order_is_highest_points_first(self):
        rival = User.objects.create_user("lb-rival", password="pw-perf-1")
        ActivityEvent.objects.create(
            user=rival,
            event_type="like_received",
            points=99,
        )
        ActivityEvent.objects.create(
            user=self.user,
            event_type="like_received",
            points=5,
        )

        refresh_leaderboards()

        top = Leaderboard.objects.filter(period="overall").order_by("rank").first()
        self.assertEqual(top.user, rival)
        self.assertEqual(top.points, 99)

    def test_ties_are_broken_alphabetically_so_ranks_are_stable(self):
        User.objects.create_user("aaa-tied", password="pw-perf-1")
        User.objects.create_user("zzz-tied", password="pw-perf-1")

        refresh_leaderboards()
        first_pass = list(
            Leaderboard.objects.filter(period="overall")
            .order_by("rank")
            .values_list("user__username", flat=True)
        )

        refresh_leaderboards()
        second_pass = list(
            Leaderboard.objects.filter(period="overall")
            .order_by("rank")
            .values_list("user__username", flat=True)
        )

        self.assertEqual(first_pass, second_pass)
        self.assertEqual(first_pass, sorted(first_pass))

    def test_weekly_and_monthly_periods_exclude_older_events(self):
        old = ActivityEvent.objects.create(
            user=self.user,
            event_type="like_received",
            points=100,
        )
        # created_at is auto_now_add, so move it back explicitly.
        ActivityEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=90)
        )
        ActivityEvent.objects.create(
            user=self.user,
            event_type="like_received",
            points=7,
        )

        refresh_leaderboards()

        self.assertEqual(
            Leaderboard.objects.get(user=self.user, period="weekly").points,
            7,
        )
        self.assertEqual(
            Leaderboard.objects.get(user=self.user, period="overall").points,
            107,
        )

    def test_every_period_gets_an_entry_per_user(self):
        refresh_leaderboards()

        for period in ["overall", "weekly", "monthly"]:
            with self.subTest(period=period):
                self.assertTrue(
                    Leaderboard.objects.filter(
                        user=self.user,
                        period=period,
                    ).exists()
                )

    def test_repeated_refreshes_do_not_duplicate_entries(self):
        refresh_leaderboards()
        refresh_leaderboards()
        refresh_leaderboards()

        self.assertEqual(
            Leaderboard.objects.filter(user=self.user, period="overall").count(),
            1,
        )

    def test_the_management_command_runs(self):
        call_command("refresh_leaderboards", verbosity=0)

        self.assertTrue(Leaderboard.objects.exists())

    def test_an_unknown_period_falls_back_to_overall(self):
        response = self.client.get(reverse("leaderboard") + "?period=nonsense")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], "overall")


class QueryCountTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("perf-owner", password="pw-perf-1")
        self.category = Category.objects.get(name="Web Development")

    def make_projects(self, count, with_images=True):
        for index in range(count):
            project = Project.objects.create(
                owner=self.owner,
                category=self.category,
                title=f"Perf Project {index}",
                description="d",
                status="published",
                visibility="public",
            )
            if with_images:
                ProjectImage.objects.create(
                    project=project,
                    image=f"projects/perf-{index}.png",
                )

    def test_project_list_does_not_scale_queries_with_project_count(self):
        self.make_projects(12)

        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("project_list"))

        Project.objects.all().delete()
        self.make_projects(3)

        with CaptureQueriesContext(connection) as fewer:
            self.client.get(reverse("project_list"))

        self.assertEqual(
            len(few),
            len(fewer),
            "project_list query count still grows with the number of projects",
        )
        self.assertLess(len(few), 15, f"project_list used {len(few)} queries")

    def test_leaderboard_does_not_scale_queries_with_user_count(self):
        for index in range(15):
            user = User.objects.create_user(f"perf-lb-{index}", password="pw-perf-1")
            ActivityEvent.objects.create(
                user=user,
                event_type="like_received",
                points=index,
            )

        Leaderboard.objects.all().delete()

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            len(ctx),
            40,
            f"leaderboard used {len(ctx)} queries for {User.objects.count()} users",
        )

    def test_a_warm_leaderboard_does_not_recompute(self):
        for index in range(10):
            User.objects.create_user(f"warm-{index}", password="pw-perf-1")

        self.client.get(reverse("leaderboard"))

        with CaptureQueriesContext(connection) as warm:
            self.client.get(reverse("leaderboard"))

        self.assertLess(
            len(warm),
            12,
            f"a warm leaderboard still cost {len(warm)} queries; the staleness "
            f"check is not short-circuiting the refresh",
        )

    def test_home_does_not_scale_queries_with_project_count(self):
        self.make_projects(6, with_images=False)

        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("home"))

        Project.objects.all().delete()
        self.make_projects(1, with_images=False)

        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse("home"))

        self.assertEqual(len(many), len(one), "home still has an N+1")

    def test_my_bookmarks_does_not_scale_queries_with_bookmark_count(self):
        self.make_projects(8)
        self.client.force_login(self.owner)
        for project in Project.objects.all():
            Bookmark.objects.create(user=self.owner, project=project)

        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("my_bookmarks"))

        Bookmark.objects.exclude(
            pk=Bookmark.objects.first().pk,
        ).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse("my_bookmarks"))

        self.assertEqual(len(many), len(one), "my_bookmarks still has an N+1")

    def test_collection_detail_does_not_scale_queries_with_bookmark_count(self):
        self.make_projects(8)
        self.client.force_login(self.owner)
        collection = BookmarkCollection.objects.create(
            user=self.owner,
            name="Perf Collection",
        )
        for project in Project.objects.all():
            Bookmark.objects.create(
                user=self.owner,
                project=project,
                collection=collection,
            )

        url = reverse("collection_detail", args=[collection.pk])
        with CaptureQueriesContext(connection) as many:
            self.client.get(url)

        collection.bookmarks.exclude(
            pk=collection.bookmarks.first().pk,
        ).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(url)

        self.assertEqual(len(many), len(one), "collection_detail still has an N+1")

    def test_public_profile_does_not_scale_queries_with_project_count(self):
        self.make_projects(8)
        url = reverse("public_profile", args=[self.owner.username])

        # public_profile calls session.save(), so the very first anonymous
        # request pays for a session INSERT that later ones do not. Warm that
        # up so the comparison measures project scaling and nothing else.
        self.client.get(url)

        with CaptureQueriesContext(connection) as many:
            self.client.get(url)

        Project.objects.exclude(pk=Project.objects.first().pk).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(url)

        self.assertEqual(len(many), len(one), "public_profile still has an N+1")

    def test_analytics_does_not_scale_queries_with_project_count(self):
        self.make_projects(8, with_images=False)
        self.client.force_login(self.owner)

        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("analytics"))

        Project.objects.exclude(pk=Project.objects.first().pk).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse("analytics"))

        self.assertEqual(len(many), len(one), "analytics still has an N+1")


class ScaleRegressionTests(TestCase):
    """Bugs that only surfaced once the dataset was realistic."""

    def setUp(self):
        self.person = User.objects.create_user("scale-target", password="pw-perf-1")

    def follower_url(self):
        return reverse("followers_list", args=[self.person.username])

    def add_followers(self, count):
        from .models import Follow, Profile

        for index in range(count):
            follower = User.objects.create_user(
                f"scale-follower-{index}", password="pw-perf-1"
            )
            Profile.objects.filter(user=follower).update(display_name=f"Person {index}")
            Follow.objects.create(follower=follower, following=self.person)

    def test_followers_list_does_not_scale_queries_with_follower_count(self):
        """user_list.html reads person.profile per row; it must be joined in."""
        self.add_followers(12)
        self.client.get(self.follower_url())

        with CaptureQueriesContext(connection) as many:
            self.client.get(self.follower_url())

        from .models import Follow

        Follow.objects.exclude(pk=Follow.objects.first().pk).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.follower_url())

        self.assertEqual(
            len(many),
            len(one),
            f"followers_list still has an N+1 on Profile "
            f"({len(many)} queries for 12 followers vs {len(one)} for 1)",
        )

    def test_following_list_does_not_scale_queries_with_count(self):
        from .models import Follow, Profile

        for index in range(12):
            target = User.objects.create_user(
                f"scale-followed-{index}", password="pw-perf-1"
            )
            Profile.objects.filter(user=target).update(display_name=f"Target {index}")
            Follow.objects.create(follower=self.person, following=target)

        url = reverse("following_list", args=[self.person.username])
        self.client.get(url)

        with CaptureQueriesContext(connection) as many:
            self.client.get(url)

        Follow.objects.exclude(pk=Follow.objects.first().pk).delete()

        with CaptureQueriesContext(connection) as one:
            self.client.get(url)

        self.assertEqual(len(many), len(one), "following_list still has an N+1")

    def test_a_settled_leaderboard_stops_recomputing(self):
        """The staleness marker must advance even when no ranking changed.

        refresh_leaderboards() only wrote updated_at on rows it created or
        changed. Once the ranking settled, MAX(updated_at) froze, every request
        looked stale, and the throttle stopped working entirely.
        """
        for index in range(6):
            user = User.objects.create_user(f"settled-{index}", password="pw-perf-1")
            ActivityEvent.objects.create(
                user=user, event_type="like_received", points=index
            )

        # First pass populates the table.
        self.client.get(reverse("leaderboard"))
        # Second pass changes nothing at all.
        self.client.get(reverse("leaderboard"))

        with CaptureQueriesContext(connection) as third:
            self.client.get(reverse("leaderboard"))

        self.assertLess(
            len(third),
            12,
            f"a settled leaderboard still recomputes on every request "
            f"({len(third)} queries)",
        )

    def test_the_staleness_marker_advances_on_an_unchanged_refresh(self):
        from django.db.models import Max

        User.objects.create_user("marker-user", password="pw-perf-1")
        refresh_leaderboards()
        first = Leaderboard.objects.aggregate(m=Max("updated_at"))["m"]

        refresh_leaderboards()
        second = Leaderboard.objects.aggregate(m=Max("updated_at"))["m"]

        self.assertGreater(
            second, first, "updated_at did not advance on an unchanged refresh"
        )
