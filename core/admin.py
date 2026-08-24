from django.contrib import admin
from .models import (
    Category, Profile, Project, ProjectImage, Like, Comment, Follow,
    BookmarkCollection, Bookmark, Notification, Contest, ContestParticipant,
    ContestSubmission, Certificate, Badge, UserBadge, Achievement, Leaderboard,
    ProjectView, ProfileVisit, ActivityEvent, Report,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Categories are an admin-managed taxonomy.

    Students select a category when publishing and visitors filter by it, but
    no student-facing view creates one. The starting set is seeded by migration
    0009; everything after that is managed here.
    """

    list_display = ("name", "project_count", "created_at")
    search_fields = ("name", "description")
    ordering = ("name",)

    @admin.display(description="Projects")
    def project_count(self, obj):
        return obj.projects.count()


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "category", "status", "visibility", "featured", "views_count", "created_at")
    list_filter = ("status", "visibility", "featured", "stage", "category")
    search_fields = ("title", "description", "tags", "technologies", "owner__username")
    list_editable = ("featured", "status", "visibility")


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "registration_deadline", "submission_deadline", "participant_count")
    list_filter = ("status",)
    search_fields = ("title", "description", "rules")

    @admin.display(description="Participants")
    def participant_count(self, obj):
        return obj.participants.count()


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reason", "reporter", "project", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("reason", "description", "reporter__username", "project__title")
    list_editable = ("status",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")
    search_fields = ("recipient__username", "sender__username", "message")


for model in [
    Profile, ProjectImage, Like, Comment, Follow, BookmarkCollection,
    Bookmark, ContestParticipant, ContestSubmission, Certificate, Badge,
    UserBadge, Achievement, Leaderboard, ProjectView, ProfileVisit, ActivityEvent,
]:
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
