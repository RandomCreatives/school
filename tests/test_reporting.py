from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core import reporting, services
from tests.factories import (
    AssessmentFactory,
    AttendanceRecordFactory,
    SchoolClassFactory,
    ScoreFactory,
    StudentFactory,
)


@pytest.mark.django_db
class TestTermReportCardData:
    def test_subject_averages_for_the_term(self, school):
        student = school.students[0]
        section = school.school_class.sections.get(
            subject=school.subjects[0], term__number=1
        )
        assessment = AssessmentFactory(section=section, max_score=100)
        ScoreFactory(assessment=assessment, student=student, value=88)

        term1 = school.year.terms.get(number=1)
        card = services.student_term_report_card(student, term1)

        assert card["enrollment"].school_class == school.school_class
        averages = {row["subject"].name: row["average"] for row in card["rows"]}
        assert averages[school.subjects[0].name] == Decimal("88.0")
        # subject 2 has a section but no assessment yet → no average
        assert averages[school.subjects[1].name] is None

    def test_student_without_a_class_gets_none(self, school):
        term1 = school.year.terms.get(number=1)
        assert services.student_term_report_card(StudentFactory(), term1) is None


@pytest.mark.django_db
class TestTermAttendanceSummary:
    def test_scoped_to_term_dates(self, school):
        student = school.students[0]
        year_start = school.year.start_date
        term1 = school.year.terms.get(number=1)
        term1.start_date = year_start
        term1.end_date = year_start + timedelta(days=30)
        term1.save()

        AttendanceRecordFactory(
            student=student, school_class=school.school_class,
            date=year_start + timedelta(days=10), status="absent",  # inside term 1
        )
        AttendanceRecordFactory(
            student=student, school_class=school.school_class,
            date=year_start + timedelta(days=40), status="absent",  # after term 1
        )
        assert services.term_attendance_summary(student, term1)["absent"] == 1

    def test_falls_back_to_year_bounds_when_term_dates_unset(self, school):
        student = school.students[0]
        term1 = school.year.terms.get(number=1)  # no dates set
        AttendanceRecordFactory(
            student=student, school_class=school.school_class,
            date=school.year.start_date + timedelta(days=7), status="late",
        )
        assert services.term_attendance_summary(student, term1)["late"] == 1


@pytest.mark.django_db
class TestPdfBuilders:
    def test_student_card_is_a_pdf(self, school):
        student = school.students[0]
        term1 = school.year.terms.get(number=1)
        card = services.student_term_report_card(student, term1)
        pdf = reporting.build_student_report_card(
            student, term1, card, services.term_attendance_summary(student, term1)
        )
        assert pdf.startswith(b"%PDF")

    def test_class_cards_one_pdf_for_the_whole_class(self, school):
        term1 = school.year.terms.get(number=1)
        cards = [
            (s, services.student_term_report_card(s, term1),
             services.term_attendance_summary(s, term1))
            for s in school.students
        ]
        assert reporting.build_class_report_cards(
            school.school_class, term1, cards
        ).startswith(b"%PDF")

    def test_empty_class_still_renders(self, school):
        empty_class = SchoolClassFactory(academic_year=school.year, grade_level=8)
        term1 = school.year.terms.get(number=1)
        assert reporting.build_class_report_cards(empty_class, term1, []).startswith(b"%PDF")


@pytest.mark.django_db
class TestDashboardGaps:
    def test_classes_missing_roll(self, school):
        today = timezone.localdate()
        second = SchoolClassFactory(academic_year=school.year, grade_level=8)
        assert set(services.classes_missing_roll(school.year, today)) == {
            school.school_class,
            second,
        }
        services.save_attendance(
            school.school_class,
            today,
            {s.id: "present" for s in school.students},
            taken_by=school.teacher,
        )
        assert list(services.classes_missing_roll(school.year, today)) == [second]

    def test_sections_missing_assessments(self, school):
        missing = services.sections_missing_assessments(school.year)
        assert missing.count() == 2 * 3  # 2 subjects × 3 terms, none graded yet

        graded = school.school_class.sections.get(
            subject=school.subjects[0], term__number=1
        )
        AssessmentFactory(section=graded)
        missing_after = list(services.sections_missing_assessments(school.year))
        assert graded not in missing_after
        assert len(missing_after) == 5
