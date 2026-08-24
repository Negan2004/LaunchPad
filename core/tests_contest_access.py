"""Access matrix for contests and contest submissions.

Companion to the two fixed P1 defects in tests_security.py. These cover the
surrounding cases: every contest status against every viewer role, and every
project state against submission eligibility.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Category,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Project,
)


class ContestDraftAccessMatrixTests(TestCase):
    """Who may see a contest, by contest status and viewer role."""

    def setUp(self):
        now = timezone.now()
        self.member = User.objects.create_user("matrix-member", password="pw-vis-1")
        self.staff = User.objects.create_user(
            "matrix-staff", password="pw-vis-1", is_staff=True
        )
        self.admin = User.objects.create_superuser(
            "matrix-admin", "admin@matrix.example", "pw-vis-1"
        )
        self.contests = {}
        for status in ["draft", "upcoming", "active", "completed", "cancelled"]:
            self.contests[status] = Contest.objects.create(
                title=f"{status.title()} Contest",
                description="d",
                rules="r",
                registration_deadline=now + timedelta(days=5),
                submission_deadline=now + timedelta(days=12),
                status=status,
            )

    def get(self, status, user=None):
        if user:
            self.client.force_login(user)
        else:
            self.client.logout()
        return self.client.get(
            reverse("contest_detail", args=[self.contests[status].pk])
        )

    # ---- draft ----

    def test_anonymous_cannot_open_a_draft_contest(self):
        self.assertEqual(self.get("draft").status_code, 404)

    def test_a_normal_authenticated_user_cannot_open_a_draft_contest(self):
        self.assertEqual(self.get("draft", self.member).status_code, 404)

    def test_staff_can_still_preview_a_draft_contest(self):
        response = self.get("draft", self.staff)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft Contest")

    def test_a_superuser_can_preview_a_draft_contest(self):
        self.assertEqual(self.get("draft", self.admin).status_code, 200)

    # ---- every other status stays public ----

    def test_non_draft_contests_remain_publicly_readable(self):
        for status in ["upcoming", "active", "completed", "cancelled"]:
            with self.subTest(status=status):
                self.assertEqual(self.get(status).status_code, 200)

    def test_non_draft_contests_remain_readable_by_members(self):
        for status in ["upcoming", "active", "completed", "cancelled"]:
            with self.subTest(status=status):
                self.assertEqual(self.get(status, self.member).status_code, 200)

    # ---- the listing was already correct; keep it that way ----

    def test_the_listing_shows_every_non_draft_contest(self):
        self.client.logout()
        response = self.client.get(reverse("contests"))

        self.assertNotContains(response, "Draft Contest")
        for status in ["upcoming", "active", "completed", "cancelled"]:
            self.assertContains(response, f"{status.title()} Contest")

    # ---- draft contests are not joinable or submittable ----

    def test_a_draft_contest_cannot_be_registered_for(self):
        self.client.force_login(self.member)

        response = self.client.post(
            reverse("contest_register", args=[self.contests["draft"].pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ContestParticipant.objects.filter(
                contest=self.contests["draft"]
            ).exists()
        )

    def test_a_draft_contest_submission_page_is_not_reachable(self):
        self.client.force_login(self.member)

        response = self.client.get(
            reverse("contest_submit", args=[self.contests["draft"].pk])
        )

        self.assertEqual(response.status_code, 404)

    # ---- staff management must keep working ----

    def test_staff_management_of_drafts_still_works(self):
        self.client.force_login(self.staff)
        draft = self.contests["draft"]

        self.assertEqual(self.client.get(reverse("manage_contests")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("edit_contest", args=[draft.pk])).status_code,
            200,
        )

        response = self.client.post(
            reverse("edit_contest", args=[draft.pk]),
            {
                "title": "Draft Contest",
                "description": "d",
                "rules": "r",
                "registration_deadline": "2030-01-01T00:00",
                "submission_deadline": "2030-02-01T00:00",
                "prize_information": "",
                "status": "upcoming",
            },
        )

        draft.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            draft.status,
            "upcoming",
            "staff must still be able to publish a draft contest",
        )

    def test_a_published_draft_becomes_publicly_visible(self):
        draft = self.contests["draft"]
        draft.status = "active"
        draft.save(update_fields=["status"])

        self.client.logout()

        self.assertEqual(
            self.client.get(reverse("contest_detail", args=[draft.pk])).status_code,
            200,
        )

    def test_a_missing_contest_and_a_draft_contest_look_identical(self):
        self.client.logout()
        missing = self.client.get(reverse("contest_detail", args=[99999999]))
        draft = self.get("draft")

        self.assertEqual(missing.status_code, draft.status_code)


class ContestSubmissionEligibilityTests(TestCase):
    """Which projects may be entered into a contest."""

    def setUp(self):
        now = timezone.now()
        self.owner = User.objects.create_user("elig-owner", password="pw-vis-1")
        self.other = User.objects.create_user("elig-other", password="pw-vis-1")
        self.category = Category.objects.get(name="Other")
        self.contest = Contest.objects.create(
            title="Eligibility Contest",
            description="d",
            rules="r",
            registration_deadline=now + timedelta(days=5),
            submission_deadline=now + timedelta(days=12),
            status="active",
        )
        self.projects = {
            "public": self.make("Public Entry", "published", "public"),
            "private_published": self.make(
                "Private Published", "published", "private"
            ),
            "draft_public": self.make("Draft Public", "draft", "public"),
            "draft_private": self.make("Draft Private", "draft", "private"),
        }
        self.foreign = Project.objects.create(
            owner=self.other,
            category=self.category,
            title="Another Student's Work",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.owner)
        self.client.post(reverse("contest_register", args=[self.contest.pk]))

    def make(self, title, status, visibility):
        return Project.objects.create(
            owner=self.owner,
            category=self.category,
            title=title,
            description="d",
            status=status,
            visibility=visibility,
        )

    def submit(self, project):
        return self.client.post(
            reverse("contest_submit", args=[self.contest.pk]),
            {
                "project": project.pk,
                "submission_title": f"Entry for {project.title}",
                "description": "x",
            },
        )

    # ---- allowed ----

    def test_a_public_published_project_can_be_submitted(self):
        response = self.submit(self.projects["public"])

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ContestSubmission.objects.filter(
                project=self.projects["public"]
            ).exists()
        )

    def test_an_accepted_submission_can_be_updated(self):
        self.submit(self.projects["public"])
        second = self.make("Second Public", "published", "public")

        self.submit(second)

        submissions = ContestSubmission.objects.filter(contest=self.contest)
        self.assertEqual(submissions.count(), 1, "updating must not duplicate")
        self.assertEqual(submissions.first().project, second)

    # ---- rejected ----

    def test_a_private_published_project_is_rejected(self):
        response = self.submit(self.projects["private_published"])

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ContestSubmission.objects.filter(
                project=self.projects["private_published"]
            ).exists()
        )
        self.assertIn("project", response.context["form"].errors)

    def test_a_public_draft_project_is_rejected(self):
        """Unpublished work is not eligible, matching the site-wide rule."""
        self.submit(self.projects["draft_public"])

        self.assertFalse(
            ContestSubmission.objects.filter(
                project=self.projects["draft_public"]
            ).exists()
        )

    def test_a_private_draft_project_is_rejected(self):
        self.submit(self.projects["draft_private"])

        self.assertFalse(
            ContestSubmission.objects.filter(
                project=self.projects["draft_private"]
            ).exists()
        )

    def test_another_users_project_is_rejected(self):
        self.submit(self.foreign)

        self.assertFalse(
            ContestSubmission.objects.filter(project=self.foreign).exists()
        )

    def test_a_nonexistent_project_id_is_rejected(self):
        response = self.client.post(
            reverse("contest_submit", args=[self.contest.pk]),
            {"project": 99999999, "submission_title": "Ghost", "description": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContestSubmission.objects.exists())

    # ---- the form itself ----

    def test_the_dropdown_offers_only_eligible_projects(self):
        response = self.client.get(
            reverse("contest_submit", args=[self.contest.pk])
        )

        offered = list(response.context["form"].fields["project"].queryset)
        self.assertEqual(offered, [self.projects["public"]])

    # ---- the project itself must never be altered ----

    def test_a_rejected_submission_does_not_change_project_visibility(self):
        project = self.projects["private_published"]

        self.submit(project)

        project.refresh_from_db()
        self.assertEqual(project.visibility, "private")
        self.assertEqual(project.status, "published")

    def test_an_accepted_submission_does_not_change_project_visibility(self):
        project = self.projects["public"]

        self.submit(project)

        project.refresh_from_db()
        self.assertEqual(project.visibility, "public")
        self.assertEqual(project.status, "published")

    def test_a_private_project_stays_unreachable_after_a_rejected_submission(self):
        project = self.projects["private_published"]
        self.submit(project)
        self.client.logout()

        response = self.client.get(reverse("project_detail", args=[project.pk]))

        self.assertEqual(response.status_code, 404)
