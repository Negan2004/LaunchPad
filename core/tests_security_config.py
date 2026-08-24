"""Regression coverage for the P2 security and configuration pass.

Nothing here prints or asserts on an actual secret value.
"""

import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Category, Project
from .validators import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    MAX_DOCUMENT_BYTES,
    validate_document_upload,
)


def upload(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class SettingsHygieneTests(TestCase):
    """The settings module must not carry credentials of its own."""

    def settings_source(self):
        return (Path(settings.BASE_DIR) / "config" / "settings.py").read_text(
            encoding="utf-8"
        )

    def test_settings_contains_no_hardcoded_secret_key(self):
        source = self.settings_source()

        self.assertNotIn("django-insecure-", source)
        self.assertNotIn(settings.SECRET_KEY, source)

    def test_settings_contains_no_hardcoded_database_password(self):
        source = self.settings_source()
        password = settings.DATABASES["default"]["PASSWORD"]

        self.assertNotIn("'PASSWORD': '", source)
        if password:
            self.assertNotIn(password, source)

    def test_the_secret_key_is_configured(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertGreaterEqual(len(settings.SECRET_KEY), 40)

    def test_env_example_exists_and_holds_no_real_values(self):
        example = Path(settings.BASE_DIR) / ".env.example"
        self.assertTrue(example.exists(), ".env.example is missing")

        text = example.read_text(encoding="utf-8")
        self.assertIn("DJANGO_SECRET_KEY=", text)
        self.assertIn("DB_PASSWORD=", text)
        self.assertNotIn("django-insecure-", text)
        self.assertNotIn(settings.SECRET_KEY, text)

        password = settings.DATABASES["default"]["PASSWORD"]
        if password:
            self.assertNotIn(password, text)

    def test_env_file_is_git_ignored(self):
        gitignore = (Path(settings.BASE_DIR) / ".gitignore").read_text(encoding="utf-8")

        self.assertIn(".env", gitignore.split())

    def test_collectstatic_output_is_git_ignored(self):
        gitignore = (Path(settings.BASE_DIR) / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("staticfiles/", gitignore)


class SecurityHeaderTests(TestCase):
    """Headers that are safe over plain HTTP are always on."""

    def test_always_on_hardening_is_enabled(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")

    def test_session_and_csrf_cookies_are_hardened(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")

    def test_responses_carry_the_hardening_headers(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")

    def test_static_root_is_configured(self):
        self.assertTrue(settings.STATIC_ROOT)
        self.assertTrue(str(settings.STATIC_ROOT).endswith("staticfiles"))

    def test_upload_size_ceilings_are_set(self):
        self.assertGreater(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 0)
        self.assertGreater(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 0)

    @override_settings(SECURE_HSTS_SECONDS=0)
    def test_hsts_is_off_by_default(self):
        """HSTS cannot be undone before it expires, so it must be opt-in."""
        response = self.client.get(reverse("home"))

        self.assertNotIn("Strict-Transport-Security", response.headers)

    def test_https_dependent_settings_track_secure_mode(self):
        self.assertEqual(settings.SESSION_COOKIE_SECURE, settings.SECURE_MODE)
        self.assertEqual(settings.CSRF_COOKIE_SECURE, settings.SECURE_MODE)
        self.assertEqual(settings.SECURE_SSL_REDIRECT, settings.SECURE_MODE)

    def test_local_development_is_not_broken_by_secure_cookies(self):
        """With DEBUG on, cookies must still work over plain HTTP."""
        if settings.DEBUG:
            self.assertFalse(settings.SESSION_COOKIE_SECURE)
            self.assertFalse(settings.SECURE_SSL_REDIRECT)

    def test_a_login_session_still_works(self):
        User.objects.create_user("cookie-user", password="pw-sec-1")

        self.assertTrue(
            self.client.login(username="cookie-user", password="pw-sec-1")
        )
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)


class AllowedHostsTests(TestCase):
    def test_localhost_is_allowed_so_debug_false_still_works_locally(self):
        for host in ["localhost", "127.0.0.1"]:
            with self.subTest(host=host):
                self.assertIn(host, settings.ALLOWED_HOSTS)

    def test_an_unknown_host_is_rejected(self):
        response = self.client.get(reverse("home"), HTTP_HOST="evil.example.com")

        self.assertEqual(response.status_code, 400)

    def test_no_production_domain_is_hardcoded(self):
        source = (Path(settings.BASE_DIR) / "config" / "settings.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(".com'", source.replace("example.com", ""))


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


class DocumentValidatorTests(TestCase):
    """The validator in isolation."""

    def test_html_is_rejected_by_extension(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_document_upload(
                upload("payload.html", b"<script>alert(1)</script>", "text/html")
            )

        self.assertEqual(ctx.exception.code, "forbidden_extension")

    def test_htm_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_document_upload(upload("payload.htm", b"<html></html>"))

    def test_svg_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_document_upload(upload("evil.svg", b"<svg onload=alert(1)>"))

    def test_script_files_are_rejected(self):
        for name in ["x.js", "x.php", "x.py", "x.sh", "x.bat", "x.exe"]:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_document_upload(upload(name, b"anything"))

    def test_html_disguised_as_a_pdf_is_rejected_on_content(self):
        """Extension checks alone are not enough."""
        with self.assertRaises(ValidationError) as ctx:
            validate_document_upload(
                upload(
                    "sneaky.pdf",
                    b"<!DOCTYPE html><html><script>alert(1)</script></html>",
                    "application/pdf",
                )
            )

        self.assertEqual(ctx.exception.code, "markup_content")

    def test_script_markup_inside_a_txt_file_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_document_upload(
                upload("notes.txt", b"<script>alert(1)</script>", "text/plain")
            )

    def test_a_claimed_pdf_without_the_pdf_signature_is_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_document_upload(upload("fake.pdf", b"not a pdf at all"))

        self.assertEqual(ctx.exception.code, "content_mismatch")

    def test_a_forged_content_type_does_not_help(self):
        """Content-Type comes from the client and is ignored."""
        with self.assertRaises(ValidationError):
            validate_document_upload(
                upload("payload.html", b"<html>", "application/pdf")
            )

    def test_an_oversized_file_is_rejected(self):
        big = upload("big.txt", b"x" * 16)
        big.size = MAX_DOCUMENT_BYTES + 1

        with self.assertRaises(ValidationError) as ctx:
            validate_document_upload(big)

        self.assertEqual(ctx.exception.code, "file_too_large")

    # ---- accepted ----

    def test_a_real_pdf_is_accepted(self):
        validate_document_upload(
            upload("guide.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf")
        )

    def test_plain_text_is_accepted(self):
        validate_document_upload(
            upload("notes.txt", b"Setup steps for the project.", "text/plain")
        )

    def test_markdown_is_accepted(self):
        validate_document_upload(upload("README.md", b"# Project\n\nNotes."))

    def test_restructured_text_is_accepted(self):
        validate_document_upload(upload("docs.rst", b"Title\n=====\n"))

    def test_a_docx_is_accepted(self):
        validate_document_upload(upload("report.docx", b"PK\x03\x04\x14\x00"))

    def test_an_odt_is_accepted(self):
        validate_document_upload(upload("report.odt", b"PK\x03\x04\x14\x00"))

    def test_an_empty_value_is_ignored(self):
        # Django refuses to build an UploadedFile with a blank name, so this
        # path is reached with a bare field value rather than an upload.
        class Blank:
            name = ""
            size = 0

        validate_document_upload(Blank())

    def test_a_stored_file_missing_from_disk_does_not_break_validation(self):
        """Model validators also run against already-saved files."""

        class MissingFile:
            name = "documentation/gone.pdf"
            size = 10

            @property
            def file(self):
                raise FileNotFoundError("not on disk")

        validate_document_upload(MissingFile())

    def test_every_allowed_extension_is_documented(self):
        self.assertIn(".pdf", ALLOWED_DOCUMENT_EXTENSIONS)
        self.assertNotIn(".html", ALLOWED_DOCUMENT_EXTENSIONS)
        self.assertNotIn(".svg", ALLOWED_DOCUMENT_EXTENSIONS)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class DocumentUploadFlowTests(TestCase):
    """The validator through the real create/edit views."""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("doc-user", password="pw-sec-1")
        self.category = Category.objects.get(name="Other")
        self.client.force_login(self.user)

    def payload(self, **overrides):
        data = {
            "title": "Documented Project",
            "description": "d",
            "category": self.category.pk,
            "visibility": "public",
            "status": "published",
            "stage": "prototype",
        }
        data.update(overrides)
        return data

    def image(self):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), "blue").save(buffer, format="PNG")
        return SimpleUploadedFile("shot.png", buffer.getvalue(), "image/png")

    def test_an_html_upload_is_refused_by_the_create_view(self):
        response = self.client.post(
            reverse("create_project"),
            self.payload(
                documentation_file=upload(
                    "payload.html", b"<script>alert(1)</script>", "text/html"
                )
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.exists())
        self.assertIn("documentation_file", response.context["form"].errors)

    def test_no_html_file_reaches_the_media_root(self):
        self.client.post(
            reverse("create_project"),
            self.payload(
                documentation_file=upload("payload.html", b"<script>x</script>")
            ),
        )

        media = Path(settings.MEDIA_ROOT)
        self.assertEqual(list(media.rglob("*.html")), [])

    def test_a_pdf_upload_is_accepted_and_stored(self):
        response = self.client.post(
            reverse("create_project"),
            self.payload(
                documentation_file=upload(
                    "guide.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf"
                )
            ),
        )

        project = Project.objects.get(title="Documented Project")
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertTrue(project.documentation_file.name.endswith(".pdf"))

    def test_a_markdown_upload_is_accepted(self):
        self.client.post(
            reverse("create_project"),
            self.payload(
                title="Markdown Project",
                documentation_file=upload("README.md", b"# Notes"),
            ),
        )

        project = Project.objects.get(title="Markdown Project")
        self.assertTrue(project.documentation_file)

    def test_creating_a_project_without_any_document_still_works(self):
        response = self.client.post(reverse("create_project"), self.payload())

        project = Project.objects.get(title="Documented Project")
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertFalse(project.documentation_file)

    def test_image_uploads_are_unaffected(self):
        data = self.payload(title="Image Project")
        data["images"] = [self.image()]

        self.client.post(reverse("create_project"), data)

        project = Project.objects.get(title="Image Project")
        self.assertEqual(project.images.count(), 1)

    def test_editing_a_project_can_replace_a_document(self):
        self.client.post(
            reverse("create_project"),
            self.payload(
                documentation_file=upload("first.pdf", b"%PDF-1.7\nfirst")
            ),
        )
        project = Project.objects.get(title="Documented Project")

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(
                documentation_file=upload("second.pdf", b"%PDF-1.7\nsecond")
            ),
        )

        project.refresh_from_db()
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertIn("second", project.documentation_file.name)

    def test_editing_cannot_swap_in_an_html_document(self):
        self.client.post(
            reverse("create_project"),
            self.payload(documentation_file=upload("ok.pdf", b"%PDF-1.7\nok")),
        )
        project = Project.objects.get(title="Documented Project")
        original = project.documentation_file.name

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(documentation_file=upload("bad.html", b"<html>")),
        )

        project.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(project.documentation_file.name, original)

    def test_editing_a_project_that_already_has_a_document_still_works(self):
        """The validator must tolerate re-validating the stored file."""
        self.client.post(
            reverse("create_project"),
            self.payload(documentation_file=upload("keep.pdf", b"%PDF-1.7\nkeep")),
        )
        project = Project.objects.get(title="Documented Project")

        response = self.client.post(
            reverse("edit_project", args=[project.pk]),
            self.payload(title="Renamed With Document"),
        )

        project.refresh_from_db()
        self.assertRedirects(response, reverse("project_detail", args=[project.pk]))
        self.assertEqual(project.title, "Renamed With Document")
        self.assertTrue(project.documentation_file)
