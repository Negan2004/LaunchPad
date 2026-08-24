"""Upload validation.

Uploaded files are served from the same origin as the application, so anything
a browser will execute or render as markup is a stored-XSS vector. HTML was
accepted before this: a file called payload.html containing <script> was saved
into MEDIA_ROOT and served back as text/html.

The approach here is an allow-list of the formats project documentation
actually needs, checked against both the file name and the file's own leading
bytes. Content-Type from the browser is deliberately ignored - it is supplied
by the client and trivially forged.
"""

from pathlib import Path

from django.core.exceptions import ValidationError

# Formats a student would plausibly attach as project documentation.
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".rst",
    ".doc",
    ".docx",
    ".odt",
}

# Extensions worth naming in the error message, because they are the ones
# people actually try and the reason matters.
EXECUTABLE_EXTENSIONS = {
    ".html", ".htm", ".xhtml", ".shtml", ".svg", ".xml",
    ".js", ".mjs", ".php", ".py", ".rb", ".pl", ".sh", ".bat",
    ".cmd", ".ps1", ".exe", ".dll", ".jar", ".vbs", ".hta",
}

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB

# Leading bytes that mean a browser may treat the file as markup or script,
# whatever the extension claims.
MARKUP_SIGNATURES = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<script",
    b"<?php",
    b"<svg",
    b"<!entity",
    b"<?xml",
)

# Expected leading bytes per format, where the format has a stable signature.
CONTENT_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".odt": (b"PK\x03\x04",),
    ".doc": (b"\xd0\xcf\x11\xe0", b"PK\x03\x04"),
}


def read_head(value, size=1024):
    """Return the first bytes of an upload, or b"" if they cannot be read.

    Model validators also run against files already saved in storage, which may
    be missing on disk in a development copy. An unreadable stored file must not
    make an otherwise valid edit fail, so those cases fall back to name-only
    checks.
    """
    try:
        file_obj = value.file
    except (AttributeError, ValueError, OSError, FileNotFoundError):
        return b""

    try:
        position = file_obj.tell()
    except (AttributeError, OSError, ValueError):
        position = None

    try:
        file_obj.seek(0)
        head = file_obj.read(size) or b""
    except (AttributeError, OSError, ValueError, FileNotFoundError):
        return b""
    finally:
        try:
            file_obj.seek(position or 0)
        except (AttributeError, OSError, ValueError):
            pass

    if isinstance(head, str):
        head = head.encode("utf-8", "ignore")

    return head


def validate_document_upload(value):
    """Allow only real documentation files.

    Checks the extension against an allow-list, the declared size, and the
    file's own leading bytes. Raises ValidationError otherwise.
    """
    name = (getattr(value, "name", "") or "").strip()
    if not name:
        return

    suffix = Path(name).suffix.lower()

    if suffix in EXECUTABLE_EXTENSIONS:
        raise ValidationError(
            "%(ext)s files cannot be uploaded because a browser would run or "
            "render them. Attach a PDF, plain text, Markdown or Word document.",
            code="forbidden_extension",
            params={"ext": suffix or "These"},
        )

    if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type %(ext)s. Allowed types: %(allowed)s.",
            code="unsupported_extension",
            params={
                "ext": suffix or "(none)",
                "allowed": ", ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS)),
            },
        )

    size = getattr(value, "size", None)
    if size is not None and size > MAX_DOCUMENT_BYTES:
        raise ValidationError(
            "That file is %(size).1f MB. The limit is %(limit)s MB.",
            code="file_too_large",
            params={
                "size": size / (1024 * 1024),
                "limit": MAX_DOCUMENT_BYTES // (1024 * 1024),
            },
        )

    head = read_head(value)
    if not head:
        # Nothing readable (empty upload, or a stored file missing from disk).
        # The name-based checks above already passed.
        return

    lowered = head.lstrip().lower()
    if lowered.startswith(MARKUP_SIGNATURES) or b"<script" in lowered:
        raise ValidationError(
            "That file contains HTML or script markup, which cannot be "
            "uploaded regardless of its file name.",
            code="markup_content",
        )

    expected = CONTENT_SIGNATURES.get(suffix)
    if expected and not head.startswith(expected):
        raise ValidationError(
            "That file does not look like a valid %(ext)s file.",
            code="content_mismatch",
            params={"ext": suffix},
        )
