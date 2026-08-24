"""Seed the initial project category taxonomy.

Category is an admin-managed taxonomy: students select a category when
publishing a project and visitors filter by it, but no student-facing view
creates one. Project.category is a required PROTECT foreign key, so with an
empty Category table project creation is impossible - the create form renders
with an empty dropdown and never validates.

This migration seeds a starting taxonomy so the platform is usable out of the
box. Administrators can add, rename, or remove entries afterwards through the
Django admin; this migration does not run again and does not overwrite edits.
"""

from django.db import migrations


INITIAL_CATEGORIES = [
    (
        "Web Development",
        "Websites, web applications, APIs, and browser-based tools.",
    ),
    (
        "Mobile Development",
        "Android, iOS, and cross-platform mobile applications.",
    ),
    (
        "Machine Learning & AI",
        "Models, training pipelines, computer vision, NLP, and applied AI projects.",
    ),
    (
        "Data Science",
        "Analysis, visualisation, dashboards, and data engineering work.",
    ),
    (
        "IoT & Hardware",
        "Embedded systems, robotics, sensors, and connected devices.",
    ),
    (
        "Game Development",
        "Games, interactive experiences, simulations, and game engines.",
    ),
    (
        "UI/UX Design",
        "Interface design, design systems, prototypes, and user research.",
    ),
    (
        "Systems & Tools",
        "Developer tooling, automation, infrastructure, and desktop software.",
    ),
    (
        "Other",
        "Projects that do not fit an existing category.",
    ),
]


def seed_categories(apps, schema_editor):
    """Create any missing category. Existing rows are left untouched."""
    Category = apps.get_model("core", "Category")

    for name, description in INITIAL_CATEGORIES:
        Category.objects.get_or_create(
            name=name,
            defaults={"description": description},
        )


def unseed_categories(apps, schema_editor):
    """Remove seeded categories that are not in use.

    Project.category is PROTECT, so a category with projects attached must not
    be deleted - doing so would raise ProtectedError and break the reverse
    migration. Categories that an administrator has since attached projects to
    are deliberately kept.
    """
    Category = apps.get_model("core", "Category")

    Category.objects.filter(
        name__in=[name for name, _ in INITIAL_CATEGORIES],
        projects__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_activityevent_profilevisit_projectview_report"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
