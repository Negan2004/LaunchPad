from .models import Contest, Follow, Notification, Project, User


def launchpad_context(request):
    return {
        "unread_notification_count": (
            Notification.objects.filter(recipient=request.user, is_read=False).count()
            if request.user.is_authenticated else 0
        ),
        "platform_stats": {
            "students": User.objects.count(),
            "projects": Project.objects.filter(status="published", visibility="public").count(),
            "contests": Contest.objects.exclude(status="draft").count(),
            "connections": Follow.objects.count(),
        },
    }
