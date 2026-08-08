from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

from .models import (
    Profile,
    Project,
    Category,
    Comment,
    Bookmark,
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

    class Meta:
        model = Profile
        fields = [
            "bio",
            "avatar",
            "skills",
            "portfolio_url",
        ]


class ProjectForm(forms.ModelForm):

    class Meta:
        model = Project
        fields = [
            "title",
            "description",
            "category",
            "demo_url",
            "repository_url",
            "visibility",
            "status",
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

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]