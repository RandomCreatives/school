from datetime import date

import factory
from django.contrib.auth import get_user_model

from core.models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Section,
    Student,
    Subject,
    Teacher,
)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")


class StudentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Student

    student_id = factory.Sequence(lambda n: f"S{n:04d}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    date_of_birth = factory.Faker("date_of_birth", minimum_age=6, maximum_age=18)
    gender = factory.Iterator([Student.Gender.FEMALE, Student.Gender.MALE])


class TeacherFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Teacher

    user = factory.SubFactory(UserFactory)


class AcademicYearFactory(factory.django.DjangoModelFactory):
    """Saving auto-creates the year's 3 terms (see AcademicYear.save)."""

    class Meta:
        model = AcademicYear

    name = factory.Sequence(lambda n: f"{2024 + n}/{str(2025 + n)[-2:]}")
    start_date = date(2024, 9, 1)
    end_date = date(2025, 6, 30)


class SubjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subject

    name = factory.Sequence(lambda n: f"Subject {n}")
    code = factory.Sequence(lambda n: f"SUB{n:03d}")


class SchoolClassFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SchoolClass

    academic_year = factory.SubFactory(AcademicYearFactory)
    grade_level = 7
    letter = factory.Sequence(lambda n: chr(ord("A") + n % 26))


class SectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Section

    school_class = factory.SubFactory(SchoolClassFactory)
    subject = factory.SubFactory(SubjectFactory)
    term = factory.LazyAttribute(lambda o: o.school_class.academic_year.terms.get(number=1))


class EnrollmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Enrollment

    student = factory.SubFactory(StudentFactory)
    school_class = factory.SubFactory(SchoolClassFactory)
