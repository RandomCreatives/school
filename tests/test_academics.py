from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from core.models import Enrollment, Section, Term
from core.services import generate_sections_for_class
from tests.factories import (
    AcademicYearFactory,
    EnrollmentFactory,
    SchoolClassFactory,
    SectionFactory,
    StudentFactory,
    SubjectFactory,
    TeacherFactory,
)


@pytest.mark.django_db
class TestAcademicYear:
    def test_creating_a_year_auto_creates_three_terms(self):
        year = AcademicYearFactory()
        assert list(year.terms.values_list("number", flat=True)) == [1, 2, 3]

    def test_only_one_year_can_be_current(self):
        AcademicYearFactory(is_current=True)
        with pytest.raises(IntegrityError):
            AcademicYearFactory(is_current=True)

    def test_end_date_must_be_after_start_date(self):
        year = AcademicYearFactory.build(start_date="2025-06-30", end_date="2024-09-01")
        with pytest.raises(ValidationError):
            year.full_clean()


@pytest.mark.django_db
class TestTerm:
    def test_at_most_three_terms_per_year(self):
        year = AcademicYearFactory()
        term = Term(academic_year=year, number=4)
        with pytest.raises(ValidationError):
            term.full_clean()

    def test_term_dates_must_fall_within_the_year(self):
        year = AcademicYearFactory(start_date=date(2024, 9, 1), end_date=date(2025, 6, 30))
        term = year.terms.get(number=1)
        term.start_date = date(2026, 1, 1)
        with pytest.raises(ValidationError):
            term.full_clean()

    def test_str_shows_year_and_number(self):
        year = AcademicYearFactory(name="2025/26")
        assert str(year.terms.get(number=2)) == "2025/26 · Term 2"


@pytest.mark.django_db
class TestSchoolClass:
    def test_name_property(self):
        school_class = SchoolClassFactory(grade_level=7, letter="b")
        assert school_class.name == "Grade 7B"  # letter is normalized to uppercase

    def test_str_includes_year(self):
        school_class = SchoolClassFactory(
            academic_year__name="2025/26", grade_level=3, letter="A"
        )
        assert str(school_class) == "Grade 3A · 2025/26"

    def test_same_grade_and_letter_cannot_repeat_within_a_year(self):
        year = AcademicYearFactory()
        SchoolClassFactory(academic_year=year, grade_level=7, letter="A")
        with pytest.raises(IntegrityError):
            SchoolClassFactory(academic_year=year, grade_level=7, letter="A")

    def test_a_teacher_gets_at_most_one_homeroom_per_year(self):
        year = AcademicYearFactory()
        teacher = TeacherFactory()
        SchoolClassFactory(academic_year=year, homeroom_teacher=teacher)
        with pytest.raises(IntegrityError):
            SchoolClassFactory(academic_year=year, homeroom_teacher=teacher)


@pytest.mark.django_db
class TestSection:
    def test_unique_per_class_subject_and_term(self):
        section = SectionFactory()
        with pytest.raises(IntegrityError):
            SectionFactory(
                school_class=section.school_class, subject=section.subject, term=section.term
            )

    def test_str(self):
        section = SectionFactory(
            subject__name="Mathematics", school_class__grade_level=7, school_class__letter="B"
        )
        assert str(section) == "Mathematics · Grade 7B · Term 1"


@pytest.mark.django_db
class TestGenerateSections:
    def test_creates_all_subjects_times_terms(self):
        SubjectFactory.create_batch(4)
        school_class = SchoolClassFactory()
        assert generate_sections_for_class(school_class) == 4 * 3
        assert Section.objects.filter(school_class=school_class).count() == 12

    def test_idempotent_and_preserves_teacher_assignments(self):
        subject = SubjectFactory()
        teacher = TeacherFactory()
        school_class = SchoolClassFactory()
        existing = Section.objects.create(
            school_class=school_class,
            subject=subject,
            term=school_class.academic_year.terms.get(number=1),
            teacher=teacher,
        )
        generate_sections_for_class(school_class)
        existing.refresh_from_db()
        assert existing.teacher == teacher
        assert generate_sections_for_class(school_class) == 0


@pytest.mark.django_db
class TestEnrollment:
    def test_duplicate_enrollment_in_same_class_rejected(self):
        enrollment = EnrollmentFactory()
        with pytest.raises(IntegrityError):
            Enrollment.objects.create(
                student=enrollment.student, school_class=enrollment.school_class
            )

    def test_student_cannot_join_two_classes_in_one_year(self):
        year = AcademicYearFactory()
        enrollment = EnrollmentFactory(school_class=SchoolClassFactory(academic_year=year))
        second = Enrollment(
            student=enrollment.student, school_class=SchoolClassFactory(academic_year=year)
        )
        with pytest.raises(ValidationError, match="already enrolled"):
            second.full_clean()

    def test_student_can_join_a_class_in_the_next_year(self):
        enrollment = EnrollmentFactory()
        second = EnrollmentFactory.build(
            student=enrollment.student,
            school_class=SchoolClassFactory(academic_year=AcademicYearFactory()),
        )
        second.full_clean()  # should not raise

    def test_section_membership_is_derived_from_the_class(self):
        school_class = SchoolClassFactory()
        subjects = SubjectFactory.create_batch(2)
        generate_sections_for_class(school_class)  # 2 subjects × 3 terms = 6 sections
        enrollment = EnrollmentFactory(school_class=school_class, student=StudentFactory())

        assert enrollment.sections.count() == 6
        term1_sections = enrollment.sections.filter(term__number=1)
        assert term1_sections.count() == 2
        assert {s.subject for s in term1_sections} == set(subjects)
