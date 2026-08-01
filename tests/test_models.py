import pytest
from django.db import IntegrityError

from core.models import Student
from tests.factories import StudentFactory, TeacherFactory


@pytest.mark.django_db
class TestStudent:
    def test_str_shows_full_name_and_id(self):
        student = StudentFactory(student_id="S0042", first_name="Hana", last_name="Tesfaye")
        assert str(student) == "Hana Tesfaye (S0042)"

    def test_default_status_is_active(self):
        assert StudentFactory().status == Student.Status.ACTIVE

    def test_student_id_must_be_unique(self):
        StudentFactory(student_id="S0001")
        with pytest.raises(IntegrityError):
            StudentFactory(student_id="S0001")

    def test_students_ordered_by_last_then_first_name(self):
        StudentFactory(first_name="Yonas", last_name="Girma")
        StudentFactory(first_name="Meron", last_name="Bekele")
        StudentFactory(first_name="Abel", last_name="Girma")
        names = [(s.first_name, s.last_name) for s in Student.objects.all()]
        assert names == [("Meron", "Bekele"), ("Abel", "Girma"), ("Yonas", "Girma")]


@pytest.mark.django_db
class TestTeacher:
    def test_str_uses_full_name(self):
        teacher = TeacherFactory(user__first_name="Almaz", user__last_name="Kebede")
        assert str(teacher) == "Almaz Kebede"

    def test_str_falls_back_to_username(self):
        teacher = TeacherFactory(user__username="tademe", user__first_name="", user__last_name="")
        assert str(teacher) == "tademe"
