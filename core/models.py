from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone

from .validators import validate_document_upload

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class College(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=40, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Department(models.Model):
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["college__name", "name"]
        constraints = [models.UniqueConstraint(fields=["college", "code"], name="unique_department_code_per_college")]

    def __str__(self):
        return f"{self.name} — {self.college.code}"


class Program(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="programs")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=40)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["department__college__name", "name"]
        constraints = [models.UniqueConstraint(fields=["department", "code"], name="unique_program_code_per_department")]

    def __str__(self):
        return f"{self.name} — {self.department.code}"


class AcademicYear(models.Model):
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name="academic_years")
    label = models.CharField(max_length=20)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-label"]
        constraints = [models.UniqueConstraint(fields=["college", "label"], name="unique_academic_year_per_college")]

    def __str__(self):
        return self.label


class Semester(models.Model):
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="semesters")
    name = models.CharField(max_length=50)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["starts_on", "name"]
        constraints = [models.UniqueConstraint(fields=["academic_year", "name"], name="unique_semester_per_academic_year")]

    def __str__(self):
        return f"{self.academic_year} — {self.name}"


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    role = models.CharField(max_length=30, choices=[
        ("student", "Student"), ("faculty", "Faculty"), ("mentor", "Mentor"),
        ("department_admin", "Department Admin"), ("college_admin", "College Admin"),
        ("platform_admin", "Platform Admin"), ("judge", "Judge"),
    ], default="student")
    college_entity = models.ForeignKey(College, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    department_entity = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    program_entity = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    academic_year_entity = models.ForeignKey(AcademicYear, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    semester_entity = models.ForeignKey(Semester, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles")
    display_name = models.CharField(max_length=150, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='covers/', blank=True, null=True)
    college = models.CharField(max_length=200, blank=True)
    education = models.CharField(max_length=200, blank=True)
    skills = models.TextField(blank=True)
    portfolio_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)

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
    LIFECYCLE_CHOICES = [
        ("idea", "Idea"), ("team_formation", "Team Formation"), ("awaiting_mentor", "Awaiting Mentor"),
        ("proposal", "Proposal"), ("awaiting_approval", "Awaiting Approval"), ("approved", "Approved"),
        ("planning", "Planning"), ("development", "In Development"), ("milestones", "Milestones"),
        ("under_review", "Under Review"), ("revision_required", "Revision Required"), ("submitted", "Submitted"),
        ("evaluated", "Evaluated"), ("verified", "Verified"), ("showcase", "Showcase"),
        ("completed", "Completed"), ("archived", "Archived"),
    ]

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='projects'
    )
    project_id = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    tagline = models.CharField(max_length=280, blank=True)
    problem_statement = models.TextField(blank=True)
    proposed_solution = models.TextField(blank=True)
    project_type = models.CharField(max_length=100, blank=True)
    skills = models.TextField(blank=True)
    college_entity = models.ForeignKey(College, on_delete=models.PROTECT, null=True, blank=True, related_name="projects")
    department_entity = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="projects")
    program_entity = models.ForeignKey(Program, on_delete=models.PROTECT, null=True, blank=True, related_name="projects")
    academic_year_entity = models.ForeignKey(AcademicYear, on_delete=models.PROTECT, null=True, blank=True, related_name="projects")
    semester_entity = models.ForeignKey(Semester, on_delete=models.PROTECT, null=True, blank=True, related_name="projects")
    lifecycle_state = models.CharField(max_length=30, choices=LIFECYCLE_CHOICES, default="idea")
    is_archived = models.BooleanField(default=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='projects'
    )
    title = models.CharField(max_length=200)
    short_description = models.CharField(max_length=280, blank=True)
    description = models.TextField()
    technologies = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True)
    demo_url = models.URLField(blank=True)
    repository_url = models.URLField(blank=True)
    documentation_url = models.URLField(blank=True)
    documentation_file = models.FileField(
        upload_to='documentation/',
        blank=True,
        null=True,
        # On the model rather than the form so the admin and any future
        # code path are covered too.
        validators=[validate_document_upload],
    )

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
    STAGE_CHOICES = [
        ('prototype', 'Prototype'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
    ]
    stage = models.CharField(
        max_length=12,
        choices=STAGE_CHOICES,
        default='prototype'
    )
    views_count = models.PositiveIntegerField(default=0)
    featured = models.BooleanField(default=False)
    featured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.project_id:
            self.project_id = f"LP-{timezone.now():%Y%m%d}-{self.owner_id or 'NEW'}-{timezone.now().strftime('%f')[-6:]}"
        super().save(*args, **kwargs)


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

    class Meta:
        # The inbox view slices [:100]; without a deterministic order those are
        # an arbitrary 100 rows rather than the newest 100.
        ordering = ["-created_at", "-id"]

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


class ProjectView(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="view_events",
    )
    visitor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="project_views",
    )
    session_key = models.CharField(max_length=40, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"View: {self.project.title}"


class ProfileVisit(models.Model):
    profile_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile_visits",
    )
    visitor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="profile_views_made",
    )
    session_key = models.CharField(max_length=40, blank=True)
    visited_at = models.DateTimeField(auto_now_add=True)


