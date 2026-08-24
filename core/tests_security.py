"""Visibility and authorisation, exercised against seeded-style data.

The two classes at the bottom cover defects that were open during the dataset
phase and are now fixed. They were written first as @expectedFailure; the
markers came off once the behaviour was corrected, and the assertions stayed.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Bookmark,
    BookmarkCollection,
    Category,
    Comment,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Project,
)


class VisibilityEnforcementTests(TestCase):
    """Anonymous and third-party access to non-public work."""

    def setUp(self):
        self.owner = User.objects.create_user("vis-owner", password="pw-vis-1")
        self.stranger = User.objects.create_user("vis-stranger", password="pw-vis-1")
        self.category = Category.objects.get(name="Web Development")

        self.public = self.make("Public Work", "published", "public")
        self.private_published = self.make("Private Published", "published", "private")
        self.draft_public = self.make("Draft Public", "draft", "public")
        self.draft_private = self.make("Draft Private", "draft", "private")

        self.hidden = [self.private_published, self.draft_public, self.draft_private]

    def make(self, title, status, visibility):
        # A distinctive description: assertNotContains on a one-letter string
        # matches any HTML page, which makes the assertion meaningless.
        slug = title.lower().replace(" ", "-")
        return Project.objects.create(
            owner=self.owner,
            category=self.category,
            title=title,
            description=f"body-marker-{slug}-unique-content",
            status=status,
            visibility=visibility,
        )

    # ---- anonymous ----

    def test_anonymous_sees_only_public_published_work_in_discovery(self):
        response = self.client.get(reverse("project_list"))

        self.assertContains(response, "Public Work")
        for project in self.hidden:
            self.assertNotContains(response, project.title)

    def test_anonymous_cannot_open_hidden_projects_by_direct_url(self):
        for project in self.hidden:
            with self.subTest(project=project.title):
                response = self.client.get(
                    reverse("project_detail", args=[project.pk])
                )
                self.assertEqual(response.status_code, 404)

    def test_anonymous_sees_only_public_work_on_a_profile(self):
        response = self.client.get(
            reverse("public_profile", args=[self.owner.username])
        )

        self.assertContains(response, "Public Work")
        for project in self.hidden:
            self.assertNotContains(response, project.title)

    def test_anonymous_sees_only_public_work_on_the_landing_page(self):
        response = self.client.get(reverse("home"))

        for project in self.hidden:
            self.assertNotContains(response, project.title)

    def test_search_cannot_surface_hidden_work(self):
        # Assert on the result set, not the HTML: the search box echoes the
        # submitted query back into its own input, so the title legitimately
        # appears in the markup even when nothing matched.
        for project in self.hidden:
            with self.subTest(project=project.title):
                response = self.client.get(
                    reverse("project_list") + f"?q={project.title}"
                )
                self.assertNotIn(project, list(response.context["projects"]))
                self.assertNotContains(response, project.description)

    def test_category_filter_cannot_surface_hidden_work(self):
        response = self.client.get(
            reverse("project_list") + "?category=Web Development"
        )

        results = list(response.context["projects"])
        for project in self.hidden:
            self.assertNotIn(project, results)

    # ---- authenticated third party ----

    def test_a_stranger_cannot_open_hidden_projects(self):
        self.client.force_login(self.stranger)

        for project in self.hidden:
            with self.subTest(project=project.title):
                response = self.client.get(
                    reverse("project_detail", args=[project.pk])
                )
                self.assertEqual(response.status_code, 404)

    def test_a_stranger_cannot_engage_with_hidden_projects(self):
        self.client.force_login(self.stranger)

        for project in self.hidden:
            for route in ["toggle_like", "toggle_bookmark", "add_comment"]:
                with self.subTest(project=project.title, route=route):
                    response = self.client.post(
                        reverse(route, args=[project.pk]),
                        {"content": "x"} if route == "add_comment" else {},
                    )
                    self.assertEqual(response.status_code, 404)

    def test_the_owner_can_still_reach_their_own_hidden_work(self):
        self.client.force_login(self.owner)

        for project in self.hidden:
            with self.subTest(project=project.title):
                response = self.client.get(
                    reverse("project_detail", args=[project.pk])
                )
                self.assertEqual(response.status_code, 200)

    # ---- ownership ----

    def test_a_stranger_cannot_edit_or_delete_another_users_project(self):
        self.client.force_login(self.stranger)

        edit = self.client.post(
            reverse("edit_project", args=[self.public.pk]),
            {
                "title": "Hijacked",
                "description": "d",
                "category": self.category.pk,
                "visibility": "public",
                "status": "published",
                "stage": "prototype",
            },
        )
        delete = self.client.post(reverse("delete_project", args=[self.public.pk]))

        self.public.refresh_from_db()
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(delete.status_code, 404)
        self.assertEqual(self.public.title, "Public Work")
        self.assertTrue(Project.objects.filter(pk=self.public.pk).exists())

    def test_id_enumeration_does_not_reveal_object_existence(self):
        """A hidden project and a missing project must be indistinguishable."""
        self.client.force_login(self.stranger)

        missing = self.client.get(reverse("project_detail", args=[99999999]))
        hidden = self.client.get(
            reverse("project_detail", args=[self.private_published.pk])
        )

        self.assertEqual(missing.status_code, hidden.status_code)

    def test_a_stranger_cannot_open_another_users_collection(self):
        collection = BookmarkCollection.objects.create(
            user=self.owner, name="Private Shelf"
        )
        self.client.force_login(self.stranger)

        response = self.client.get(
            reverse("collection_detail", args=[collection.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_a_stranger_cannot_refile_another_users_bookmark(self):
        bookmark = Bookmark.objects.create(user=self.owner, project=self.public)
        mine = BookmarkCollection.objects.create(
            user=self.stranger, name="Mine"
        )
        self.client.force_login(self.stranger)

        response = self.client.post(
            reverse("add_bookmark_to_collection", args=[bookmark.pk]),
            {"collection": mine.pk},
        )

        bookmark.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(bookmark.collection)

    def test_a_stranger_cannot_edit_or_delete_another_users_comment(self):
        comment = Comment.objects.create(
            user=self.owner, project=self.public, content="Mine"
        )
        self.client.force_login(self.stranger)

        edit = self.client.post(
            reverse("edit_comment", args=[comment.pk]), {"content": "Hijacked"}
        )
        self.client.post(reverse("delete_comment", args=[comment.pk]))

        comment.refresh_from_db()
        self.assertEqual(edit.status_code, 404)
        self.assertEqual(comment.content, "Mine")

    # ---- staff ----

    def test_a_normal_user_cannot_reach_staff_pages(self):
        self.client.force_login(self.stranger)

        for name in ["manage_contests", "create_contest"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)

    def test_a_normal_user_cannot_review_a_submission(self):
        contest = Contest.objects.create(
            title="Judged", description="d", rules="r",
            registration_deadline=timezone.now() + timedelta(days=3),
            submission_deadline=timezone.now() + timedelta(days=9),
            status="active",
        )
        participant = ContestParticipant.objects.create(
            contest=contest, user=self.owner
        )
        submission = ContestSubmission.objects.create(
            contest=contest,
            participant=participant,
            project=self.public,
            submission_title="Entry",
        )
        self.client.force_login(self.stranger)

        response = self.client.post(
            reverse("review_submission", args=[submission.pk]),
            {"status": "winner", "score": "99"},
        )

        submission.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(submission.status, "submitted")


class ContestDraftVisibilityTests(TestCase):
    """P1, fixed: a draft contest used to be readable by direct URL.

    `contests` excluded drafts from the listing, but `contest_detail` did no
    status check, so the brief, rules and prize information of an unpublished
    contest were served to anonymous visitors.

    Contests have no owner field - they are staff-managed - so the rule is that
    a draft is visible to staff only, enforced by get_accessible_contest(),
    which mirrors get_accessible_project() and returns 404 rather than 403 so
    the response does not confirm the contest exists.
    """

    def setUp(self):
        now = timezone.now()
        self.draft = Contest.objects.create(
            title="Unannounced Sponsor Contest",
            description="Not public yet.",
            rules="Confidential rules.",
            prize_information="Confidential prize details.",
            registration_deadline=now + timedelta(days=14),
            submission_deadline=now + timedelta(days=30),
            status="draft",
        )

    def test_a_draft_contest_is_excluded_from_the_listing(self):
        """This part already works."""
        response = self.client.get(reverse("contests"))

        self.assertNotContains(response, "Unannounced Sponsor Contest")

    def test_a_draft_contest_is_not_readable_by_direct_url(self):
        response = self.client.get(
            reverse("contest_detail", args=[self.draft.pk])
        )

        self.assertEqual(
            response.status_code,
            404,
            "draft contests are still publicly readable by direct URL",
        )

    def test_a_draft_contest_does_not_leak_its_rules_and_prizes(self):
        response = self.client.get(
            reverse("contest_detail", args=[self.draft.pk])
        )

        # assertNotContains asserts the status code too, and the correct
        # response here is 404 rather than a 200 with the content stripped.
        self.assertNotContains(response, "Confidential rules.", status_code=404)
        self.assertNotContains(
            response, "Confidential prize details.", status_code=404
        )


class PrivateProjectSubmissionTests(TestCase):
    """P1, fixed: a private or draft project could be entered into a contest.

    `ContestSubmissionForm` filtered the project field to `owner=user` but not
    by status or visibility, so work the owner deliberately kept private could
    be entered into a public competition, judged, scored and awarded a
    certificate - and winning sets featured=True on it.

    This was a data-integrity defect rather than a content leak: the contest
    page renders submission_title, not the project title, and does not link to
    the project, which still 404s. The submitter's username and the entry's
    status did become public.

    The queryset is now restricted to published + public work. That both keeps
    private projects out of the dropdown and makes ModelChoiceField reject a
    forged project id on POST, before any ContestSubmission is created. The
    project's own visibility is never modified.
    """

    def setUp(self):
        now = timezone.now()
        self.user = User.objects.create_user("entrant", password="pw-vis-1")
        self.category = Category.objects.get(name="Other")
        self.contest = Contest.objects.create(
            title="Public Contest",
            description="d",
            rules="r",
            registration_deadline=now + timedelta(days=5),
            submission_deadline=now + timedelta(days=12),
            status="active",
        )
        self.private = Project.objects.create(
            owner=self.user,
            category=self.category,
            title="Confidential Prototype",
            description="Deliberately kept private.",
            status="draft",
            visibility="private",
        )
        self.client.force_login(self.user)
        self.client.post(reverse("contest_register", args=[self.contest.pk]))

    def submit(self):
        return self.client.post(
            reverse("contest_submit", args=[self.contest.pk]),
            {
                "project": self.private.pk,
                "submission_title": "My entry",
                "description": "x",
            },
        )

    def test_the_private_project_itself_stays_unreachable(self):
        """This part already works: the project detail page still 404s."""
        self.submit()
        self.client.logout()

        response = self.client.get(
            reverse("project_detail", args=[self.private.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_the_contest_page_does_not_render_the_private_project_title(self):
        """Also already true: the template shows submission_title instead."""
        self.submit()
        self.client.logout()

        response = self.client.get(
            reverse("contest_detail", args=[self.contest.pk])
        )

        self.assertNotContains(response, "Confidential Prototype")

    def test_a_private_project_cannot_be_entered_into_a_contest(self):
        self.submit()

        self.assertFalse(
            ContestSubmission.objects.filter(project=self.private).exists(),
            "a private, draft project was accepted into a public contest",
        )

    def test_the_submission_form_only_offers_public_published_projects(self):
        response = self.client.get(
            reverse("contest_submit", args=[self.contest.pk])
        )

        offered = response.context["form"].fields["project"].queryset
        self.assertNotIn(
            self.private,
            offered,
            "the submission form offers projects the owner kept private",
        )
