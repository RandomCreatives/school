import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import (
    AcademicYear,
    Assessment,
    AttendanceRecord,
    SchoolClass,
    Score,
    Section,
    Student,
)


@pytest.mark.django_db
class TestSeedDemo:
    def test_scaffolds_a_full_school(self):
        call_command("seed_demo")

        year = AcademicYear.objects.get()
        assert year.is_current
        assert year.terms.count() == 3
        assert all(term.start_date and term.end_date for term in year.terms.all())

        assert SchoolClass.objects.count() == 16  # grades 1–8 × A/B
        assert Student.objects.count() == 16 * 24
        assert Section.objects.count() == 16 * 8 * 3  # classes × subjects × terms
        assert Assessment.objects.count() > 0
        assert Score.objects.count() > 0
        assert AttendanceRecord.objects.count() > 16 * 24 * 5  # ~10 school days
        assert (
            AttendanceRecord.objects.filter(taken_by__isnull=False).count()
            == AttendanceRecord.objects.count()
        )
        # every class has a homeroom teacher, every section a teacher
        assert SchoolClass.objects.filter(homeroom_teacher__isnull=True).count() == 0
        assert Section.objects.filter(teacher__isnull=True).count() == 0
        # demo logins exist
        User = get_user_model()
        assert User.objects.filter(username="office", is_superuser=True).exists()
        assert User.objects.filter(teacher_profile__isnull=False).count() == 16

    def test_refuses_to_overwrite_without_fresh_flag(self):
        call_command("seed_demo")
        with pytest.raises(CommandError, match="--fresh"):
            call_command("seed_demo")
        call_command("seed_demo", fresh=True)  # wipes and reseeds cleanly
        assert Student.objects.count() == 16 * 24
        assert AcademicYear.objects.count() == 1