class ActivityEvent(models.Model):
    EVENT_CHOICES = [
        ("project_published", "Project published"),
        ("like_received", "Like received"),
        ("comment_received", "Comment received"),
        ("follow_received", "Follow received"),
        ("contest_winner", "Contest winner"),
        ("featured_project", "Featured project"),
        ("badge_awarded", "Badge awarded"),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events_triggered",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    points = models.PositiveIntegerField(default=0)
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events",
    )
    contest = models.ForeignKey(
        Contest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Report(models.Model):
    STATUS_CHOICES = [
        ("open", "Open"),
        ("reviewing", "Reviewing"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_made",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_received",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    reason = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_resolved",
    )

    class Meta:
        ordering = ["-created_at"]


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships")
    role = models.CharField(max_length=100, default="Contributor")
    responsibilities = models.TextField(blank=True)
    contribution = models.TextField(blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")]


class ProjectMentorship(models.Model):
    STATUS_CHOICES = [("requested", "Requested"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("ended", "Ended")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="mentorships")
    mentor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentorships")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_requests")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="requested")
    feedback = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "mentor"], name="unique_project_mentor_request")]


class ProjectMilestone(models.Model):
    STATUS_CHOICES = [("not_started", "Not Started"), ("in_progress", "In Progress"), ("blocked", "Blocked"), ("submitted", "Submitted"), ("reviewed", "Reviewed"), ("completed", "Completed"), ("overdue", "Overdue")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_milestones")
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    progress = models.PositiveSmallIntegerField(default=0)
    deliverables = models.TextField(blank=True)
    evidence = models.FileField(upload_to="milestones/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProjectLifecycleEvent(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="lifecycle_events")
    previous_state = models.CharField(max_length=30, blank=True)
    new_state = models.CharField(max_length=30, choices=Project.LIFECYCLE_CHOICES)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="project_lifecycle_events")
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ProjectVerification(models.Model):
    SCOPE_CHOICES = [("mentor", "Mentor"), ("faculty", "Faculty"), ("department", "Department"), ("institution", "Institution")]
    STATUS_CHOICES = [("pending", "Pending"), ("verified", "Verified"), ("rejected", "Rejected")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="verifications")
    verifier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="project_verifications")
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    evidence = models.TextField(blank=True)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "scope"], name="unique_project_verification_scope")]


class ProjectReview(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="project_reviews")
    milestone = models.ForeignKey(ProjectMilestone, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    comments = models.TextField()
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    revision_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ProjectApproval(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("revision", "Revision Required")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="approvals")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="project_approvals")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    comments = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


class ProjectDocument(models.Model):
    DOCUMENT_TYPES = [("proposal", "Proposal"), ("requirements", "Requirements"), ("report", "Report"), ("presentation", "Presentation"), ("research", "Research"), ("final", "Final Submission")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="project_documents")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="project_documents/", validators=[validate_document_upload])
    created_at = models.DateTimeField(auto_now_add=True)
