from django.contrib import admin
from .models import (
    Category,
    Profile,
    Project,
    ProjectImage,
    Like,
    Comment,
    Follow,
    BookmarkCollection,
    Bookmark,
    Notification,
    Contest,
    ContestParticipant,
    ContestSubmission,
    Certificate,
    Badge,
    UserBadge,
    Achievement,
    Leaderboard,
)


admin.site.register(Category)
admin.site.register(Profile)
admin.site.register(Project)
admin.site.register(ProjectImage)
admin.site.register(Like)
admin.site.register(Comment)
admin.site.register(Follow)
admin.site.register(BookmarkCollection)
admin.site.register(Bookmark)
admin.site.register(Notification)
admin.site.register(Contest)
admin.site.register(ContestParticipant)
admin.site.register(ContestSubmission)
admin.site.register(Certificate)
admin.site.register(Badge)
admin.site.register(UserBadge)
admin.site.register(Achievement)
admin.site.register(Leaderboard)