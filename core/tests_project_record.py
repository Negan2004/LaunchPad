from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Category, College, Project, ProjectLifecycleEvent, ProjectMentorship, ProjectMilestone


class ProjectRecordWorkflowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Project Records")
        self.college_a = College.objects.create(name="Demo Institute A", code="DIA")
        self.college_b = College.objects.create(name="Demo Institute B", code="DIB")
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.mentor = User.objects.create_user(username="mentor", password="pass12345")
        self.mentor.profile.role = "mentor"
        self.mentor.profile.college_entity = self.college_a
        self.mentor.profile.save()
        self.outsider = User.objects.create_user(username="outsider", password="pass12345")
        self.outsider.profile.role = "college_admin"
        self.outsider.profile.college_entity = self.college_b
        self.outsider.profile.save()
        self.project = Project.objects.create(owner=self.owner, category=self.category, college_entity=self.college_a, title="Lifecycle Project", description="A complete project record.")

    def test_project_receives_stable_record_id(self):
        self.assertTrue(self.project.project_id.startswith("LP-"))

    def test_owner_can_add_milestone_and_transition(self):
        self.client.login(username="owner", password="pass12345")
        self.assertEqual(self.client.post(reverse("add_project_milestone", args=[self.project.pk]), {"title": "Proposal", "description": "Write proposal"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("transition_project", args=[self.project.pk]), {"new_state": "team_formation", "reason": "Team formed"}).status_code, 302)
        self.assertTrue(ProjectMilestone.objects.filter(project=self.project, title="Proposal").exists())
        self.assertTrue(ProjectLifecycleEvent.objects.filter(project=self.project, new_state="team_formation", actor=self.owner).exists())

    def test_cross_college_reviewer_is_forbidden(self):
        self.client.login(username="outsider", password="pass12345")
        response = self.client.post(reverse("review_project_approval", args=[self.project.pk]), {"status": "approved"})
        self.assertEqual(response.status_code, 403)

    def test_mentor_request_and_response_are_persistent(self):
        self.client.login(username="owner", password="pass12345")
        self.assertEqual(self.client.post(reverse("request_project_mentor", args=[self.project.pk]), {"mentor_id": self.mentor.pk}).status_code, 302)
        request = ProjectMentorship.objects.get(project=self.project, mentor=self.mentor)
        self.client.logout()
        self.client.login(username="mentor", password="pass12345")
        self.assertEqual(self.client.post(reverse("respond_to_mentor_request", args=[request.pk]), {"action": "accepted", "feedback": "I can supervise this project."}).status_code, 302)
        request.refresh_from_db()
        self.assertEqual(request.status, "accepted")
