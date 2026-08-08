from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    skills = models.TextField(blank=True)
    portfolio_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username

class Project(models.Model):
    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('private', 'Private'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
    ]

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='projects'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='projects'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    demo_url = models.URLField(blank=True)
    repository_url = models.URLField(blank=True)
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='public'
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class ProjectImage(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='projects/')
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.title} - Image"

class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='likes'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'project'],
                name='unique_user_project_like'
            )
        ]

    def __str__(self):
        return f"{self.user} likes {self.project.title}"

class Comment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.project.title}"


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='following'
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='followers'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['follower', 'following'],
                name='unique_follower_following'
            )
        ]

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class BookmarkCollection(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookmark_collections'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class Bookmark(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookmarks'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='bookmarks'
    )
    collection = models.ForeignKey(
        BookmarkCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookmarks'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'project'],
                name='unique_user_project_bookmark'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.project.title}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    notification_type = models.CharField(max_length=50)
    message = models.CharField(max_length=255)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications'
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient.username} - {self.notification_type}"

class Contest(models.Model):

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('upcoming', 'Upcoming'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    rules = models.TextField()
    registration_deadline = models.DateTimeField()
    submission_deadline = models.DateTimeField()
    max_participants = models.PositiveIntegerField(null=True, blank=True)
    prize_information = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ContestParticipant(models.Model):

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='contest_participations'
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['contest', 'user'],
                name='unique_contest_participant'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.contest.title}"


class ContestSubmission(models.Model):

    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('winner', 'Winner'),
        ('runner_up', 'Runner Up'),
        ('rejected', 'Rejected'),
    ]

    contest = models.ForeignKey(
        Contest,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    participant = models.ForeignKey(
        ContestParticipant,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='contest_submissions'
    )
    submission_title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted'
    )
    score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['contest', 'participant'],
                name='unique_contest_participant_submission'
            )
        ]

    def __str__(self):
        return f"{self.submission_title} - {self.contest.title}"


class Certificate(models.Model):

    submission = models.OneToOneField(
        ContestSubmission,
        on_delete=models.CASCADE,
        related_name='certificate'
    )
    certificate_number = models.CharField(
        max_length=100,
        unique=True
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    certificate_file = models.FileField(
        upload_to='certificates/',
        blank=True,
        null=True
    )

    def __str__(self):
        return self.certificate_number

class Badge(models.Model):

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    icon = models.ImageField(
        upload_to='badges/',
        blank=True,
        null=True
    )
    points = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserBadge(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='badges'
    )
    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name='earned_by'
    )
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'badge'],
                name='unique_user_badge'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"


class Achievement(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='achievements'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    points = models.PositiveIntegerField(default=0)
    achieved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class Leaderboard(models.Model):

    PERIOD_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('overall', 'Overall'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leaderboard_entries'
    )
    period = models.CharField(
        max_length=20,
        choices=PERIOD_CHOICES
    )
    points = models.PositiveIntegerField(default=0)
    rank = models.PositiveIntegerField()
    period_start = models.DateField(
        null=True,
        blank=True
    )
    period_end = models.DateField(
        null=True,
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'period', 'period_start', 'period_end'],
                name='unique_user_leaderboard_period'
            )
        ]
        ordering = ['rank']

    def __str__(self):
        return f"{self.period} - {self.user.username} - Rank {self.rank}"