"""HTMX partial responses, and the no-JavaScript fallback they must preserve.

Every interaction enhanced with htmx has to keep working as a plain form POST,
so each behaviour is asserted twice: once with the HX-Request header and once
without it.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Bookmark, Category, Follow, Like, Project

HX = {"HTTP_HX_REQUEST": "true"}


class EngagementHtmxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hx-user", password="pw-hx-1")
        self.owner = User.objects.create_user("hx-owner", password="pw-hx-1")
        self.category = Category.objects.get(name="Other")
        self.project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="HTMX Project",
            description="d",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.user)

    # ---- like ----

    def test_liking_over_htmx_returns_only_the_panel(self):
        response = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="engagement-card"')
        self.assertNotContains(response, "<html")
        self.assertNotContains(response, "site-header")
        self.assertTrue(Like.objects.filter(user=self.user, project=self.project).exists())

    def test_the_returned_panel_reflects_the_new_state(self):
        liked = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )
        self.assertContains(liked, "Unlike project")
        self.assertContains(liked, 'aria-pressed="true"')

        unliked = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )
        self.assertContains(unliked, "Appreciate project")
        self.assertContains(unliked, 'aria-pressed="false"')

    def test_the_returned_panel_carries_the_updated_like_count(self):
        response = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )

        self.assertContains(response, '<span class="engagement-button__count">1</span>')

    def test_liking_without_htmx_still_redirects(self):
        response = self.client.post(reverse("toggle_like", args=[self.project.pk]))

        self.assertRedirects(
            response,
            reverse("project_detail", args=[self.project.pk]),
        )
        self.assertTrue(Like.objects.filter(user=self.user, project=self.project).exists())

    # ---- bookmark ----

    def test_bookmarking_over_htmx_returns_only_the_panel(self):
        response = self.client.post(
            reverse("toggle_bookmark", args=[self.project.pk]), **HX
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="engagement-card"')
        self.assertContains(response, "Remove from saved")
        self.assertTrue(
            Bookmark.objects.filter(user=self.user, project=self.project).exists()
        )

    def test_bookmarking_without_htmx_still_redirects(self):
        response = self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))

        self.assertRedirects(
            response,
            reverse("project_detail", args=[self.project.pk]),
        )

    def test_the_panel_shows_both_controls_in_their_current_state(self):
        self.client.post(reverse("toggle_like", args=[self.project.pk]), **HX)
        response = self.client.post(
            reverse("toggle_bookmark", args=[self.project.pk]), **HX
        )

        self.assertContains(response, "Unlike project")
        self.assertContains(response, "Remove from saved")

    # ---- follow ----

    def test_following_over_htmx_returns_only_the_button(self):
        response = self.client.post(
            reverse("toggle_follow", args=[self.owner.username]), **HX
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="follow-action"')
        self.assertContains(response, "Following")
        self.assertNotContains(response, "site-header")
        self.assertTrue(
            Follow.objects.filter(follower=self.user, following=self.owner).exists()
        )

    def test_unfollowing_over_htmx_returns_the_button_reset(self):
        Follow.objects.create(follower=self.user, following=self.owner)

        response = self.client.post(
            reverse("toggle_follow", args=[self.owner.username]), **HX
        )

        self.assertContains(response, 'aria-pressed="false"')
        self.assertFalse(
            Follow.objects.filter(follower=self.user, following=self.owner).exists()
        )

    def test_following_without_htmx_still_redirects(self):
        response = self.client.post(
            reverse("toggle_follow", args=[self.owner.username])
        )

        self.assertRedirects(
            response,
            reverse("public_profile", args=[self.owner.username]),
        )

    # ---- messages stay quiet for htmx ----

    def test_htmx_toggles_do_not_queue_a_flash_message(self):
        self.client.post(reverse("toggle_like", args=[self.project.pk]), **HX)

        page = self.client.get(reverse("home"))

        self.assertEqual(
            [str(m) for m in page.context["messages"]],
            [],
            "an htmx toggle left an orphaned message to appear on a later page",
        )

    def test_non_htmx_toggles_still_queue_a_flash_message(self):
        response = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), follow=True
        )

        self.assertIn(
            "You appreciated 'HTMX Project'.",
            [str(m) for m in response.context["messages"]],
        )

    # ---- guards preserved ----

    def test_htmx_requests_still_require_authentication(self):
        self.client.logout()

        response = self.client.post(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Like.objects.exists())

    def test_htmx_requests_still_respect_project_visibility(self):
        private = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title="Private",
            description="d",
            status="published",
            visibility="private",
        )

        response = self.client.post(
            reverse("toggle_like", args=[private.pk]), **HX
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Like.objects.filter(project=private).exists())

    def test_htmx_requests_are_still_post_only(self):
        response = self.client.get(
            reverse("toggle_like", args=[self.project.pk]), **HX
        )

        self.assertEqual(response.status_code, 405)


class ProgressiveEnhancementTests(TestCase):
    """The page must work as plain HTML before htmx loads."""

    def setUp(self):
        self.user = User.objects.create_user("pe-user", password="pw-hx-1")
        self.owner = User.objects.create_user("pe-owner", password="pw-hx-1")
        self.project = Project.objects.create(
            owner=self.owner,
            category=Category.objects.get(name="Other"),
            title="Fallback Project",
            description="d",
            status="published",
            visibility="public",
        )

    def test_the_forms_keep_method_and_action_for_the_no_js_path(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("project_detail", args=[self.project.pk])
        )

        self.assertContains(
            response,
            f'action="{reverse("toggle_like", args=[self.project.pk])}"',
        )
        self.assertContains(response, 'method="post"')

    def test_the_forms_carry_a_csrf_token(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("project_detail", args=[self.project.pk])
        )

        self.assertContains(response, "csrfmiddlewaretoken")

    def test_htmx_is_served_from_local_static_not_a_cdn(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "core/js/htmx.min.js")
        self.assertNotContains(response, "unpkg.com")
        self.assertNotContains(response, "cdn.jsdelivr.net")

    def test_anonymous_visitors_get_a_login_link_that_returns_them(self):
        response = self.client.get(
            reverse("project_detail", args=[self.project.pk])
        )

        self.assertContains(response, "Log in to engage")
        self.assertContains(response, "next=")
