"""Regression tests for the five P0 defects found in the backend audit.

Each class here pins one fix. They are deliberately written to fail against the
pre-fix code so a future change that reintroduces the defect is caught.
"""

import shutil
import tempfile
from io import BytesIO

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.models import BigAutoField
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import (
    Bookmark,
    BookmarkCollection,
    Category,
    Comment,
    Like,
    Project,
    ProjectView,
)


def build_image(name="shot.png"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


# ---------------------------------------------------------------------------
# P0 #1 - project creation was impossible: Category is a required PROTECT FK
#         and the table was empty, with no view or URL that creates one.
# ---------------------------------------------------------------------------


class CategoryLifecycleTests(TestCase):
    """Categories are an admin-managed taxonomy seeded by migration 0009."""

    def test_migration_seeds_a_usable_starting_taxonomy(self):
        self.assertGreaterEqual(
            Category.objects.count(),
            5,
            "migration 0009 should seed a starting category taxonomy",
        )
        self.assertTrue(Category.objects.filter(name="Web Development").exists())
        self.assertTrue(Category.objects.filter(name="Other").exists())

    def test_seeded_categories_carry_descriptions(self):
        for category in Category.objects.all():
            self.assertTrue(
                category.description.strip(),
                f"seeded category {category.name!r} should describe itself",
            )

    def test_category_names_are_unique(self):
        names = list(Category.objects.values_list("name", flat=True))
        self.assertEqual(len(names), len(set(names)))

    def test_project_category_is_still_required(self):
        """The fix must not have quietly loosened the schema."""
        field = Project._meta.get_field("category")
        self.assertFalse(field.null, "category must stay required")
        self.assertFalse(field.blank, "category must stay required")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProjectCreationTests(TestCase):
    """The end-to-end journey that was blocked before the seed migration."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner = User.objects.create_user("p0-owner", password="pw-p0-strong-1")
        self.other = User.objects.create_user("p0-other", password="pw-p0-strong-1")
        self.category = Category.objects.get(name="Web Development")

    def payload(self, **overrides):
        data = {
            "title": "Campus Routing App",
            "short_description": "Finds the fastest walk between lecture halls.",
            "description": "A longer description of the project.",
            "category": self.category.pk,
            "technologies": "Django, PostgreSQL",
            "tags": "campus, maps",
            "demo_url": "",
            "repository_url": "",
            "documentation_url": "",
            "visibility": "public",
            "status": "published",
            "stage": "prototype",
        }
        data.update(overrides)
        return data

    def test_a_student_can_create_a_project_using_a_seeded_category(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse("create_project"), self.payload())

        project = Project.objects.get(title="Campus Routing App")
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertEqual(project.owner, self.owner)
        self.assertEqual(project.category, self.category)

    def test_the_create_form_offers_every_seeded_category(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("create_project"))

        self.assertEqual(response.status_code, 200)
        choices = response.context["form"].fields["category"].queryset
        self.assertEqual(choices.count(), Category.objects.count())
        self.assertGreaterEqual(choices.count(), 5)

    def test_creation_with_images_attaches_them(self):
        self.client.force_login(self.owner)
        data = self.payload(title="With Images")
        data["images"] = [build_image("one.png"), build_image("two.png")]

        self.client.post(reverse("create_project"), data)

        project = Project.objects.get(title="With Images")
        self.assertEqual(project.images.count(), 2)

    def test_a_nonexistent_category_is_rejected(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("create_project"),
            self.payload(category=999999),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(title="Campus Routing App").exists())
        self.assertIn("category", response.context["form"].errors)

    def test_a_missing_category_is_rejected(self):
        self.client.force_login(self.owner)
        data = self.payload()
        del data["category"]

        response = self.client.post(reverse("create_project"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertIn("category", response.context["form"].errors)

    def test_anonymous_users_cannot_create_projects(self):
        response = self.client.post(reverse("create_project"), self.payload())

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('create_project')}",
        )
        self.assertFalse(Project.objects.exists())

    def test_the_owner_can_edit_a_project(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())
        project = Project.objects.get(title="Campus Routing App")

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(title="Campus Routing App v2"),
        )

        project.refresh_from_db()
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertEqual(project.title, "Campus Routing App v2")

    def test_a_project_can_be_moved_to_another_category(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())
        project = Project.objects.get(title="Campus Routing App")
        destination = Category.objects.get(name="Machine Learning & AI")

        self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(category=destination.pk),
        )

        project.refresh_from_db()
        self.assertEqual(project.category, destination)

    def test_a_non_owner_cannot_edit_a_project(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())
        project = Project.objects.get(title="Campus Routing App")
        self.client.force_login(self.other)

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(title="Hijacked"),
        )

        project.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(project.title, "Campus Routing App")

    def test_the_owner_can_delete_a_project(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())
        project = Project.objects.get(title="Campus Routing App")

        response = self.client.post(reverse("delete_project", args=[project.pk]))

        self.assertRedirects(response, reverse("project_list"))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_a_non_owner_cannot_delete_a_project(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())
        project = Project.objects.get(title="Campus Routing App")
        self.client.force_login(self.other)

        response = self.client.post(reverse("delete_project", args=[project.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Project.objects.filter(pk=project.pk).exists())

    def test_a_category_with_projects_is_protected_from_deletion(self):
        """PROTECT is deliberate - deleting a used category must not orphan work."""
        from django.db.models import ProtectedError

        self.client.force_login(self.owner)
        self.client.post(reverse("create_project"), self.payload())

        with self.assertRaises(ProtectedError):
            self.category.delete()


# ---------------------------------------------------------------------------
# P0 #2 - add_bookmark_to_collection raised AttributeError (500) whenever the
#         optional collection field was submitted empty.
# ---------------------------------------------------------------------------


class BookmarkCollectionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("bm-owner", password="pw-p0-strong-1")
        self.other = User.objects.create_user("bm-other", password="pw-p0-strong-1")
        self.category = Category.objects.get(name="Other")
        self.project = Project.objects.create(
            owner=self.other,
            category=self.category,
            title="Bookmarkable",
            description="A public project.",
            status="published",
            visibility="public",
        )
        self.client.force_login(self.owner)
        self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))
        self.bookmark = Bookmark.objects.get(user=self.owner, project=self.project)
        self.collection = BookmarkCollection.objects.create(
            user=self.owner,
            name="Final Year Ideas",
        )

    def url(self, bookmark=None):
        return reverse(
            "add_bookmark_to_collection",
            args=[(bookmark or self.bookmark).pk],
        )

    def test_assigning_to_a_valid_collection_redirects_to_that_collection(self):
        response = self.client.post(self.url(), {"collection": self.collection.pk})

        self.bookmark.refresh_from_db()
        self.assertEqual(self.bookmark.collection, self.collection)
        self.assertRedirects(
            response,
            reverse("collection_detail", args=[self.collection.pk]),
        )

    def test_clearing_the_collection_does_not_raise_a_500(self):
        """The exact P0 regression: an empty collection field used to crash."""
        self.bookmark.collection = self.collection
        self.bookmark.save(update_fields=["collection"])

        response = self.client.post(self.url(), {"collection": ""})

        self.bookmark.refresh_from_db()
        self.assertIsNone(self.bookmark.collection)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("my_bookmarks"))

    def test_submitting_an_unassigned_bookmark_with_no_collection_is_handled(self):
        self.assertIsNone(self.bookmark.collection)

        response = self.client.post(self.url(), {"collection": ""})

        self.assertRedirects(response, reverse("my_bookmarks"))
        self.bookmark.refresh_from_db()
        self.assertIsNone(self.bookmark.collection)

    def test_deleting_a_collection_leaves_the_bookmark_intact(self):
        """collection is SET_NULL, so the bookmark must survive."""
        self.bookmark.collection = self.collection
        self.bookmark.save(update_fields=["collection"])

        self.collection.delete()

        self.bookmark.refresh_from_db()
        self.assertIsNone(self.bookmark.collection)
        self.assertTrue(Bookmark.objects.filter(pk=self.bookmark.pk).exists())

    def test_the_form_page_still_renders_after_its_collection_was_deleted(self):
        self.bookmark.collection = self.collection
        self.bookmark.save(update_fields=["collection"])
        self.collection.delete()

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)

    def test_a_nonexistent_collection_is_rejected(self):
        response = self.client.post(self.url(), {"collection": 999999})

        self.assertEqual(response.status_code, 200)
        self.bookmark.refresh_from_db()
        self.assertIsNone(self.bookmark.collection)

    def test_another_users_collection_cannot_be_targeted(self):
        foreign = BookmarkCollection.objects.create(
            user=self.other,
            name="Not Yours",
        )

        response = self.client.post(self.url(), {"collection": foreign.pk})

        self.assertEqual(response.status_code, 200)
        self.bookmark.refresh_from_db()
        self.assertIsNone(self.bookmark.collection)

    def test_another_users_bookmark_cannot_be_edited(self):
        foreign_bookmark = Bookmark.objects.create(
            user=self.other,
            project=self.project,
        )

        response = self.client.post(
            self.url(foreign_bookmark),
            {"collection": self.collection.pk},
        )

        self.assertEqual(response.status_code, 404)
        foreign_bookmark.refresh_from_db()
        self.assertIsNone(foreign_bookmark.collection)

    def test_anonymous_users_are_redirected_to_login(self):
        self.client.logout()

        response = self.client.post(self.url(), {"collection": self.collection.pk})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_bookmarking_twice_does_not_create_a_duplicate(self):
        """Bookmark has UniqueConstraint(user, project); toggling must be safe."""
        self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))
        self.assertFalse(
            Bookmark.objects.filter(user=self.owner, project=self.project).exists()
        )

        self.client.post(reverse("toggle_bookmark", args=[self.project.pk]))
        self.assertEqual(
            Bookmark.objects.filter(user=self.owner, project=self.project).count(),
            1,
        )


# ---------------------------------------------------------------------------
# P0 #3 - DEFAULT_AUTO_FIELD was missing, so makemigrations wanted to shrink
#         all 22 bigint primary keys to 32-bit integers.
# ---------------------------------------------------------------------------


class PrimaryKeyConfigurationTests(TestCase):
    def test_default_auto_field_is_bigautofield(self):
        self.assertEqual(
            settings.DEFAULT_AUTO_FIELD,
            "django.db.models.BigAutoField",
        )

    def test_every_core_model_resolves_to_a_bigautofield_primary_key(self):
        for model in apps.get_app_config("core").get_models():
            with self.subTest(model=model.__name__):
                self.assertIsInstance(
                    model._meta.pk,
                    BigAutoField,
                    f"{model.__name__} must keep a 64-bit primary key",
                )

    def test_there_are_no_pending_model_changes(self):
        """makemigrations --check must stay clean.

        This is the guard against the destructive 0009 the audit found armed.
        """
        try:
            call_command("makemigrations", "--check", "--dry-run", verbosity=0)
        except SystemExit:
            self.fail(
                "makemigrations --check reported pending changes; the model "
                "state has drifted from the migrations again"
            )


# ---------------------------------------------------------------------------
# P0 #4 - analytics annotated three multi-valued relations in one queryset, so
#         join fan-out multiplied every count.
# ---------------------------------------------------------------------------


class AnalyticsCountTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("an-owner", password="pw-p0-strong-1")
        self.category = Category.objects.get(name="Data Science")
        self.client.force_login(self.owner)

    def make_project(self, title, likes=0, comments=0, views=0):
        project = Project.objects.create(
            owner=self.owner,
            category=self.category,
            title=title,
            description="d",
            status="published",
            visibility="public",
        )
        for index in range(likes):
            liker = User.objects.create_user(
                f"{title.lower().replace(' ', '')}-liker{index}",
                password="pw-p0-strong-1",
            )
            Like.objects.create(user=liker, project=project)
        for index in range(comments):
            Comment.objects.create(
                user=self.owner,
                project=project,
                content=f"comment {index}",
            )
        for _ in range(views):
            ProjectView.objects.create(project=project, visitor=self.owner)
        return project

    def totals_for(self, project):
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.context["projects"] if item.pk == project.pk
        )
        return row.likes_total, row.comments_total, row.views_total

    def test_three_likes_and_two_comments_are_not_inflated(self):
        """The exact case from the audit: reported 6 and 6, actual 3 and 2."""
        project = self.make_project("Three Two", likes=3, comments=2)

        likes, comments, _ = self.totals_for(project)

        self.assertEqual(likes, 3)
        self.assertEqual(comments, 2)

    def test_a_project_with_no_engagement_reports_zero(self):
        project = self.make_project("Empty")

        self.assertEqual(self.totals_for(project), (0, 0, 0))

    def test_one_like_and_many_comments(self):
        project = self.make_project("One Many", likes=1, comments=7)

        likes, comments, _ = self.totals_for(project)

        self.assertEqual(likes, 1)
        self.assertEqual(comments, 7)

    def test_many_likes_and_one_comment(self):
        project = self.make_project("Many One", likes=6, comments=1)

        likes, comments, _ = self.totals_for(project)

        self.assertEqual(likes, 6)
        self.assertEqual(comments, 1)

    def test_all_three_relations_populated_at_once(self):
        project = self.make_project("All Three", likes=4, comments=3, views=5)

        self.assertEqual(self.totals_for(project), (4, 3, 5))

    def test_totals_match_the_database_for_several_projects_at_once(self):
        first = self.make_project("First", likes=3, comments=2, views=4)
        second = self.make_project("Second", likes=1, comments=5, views=2)
        third = self.make_project("Third")

        response = self.client.get(reverse("analytics"))
        rows = {item.pk: item for item in response.context["projects"]}

        for project in (first, second, third):
            with self.subTest(project=project.title):
                row = rows[project.pk]
                self.assertEqual(row.likes_total, project.likes.count())
                self.assertEqual(row.comments_total, project.comments.count())
                self.assertEqual(row.views_total, project.view_events.count())

    def test_replies_are_counted_the_same_way_the_database_counts_them(self):
        project = self.make_project("With Replies", likes=2, comments=2)
        parent = project.comments.first()
        Comment.objects.create(
            user=self.owner,
            project=project,
            parent=parent,
            content="a reply",
        )

        likes, comments, _ = self.totals_for(project)

        self.assertEqual(likes, 2)
        self.assertEqual(comments, project.comments.count())
        self.assertEqual(comments, 3)


# ---------------------------------------------------------------------------
# P0 #5 - login ignored ?next=, breaking the @login_required round trip.
# ---------------------------------------------------------------------------


class LoginRedirectTests(TestCase):
    def setUp(self):
        self.password = "pw-p0-strong-1"
        self.user = User.objects.create_user("login-user", password=self.password)

    def login(self, next_value=None, password=None, query_next=None):
        url = reverse("login")
        if query_next is not None:
            url = f"{url}?next={query_next}"
        data = {"username": self.user.username, "password": password or self.password}
        if next_value is not None:
            data["next"] = next_value
        return self.client.post(url, data)

    def test_login_without_next_goes_to_the_dashboard(self):
        response = self.login()

        self.assertRedirects(response, reverse("dashboard"))

    def test_login_with_a_valid_next_returns_to_that_page(self):
        target = reverse("my_bookmarks")

        response = self.login(next_value=target)

        self.assertRedirects(response, target)

    def test_the_full_login_required_round_trip(self):
        """A visitor hits a protected page, logs in, and lands back on it."""
        protected = reverse("my_collections")

        gate = self.client.get(protected)
        self.assertRedirects(gate, f"{reverse('login')}?next={protected}")

        form_page = self.client.get(f"{reverse('login')}?next={protected}")
        self.assertContains(form_page, f'name="next" value="{protected}"')

        response = self.client.post(
            f"{reverse('login')}?next={protected}",
            {"username": self.user.username, "password": self.password},
        )
        self.assertRedirects(response, protected)

    def test_an_absolute_external_next_is_refused(self):
        response = self.login(next_value="https://evil.example.com/steal")

        self.assertRedirects(response, reverse("dashboard"))
        self.assertNotIn("evil.example.com", response["Location"])

    def test_a_scheme_relative_external_next_is_refused(self):
        response = self.login(next_value="//evil.example.com/steal")

        self.assertRedirects(response, reverse("dashboard"))
        self.assertNotIn("evil.example.com", response["Location"])

    def test_a_javascript_scheme_next_is_refused(self):
        response = self.login(next_value="javascript:alert(1)")

        self.assertRedirects(response, reverse("dashboard"))
        self.assertNotIn("javascript", response["Location"].lower())

    def test_an_external_next_in_the_query_string_is_refused(self):
        response = self.client.post(
            f"{reverse('login')}?next=https://evil.example.com/",
            {"username": self.user.username, "password": self.password},
        )

        self.assertRedirects(response, reverse("dashboard"))
        self.assertNotIn("evil.example.com", response["Location"])

    def test_a_failed_login_preserves_next(self):
        target = reverse("my_bookmarks")

        response = self.login(next_value=target, password="wrong-password")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'name="next" value="{target}"')
        self.assertContains(response, "Invalid username or password.")

    def test_a_failed_login_preserves_the_username(self):
        response = self.login(password="wrong-password")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'value="{self.user.username}"')

    def test_a_failed_login_does_not_echo_an_unsafe_next_back_into_the_form(self):
        response = self.login(
            next_value="https://evil.example.com/",
            password="wrong-password",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "evil.example.com")
        self.assertNotContains(response, 'name="next"')

    def test_an_already_authenticated_user_with_next_is_sent_there(self):
        self.client.force_login(self.user)
        target = reverse("my_bookmarks")

        response = self.client.get(f"{reverse('login')}?next={target}")

        self.assertRedirects(response, target)

    def test_an_already_authenticated_user_without_next_goes_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("login"))

        self.assertRedirects(response, reverse("home"))

    def test_an_already_authenticated_user_is_not_sent_off_site(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('login')}?next=https://evil.example.com/")

        self.assertRedirects(response, reverse("home"))
