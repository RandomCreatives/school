"""Business operations that span models — kept out of views and admin."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import (
    AcademicYear,
    AttendanceRecord,
    Enrollment,
    SchoolClass,
    Score,
    Section,
    Student,
    Subject,
)


def current_academic_year():
    return AcademicYear.objects.filter(is_current=True).first()


def generate_sections_for_class(school_class) -> int:
    """Create sections for every subject × every term of the class's year.

    Idempotent: existing sections (and their teacher assignments) are left
    untouched. Returns the number of sections created.
    """
    created = 0
    for term in school_class.academic_year.terms.all():
        for subject in Subject.objects.all():
            _, was_created = Section.objects.get_or_create(
                school_class=school_class, subject=subject, term=term
            )
            created += was_created
    return created


# ---------------------------------------------------------------------------
# Access checks (who can do what in the custom views)
# ---------------------------------------------------------------------------

def teacher_for(user):
    """The Teacher profile for a user, or None."""
    return getattr(user, "teacher_profile", None)


def can_take_attendance(user, school_class) -> bool:
    if user.is_staff:
        return True
    teacher = teacher_for(user)
    return teacher is not None and school_class.homeroom_teacher_id == teacher.id


def can_grade_section(user, section) -> bool:
    if user.is_staff:
        return True
    teacher = teacher_for(user)
    return teacher is not None and section.teacher_id == teacher.id


def can_view_student_report(user, student, academic_year) -> bool:
    """Office staff see everything; teachers see their own homeroom students."""
    if user.is_staff:
        return True
    teacher = teacher_for(user)
    if teacher is None:
        return False
    return Enrollment.objects.filter(
        student=student,
        school_class__academic_year=academic_year,
        school_class__homeroom_teacher=teacher,
    ).exists()


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def _active_enrolled_ids(school_class) -> set[int]:
    return set(
        Enrollment.objects.filter(
            school_class=school_class, student__status=Student.Status.ACTIVE
        ).values_list("student_id", flat=True)
    )


@transaction.atomic
def save_attendance(school_class, on_date, statuses: dict[int, str], taken_by=None) -> dict:
    """Save a full morning roll sheet for a class.

    ``statuses`` maps student_id → status string. One record is written per
    student (including "present"), overwriting any sheet already saved for
    that date. Returns counts per status.
    """
    year = school_class.academic_year
    today = timezone.localdate()
    if not (year.start_date <= on_date <= year.end_date):
        raise ValueError(f"{on_date} is outside {year.name}.")
    if on_date > today:
        raise ValueError("Cannot take attendance for a future date.")

    enrolled = _active_enrolled_ids(school_class)
    unknown = set(statuses) - enrolled
    if unknown:
        raise ValueError(f"Students not actively enrolled in this class: {sorted(unknown)}")

    valid = set(AttendanceRecord.Status.values)
    records = []
    for student_id, status in statuses.items():
        if status not in valid:
            raise ValueError(f"Unknown attendance status: {status!r}")
        records.append(
            AttendanceRecord(
                school_class=school_class,
                student_id=student_id,
                date=on_date,
                status=status,
                taken_by=taken_by,
            )
        )
    AttendanceRecord.objects.bulk_create(
        records,
        update_conflicts=True,
        update_fields=["school_class", "status", "taken_by"],
        unique_fields=["student", "date"],
    )
    return dict(Counter(statuses.values()))


def attendance_summary_between(student, start_date, end_date) -> dict[str, int]:
    """Counts per status for a student within a date range."""
    rows = (
        AttendanceRecord.objects.filter(student=student, date__range=(start_date, end_date))
        .values("status")
        .annotate(n=Count("id"))
    )
    counts = {row["status"]: row["n"] for row in rows}
    return {value: counts.get(value, 0) for value in AttendanceRecord.Status.values}


def attendance_summary(student, academic_year) -> dict[str, int]:
    """Counts per status for a student within an academic year."""
    return attendance_summary_between(
        student, academic_year.start_date, academic_year.end_date
    )


def term_date_range(term):
    """A term's own dates, falling back to its year's bounds when unset."""
    return (
        term.start_date or term.academic_year.start_date,
        term.end_date or term.academic_year.end_date,
    )


def term_attendance_summary(student, term) -> dict[str, int]:
    start, end = term_date_range(term)
    return attendance_summary_between(student, start, end)


def student_term_report_card(student, term) -> dict | None:
    """Report-card content for one term: per-subject averages.

    Returns None if the student has no class in the term's year.
    """
    enrollment = (
        Enrollment.objects.filter(
            student=student, school_class__academic_year=term.academic_year
        )
        .select_related("school_class__homeroom_teacher__user")
        .first()
    )
    if enrollment is None:
        return None
    sections = (
        enrollment.school_class.sections.filter(term=term)
        .select_related("subject")
        .order_by("subject__name")
    )
    rows = [
        {"subject": section.subject, "average": section_weighted_averages(section).get(student.id)}
        for section in sections
    ]
    return {"enrollment": enrollment, "rows": rows}


# ---------------------------------------------------------------------------
# Dashboard gaps (what the office needs to chase today)
# ---------------------------------------------------------------------------

def classes_missing_roll(academic_year, on_date):
    """Classes in the year with no attendance records for the date."""
    taken = AttendanceRecord.objects.filter(
        school_class__academic_year=academic_year, date=on_date
    ).values_list("school_class_id", flat=True)
    return SchoolClass.objects.filter(academic_year=academic_year).exclude(pk__in=taken)


def sections_missing_assessments(academic_year):
    """Sections with zero assessments — i.e. grading hasn't started."""
    return (
        Section.objects.filter(
            school_class__academic_year=academic_year, assessments__isnull=True
        )
        .select_related("subject", "school_class", "term", "teacher__user")
        .order_by(
            "school_class__grade_level",
            "school_class__letter",
            "term__number",
            "subject__name",
        )
        .distinct()
    )


