from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from core import services
from core.models import Score
from tests.factories import AssessmentFactory, ScoreFactory


def term1_section(school, subject=None):
    return school.school_class.sections.get(
        subject=subject or school.subjects[0], term__number=1
    )


@pytest.mark.django_db
class TestUpsertScores:
    def test_creates_scores(self, school):
        assessment = AssessmentFactory(section=term1_section(school), max_score=100)
        values = {s.id: str(70 + i * 10) for i, s in enumerate(school.students)}
        saved, deleted = services.upsert_scores(assessment, values)
        assert (saved, deleted) == (3, 0)
        assert Score.objects.get(assessment=assessment, student=school.students[1]).value == 80

    def test_updates_and_blank_removes(self, school):
        assessment = AssessmentFactory(section=term1_section(school))
        s1 = school.students[0]
        ScoreFactory(assessment=assessment, student=s1, value=55)
        saved, deleted = services.upsert_scores(assessment, {s1.id: ""})
        assert (saved, deleted) == (0, 1)
        assert not Score.objects.filter(assessment=assessment, student=s1).exists()

    def test_over_max_rejected_and_nothing_written(self, school):
        assessment = AssessmentFactory(section=term1_section(school), max_score=50)
        values = {school.students[0].id: "49", school.students[1].id: "51"}
        with pytest.raises(ValueError, match="between 0 and 50"):
            services.upsert_scores(assessment, values)
        assert Score.objects.filter(assessment=assessment).count() == 0

    def test_non_numeric_rejected(self, school):
        assessment = AssessmentFactory(section=term1_section(school))
        with pytest.raises(ValueError, match="Not a number"):
            services.upsert_scores(assessment, {school.students[0].id: "eighty"})

    def test_student_from_another_class_rejected(self, school):
        assessment = AssessmentFactory(section=term1_section(school))
        with pytest.raises(ValueError, match="not actively enrolled"):
            services.upsert_scores(assessment, {424242: "10"})


@pytest.mark.django_db
class TestWeightedAverages:
    def test_weighted_normalized_average(self, school):
        section = term1_section(school)
        quiz = AssessmentFactory(section=section, weight=1, max_score=50)
        midterm = AssessmentFactory(section=section, weight=2, max_score=100)
        student = school.students[0]
        ScoreFactory(assessment=quiz, student=student, value=40)   # 80%
        ScoreFactory(assessment=midterm, student=student, value=90)  # 90%
        averages = services.section_weighted_averages(section)
        # (80×1 + 90×2) / 3 = 86.67 → 86.7
        assert averages[student.id] == Decimal("86.7")

    def test_missing_score_excludes_that_assessments_weight(self, school):
        section = term1_section(school)
        quiz = AssessmentFactory(section=section, weight=1, max_score=50)
        AssessmentFactory(section=section, weight=2, max_score=100)  # untouched
        student = school.students[0]
        ScoreFactory(assessment=quiz, student=student, value=40)  # 80%
        assert services.section_weighted_averages(section)[student.id] == Decimal("80.0")

    def test_no_assessments_means_no_averages(self, school):
        assert services.section_weighted_averages(term1_section(school)) == {}


@pytest.mark.django_db
class TestScoreModel:
    def test_cannot_exceed_assessment_max(self, school):
        score = ScoreFactory.build(
            assessment=AssessmentFactory(section=term1_section(school), max_score=20),
            value=21,
        )
        with pytest.raises(ValidationError, match="Cannot exceed"):
            score.full_clean()


@pytest.mark.django_db
class TestStudentTermReport:
    def test_rows_per_subject_and_term(self, school):
        student = school.students[0]
        for subject in school.subjects:
            section = term1_section(school, subject)
            assessment = AssessmentFactory(section=section, max_score=100)
            ScoreFactory(assessment=assessment, student=student, value=85)

        report = services.student_term_report(student, school.year)
        assert report is not None
        assert len(report["rows"]) == 2
        for row in report["rows"]:
            # term 1 has the score; terms 2 and 3 are still empty
            assert row["averages"] == [Decimal("85.0"), None, None]

    def test_no_enrollment_returns_none(self, school):
        from tests.factories import StudentFactory

        assert services.student_term_report(StudentFactory(), school.year) is None
