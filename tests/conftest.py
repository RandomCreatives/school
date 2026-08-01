from datetime import date
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core import services
from core.models import Section
from tests.factories import (
    AcademicYearFactory,
    EnrollmentFactory,
    SchoolClassFactory,
    StudentFactory,
    SubjectFactory,
    TeacherFactory,
)


@pytest.fixture
def school(db):
    """A live school year: current year spanning today, one homeroom teacher
    with a class, 2 subjects (→ 6 sections, all assigned to that teacher),
    and 3 enrolled students."""
    today = timezone.localdate()
    year = AcademicYearFactory(
        is_current=True,
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
    )
    teacher = TeacherFactory()
    school_class = SchoolClassFactory(
        academic_year=year, grade_level=7, letter="A", homeroom_teacher=teacher
    )
    subjects = SubjectFactory.create_batch(2)
    services.generate_sections_for_class(school_class)
    Section.objects.filter(school_class=school_class).update(teacher=teacher)
    students = [
        EnrollmentFactory(student=StudentFactory(), school_class=school_class).student
        for _ in range(3)
    ]
    return SimpleNamespace(
        year=year,
        teacher=teacher,
        school_class=school_class,
        subjects=subjects,
        students=students,
    )
