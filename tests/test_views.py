import re

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Assessment, AttendanceRecord, Score
from tests.factories import AssessmentFactory, TeacherFactory, UserFactory


def login(client, user):
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestHome:
    def test_anonymous_redirected_to_login(self, client):
        assert client.get(reverse("core:home")).status_code == 302

    def test_teacher_sees_homeroom_and_sections(self, client, school):
        response = login(client, school.teacher.user).get(reverse("core:home"))
        assert response.status_code == 200
        assert "not taken" in response.content.decode()
        assert "Open gradebook" in response.content.decode()


@pytest.mark.django_db
class TestAttendanceSheet:
    def url(self, school):
        return reverse("core:attendance-sheet", args=[school.school_class.id])

    def test_anonymous_redirected(self, client, school):
        assert client.get(self.url(school)).status_code == 302

    def test_other_teacher_forbidden(self, client, school):
        other = TeacherFactory()
        response = login(client, other.user).get(self.url(school))
        assert response.status_code == 403

    def test_homeroom_teacher_gets_list_with_present_defaults(self, client, school):
        response = login(client, school.teacher.user).get(self.url(school))
        content = response.content.decode()
        assert response.status_code == 200
        for student in school.students:
            assert student.full_name in content
        present_checked = re.findall(r'value="present"\s+checked', content)
        assert len(present_checked) == 3

    def test_post_saves_and_redirects(self, client, school):
        today = timezone.localdate()
        data = {"date": today.isoformat()}
        for i, student in enumerate(school.students):
            data[f"status-{student.id}"] = ["present", "absent", "late"][i]
        response = login(client, school.teacher.user).post(self.url(school), data)
        assert response.status_code == 302
        assert AttendanceRecord.objects.filter(date=today).count() == 3
        assert AttendanceRecord.objects.get(student=school.students[1]).status == "absent"

    def test_office_admin_can_open_the_sheet(self, client, school):
        admin = UserFactory(is_staff=True)
        assert login(client, admin).get(self.url(school)).status_code == 200

    def test_invalid_date_shows_error(self, client, school):
        response = login(client, school.teacher.user).get(self.url(school) + "?date=nope")
        assert response.status_code == 302  # redirected with an error message


@pytest.mark.django_db
class TestGradebook:
    def section(self, school):
        return school.school_class.sections.get(
            subject=school.subjects[0], term__number=1
        )

    def test_another_teacher_cannot_view(self, client, school):
        other = TeacherFactory()
        url = reverse("core:gradebook", args=[self.section(school).id])
        assert login(client, other.user).get(url).status_code == 403

    def test_assigned_teacher_adds_assessment(self, client, school):
        section = self.section(school)
        url = reverse("core:gradebook", args=[section.id])
        response = login(client, school.teacher.user).post(
            url, {"name": "Quiz 1", "weight": 1, "max_score": 100, "date": ""}
        )
        assert response.status_code == 302
        assert Assessment.objects.get(section=section).name == "Quiz 1"

    def test_gradebook_shows_average_column(self, client, school):
        url = reverse("core:gradebook", args=[self.section(school).id])
        content = login(client, school.teacher.user).get(url).content.decode()
        assert "Term avg /100" in content


@pytest.mark.django_db
class TestAssessmentScores:
    def assessment(self, school):
        return AssessmentFactory(
            section=school.school_class.sections.get(
                subject=school.subjects[0], term__number=1
            ),
            max_score=100,
        )

    def test_saves_scores(self, client, school):
        assessment = self.assessment(school)
        url = reverse("core:assessment-scores", args=[assessment.id])
        data = {f"score-{s.id}": "75" for s in school.students}
        response = login(client, school.teacher.user).post(url, data)
        assert response.status_code == 302
        assert Score.objects.filter(assessment=assessment, value=75).count() == 3

    def test_invalid_score_saves_nothing_and_keeps_entries(self, client, school):
        assessment = self.assessment(school)
        url = reverse("core:assessment-scores", args=[assessment.id])
        data = {f"score-{school.students[0].id}": "150"}
        response = login(client, school.teacher.user).post(url, data)
        assert response.status_code == 200  # re-rendered, not redirected
        assert Score.objects.count() == 0
        assert 'value="150"' in response.content.decode()

    def test_other_teacher_forbidden(self, client, school):
        assessment = self.assessment(school)
        other = TeacherFactory()
        url = reverse("core:assessment-scores", args=[assessment.id])
        assert login(client, other.user).get(url).status_code == 403


@pytest.mark.django_db
class TestStudentReport:
    def url(self, school):
        return reverse("core:student-report", args=[school.students[0].id])

    def test_homeroom_teacher_sees_averages(self, client, school):
        section = school.school_class.sections.get(subject=school.subjects[0], term__number=1)
        assessment = AssessmentFactory(section=section, max_score=100)
        student = school.students[0]
        from tests.factories import ScoreFactory

        ScoreFactory(assessment=assessment, student=student, value=85)
        response = login(client, school.teacher.user).get(self.url(school))
        content = response.content.decode()
        assert response.status_code == 200
        assert "85.0" in content
        assert student.full_name in content

    def test_unrelated_teacher_forbidden(self, client, school):
        other = TeacherFactory()
        assert login(client, other.user).get(self.url(school)).status_code == 403

    def test_office_admin_allowed(self, client, school):
        admin = UserFactory(is_staff=True)
        assert login(client, admin).get(self.url(school)).status_code == 200
