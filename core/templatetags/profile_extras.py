from django import template


register = template.Library()


@register.filter
def stored_file_exists(file_field):
    if not file_field:
        return False

    try:
        return file_field.storage.exists(file_field.name)
    except (AttributeError, ValueError):
        return False


@register.filter
def has_profile_text(value):
    if value is None:
        return False

    cleaned_value = str(value).strip()
    return bool(cleaned_value) and cleaned_value.lower() not in {"null", "none"}


@register.filter
def clean_profile_text(value):
    if not has_profile_text(value):
        return ""

    return str(value).strip()


@register.filter
def split_commas(value):
    """Comma-separated model text (technologies, tags) as a clean list."""
    if not value:
        return []

    return [part.strip() for part in str(value).split(",") if part.strip()]