# ---------------------------------------------------------------------------
# Gradebook
# ---------------------------------------------------------------------------

@transaction.atomic
def upsert_scores(assessment, values: dict[int, str]) -> tuple[int, int]:
    """Save raw scores for an assessment: {student_id: raw_input_string}.

    Blank input removes that student's score (so teachers can undo a mistaken
    entry). Nothing is written if any value is invalid. Returns (saved, deleted).
    """
    parsed = {}
    for student_id, raw in values.items():
        raw = (raw or "").strip()
        if not raw:
            parsed[student_id] = None
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise ValueError(f"Not a number: {raw!r} (student {student_id})") from None
        if value < 0 or value > assessment.max_score:
            raise ValueError(
                f"Scores must be between 0 and {assessment.max_score} "
                f"(got {value} for student {student_id})."
            )
        parsed[student_id] = value

    enrolled = _active_enrolled_ids(assessment.section.school_class)
    unknown = set(parsed) - enrolled
    if unknown:
        raise ValueError(f"Students not actively enrolled in this class: {sorted(unknown)}")

    saved = deleted = 0
    for student_id, value in parsed.items():
        if value is None:
            deleted += Score.objects.filter(
                assessment=assessment, student_id=student_id
            ).delete()[0]
        else:
            Score.objects.update_or_create(
                assessment=assessment, student_id=student_id, defaults={"value": value}
            )
            saved += 1
    return saved, deleted


def section_weighted_averages(section) -> dict[int, Decimal]:
    """Normalized 100-point weighted average per student for a section.

    Each score contributes (value / max_score × 100) × weight. A student
    without a score on an assessment simply doesn't carry that assessment's
    weight (relevant mid-term, while grading is still in progress).

    Interim policy only — the school's term-certification formula will
    replace this behind the same seam once shared.
    """
    assessments = {a.id: a for a in section.assessments.all()}
    if not assessments:
        return {}
    totals = defaultdict(Decimal)
    weights = defaultdict(Decimal)
    for score in Score.objects.filter(assessment_id__in=assessments):
        assessment = assessments[score.assessment_id]
        normalized = score.value / assessment.max_score * 100
        totals[score.student_id] += normalized * assessment.weight
        weights[score.student_id] += assessment.weight
    return {
        student_id: (totals[student_id] / weights[student_id]).quantize(Decimal("0.1"))
        for student_id in totals
    }


def student_term_report(student, academic_year) -> dict | None:
    """Per-subject, per-term 100-point averages for a student in a year.

    Returns None if the student has no class in that year.
    """
    enrollment = (
        Enrollment.objects.filter(
            student=student, school_class__academic_year=academic_year
        )
        .select_related("school_class__homeroom_teacher__user")
        .first()
    )
    if enrollment is None:
        return None

    sections = enrollment.school_class.sections.select_related("subject", "term").order_by(
        "subject__name", "term__number"
    )
    rows_by_subject = {}
    for section in sections:
        # "averages" is a display-ready list indexed [term_number - 1]
        row = rows_by_subject.setdefault(
            section.subject,
            {"subject": section.subject, "averages": [None] * AcademicYear.TERMS_PER_YEAR},
        )
        row["averages"][section.term.number - 1] = section_weighted_averages(section).get(
            student.id
        )
    return {"enrollment": enrollment, "rows": list(rows_by_subject.values())}
