from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import (
    Profile,
    Project,
    ProjectImage,
    Category,
    Comment,
    Bookmark,
    BookmarkCollection,
    Contest,
    ContestSubmission,
    Report,
)


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
        ]

    def clean(self):
        cleaned_data = super().clean()

        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data


class ProfileForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in ("display_name", "bio", "college", "education", "skills", "portfolio_url", "github_url", "linkedin_url", "twitter_url"):
            value = self.initial.get(field_name)
            if isinstance(value, str) and value.strip().lower() in {"null", "none"}:
                self.initial[field_name] = ""

        avatar = self.initial.get("avatar")
        if avatar and not avatar.storage.exists(avatar.name):
            self.initial["avatar"] = None

    class Meta:
        model = Profile
        fields = [
            "display_name",
            "bio",
            "avatar",
            "cover_image",
            "college",
            "education",
            "skills",
            "portfolio_url",
            "github_url",
            "linkedin_url",
            "twitter_url",

        ]


class ProjectForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage"].required = False
        if not self.initial.get("stage"):
            self.initial["stage"] = "prototype"

    class Meta:

        model = Project
        fields = [
            "title",
            "short_description",
            "description",
            "category",
            "technologies",
            "tags",
            "demo_url",
            "repository_url",
            "documentation_url",
            "documentation_file",
            "visibility",
            "status",
            "stage",
        ]
        widgets = {
            "short_description": forms.TextInput(attrs={"maxlength": 280}),
            "description": forms.Textarea(attrs={"rows": 8}),
            "technologies": forms.Textarea(attrs={"rows": 3, "placeholder": "Python, Django, PostgreSQL"}),
            "tags": forms.TextInput(attrs={"placeholder": "AI, education, web"}),
        }


class ProjectImageForm(forms.ModelForm):

    class Meta:
        model = ProjectImage
        fields = [
            "image",
        ]


class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = [
            "name",
            "description",
        ]


class CommentForm(forms.ModelForm):

    class Meta:
        model = Comment
        fields = [
            "content",
        ]


class BookmarkForm(forms.ModelForm):

    class Meta:
        model = Bookmark
        fields = []

class BookmarkCollectionForm(forms.ModelForm):

    class Meta:
        model = BookmarkCollection
        fields = [
            "name",
            "description",
        ]

class AddBookmarkToCollectionForm(forms.ModelForm):

    class Meta:
        model = Bookmark
        fields = [
            "collection",
        ]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)

        super().__init__(*args, **kwargs)

        if user:
            self.fields["collection"].queryset = BookmarkCollection.objects.filter(
                user=user
            )

class ContestForm(forms.ModelForm):
    class Meta:
        model = Contest
        fields = [
            "title",
            "description",
            "rules",
            "registration_deadline",
            "submission_deadline",
            "max_participants",
            "prize_information",
            "status",
        ]
        widgets = {
            "registration_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "submission_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 5}),
            "rules": forms.Textarea(attrs={"rows": 5}),
            "prize_information": forms.Textarea(attrs={"rows": 4}),
        }


class ContestSubmissionForm(forms.ModelForm):
    class Meta:
        model = ContestSubmission
        fields = ["project", "submission_title", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, user=None, contest=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            # Only work the owner has actually published publicly may be
            # entered. Filtering the queryset does double duty: it keeps
            # private and draft projects out of the dropdown, and ModelChoiceField
            # re-validates against the same queryset on POST, so a forged
            # project id is rejected before a ContestSubmission is created.
            # The project's own visibility is never changed by submitting it.
            self.fields["project"].queryset = Project.objects.filter(
                owner=user,
                status="published",
                visibility="public",
            )
        self.contest = contest


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}


class RegisterForm(UserCreationForm):

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
