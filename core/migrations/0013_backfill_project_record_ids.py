from django.db import migrations


def backfill_project_ids(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    for project in Project.objects.filter(project_id__isnull=True).order_by("pk").iterator():
        project.project_id = f"LP-LEGACY-{project.pk:06d}"
        project.save(update_fields=["project_id"])


def reverse_backfill(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(project_id__startswith="LP-LEGACY-").update(project_id=None)


class Migration(migrations.Migration):
    dependencies = [("core", "0012_academicyear_college_profile_role_and_more")]
    operations = [migrations.RunPython(backfill_project_ids, reverse_backfill)]
