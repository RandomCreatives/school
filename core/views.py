from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import reporting, services
from .forms import AssessmentForm
from .models import (
    AcademicYear,
    Assessment,
    AttendanceRecord,
    Enrollment,
    SchoolClass,
    Score,
    Section,
    Student,
    Term,
)


@login_required
def home(request):
    """The daily hub: teachers see their roll sheet + gradebooks; office staff
    additionally see today's roll gaps and sections missing grades."""
    year = services.current_academic_year()
    teacher = services.teacher_for(request.user)
    today = timezone.localdate()

    if request.user.is_staff:
        roll_classes = SchoolClass.objects.filter(academic_year=year) if year else []
    elif teacher and year:
        roll_classes = SchoolClass.objects.filter(
            academic_year=year, homeroom_teacher=teacher
        )
    else:
        roll_classes = []

    sections = Section.objects.none()
    if teacher and year:
        sections = Section.objects.filter(
            teacher=teacher, school_class__academic_year=year
        ).select_related("subject", "school_class", "term")

    taken_today = set(
        AttendanceRecord.objects.filter(date=today, school_class__in=roll_classes)
        .values_list("school_class_id", flat=True)
    )
    missing_assessments = (
        services.sections_missing_assessments(year)
        if (request.user.is_staff and year)
        else None
    )

    return render(
        request,
        "core/home.html",
        {
            "year": year,
            "today": today,
            "roll_classes": roll_classes,
            "taken_today": taken_today,
            "terms": year.terms.all() if year else [],
            "sections": sections,
            "missing_assessments": missing_assessments,
            "active_students": Student.objects.filter(status=Student.Status.ACTIVE).count(),
        },
    )


def _parse_date(raw):
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


@login_required
def attendance_sheet(request, class_id):
    school_class = get_object_or_404(
        SchoolClass.objects.select_related("academic_year"), pk=class_id
    )
    if not services.can_take_attendance(request.user, school_class):
        raise PermissionDenied("Only this class's homeroom teacher takes its attendance.")

    today = timezone.localdate()
    raw = request.POST.get("date") if request.method == "POST" else request.GET.get("date")
    on_date = _parse_date(raw) if raw else today
    if on_date is None:
        messages.error(request, f"Not a valid date: {raw!r}")
        return redirect("core:attendance-sheet", class_id=school_class.id)

    year = school_class.academic_year
    editable = (year.start_date <= on_date <= year.end_date) and on_date <= today

    if request.method == "POST":
        statuses = {
            int(key[7:]): value
            for key, value in request.POST.items()
            if key.startswith("status-") and key[7:].isdigit()
        }
        try:
            counts = services.save_attendance(
                school_class, on_date, statuses, taken_by=services.teacher_for(request.user)
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            summary = " · ".join(
                f"{counts.get(value, 0)} {label}"
                for value, label in AttendanceRecord.Status.choices
            )
            messages.success(request, f"Roll saved for {on_date}: {summary}.")
        return redirect(f"{request.path}?date={on_date.isoformat()}")

    enrollments = Enrollment.objects.filter(
        school_class=school_class, student__status=Student.Status.ACTIVE
    ).select_related("student")
    existing = {
        record.student_id: record.status
        for record in AttendanceRecord.objects.filter(
            date=on_date, student_id__in=[e.student_id for e in enrollments]
        )
    }
    rows = [
        {"student": e.student, "status": existing.get(e.student_id, "present")}
        for e in enrollments
    ]
    return render(
        request,
        "core/attendance_sheet.html",
        {
            "school_class": school_class,
            "on_date": on_date,
            "today": today,
            "editable": editable,
            "taken": bool(existing),
            "rows": rows,
            "statuses": AttendanceRecord.Status.choices,
        },
    )


@login_required
def gradebook(request, section_id):
    section = get_object_or_404(
        Section.objects.select_related(
            "subject", "school_class__academic_year", "term", "teacher__user"
        ),
        pk=section_id,
    )
    if not services.can_grade_section(request.user, section):
        raise PermissionDenied("Only this section's teacher can manage its gradebook.")

    if request.method == "POST":
        form = AssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.section = section
            assessment.save()
            messages.success(request, f"Added assessment “{assessment.name}”.")
            return redirect("core:gradebook", section_id=section.id)
    else:
        form = AssessmentForm()

    assessments = list(section.assessments.all())
    students = [
        e.student
        for e in Enrollment.objects.filter(
            school_class=section.school_class, student__status=Student.Status.ACTIVE
        ).select_related("student")
    ]
    score_map = {
        (s.student_id, s.assessment_id): s.value
        for s in Score.objects.filter(assessment__in=assessments)
    }
    averages = services.section_weighted_averages(section)
    rows = [
        {
            "student": student,
            "cells": [score_map.get((student.id, a.id)) for a in assessments],
            "average": averages.get(student.id),
        }
        for student in students
    ]
    return render(
        request,
        "core/gradebook.html",
        {
            "section": section,
            "form": form,
            "assessments": assessments,
            "rows": rows,
        },
    )


@login_required
def assessment_scores(request, assessment_id):
    assessment = get_object_or_404(
        Assessment.objects.select_related(
            "section__subject", "section__school_class", "section__term"
        ),
        pk=assessment_id,
    )
    section = assessment.section
    if not services.can_grade_section(request.user, section):
        raise PermissionDenied("Only this section's teacher can enter scores.")

    entered = {}
    if request.method == "POST":
        values = {
            int(key[6:]): value
            for key, value in request.POST.items()
            if key.startswith("score-") and key[6:].isdigit()
        }
        try:
            saved, deleted = services.upsert_scores(assessment, values)
        except ValueError as exc:
            messages.error(request, f"Nothing was saved — {exc}")
            entered = values  # keep the teacher's entries on screen
        else:
            message = f"Saved {saved} score(s)."
            if deleted:
                message += f" Removed {deleted}."
            messages.success(request, message)
            return redirect("core:assessment-scores", assessment_id=assessment.id)

    existing = {s.student_id: s.value for s in assessment.scores.all()}
    students = [
        e.student
        for e in Enrollment.objects.filter(
            school_class=section.school_class, student__status=Student.Status.ACTIVE
        ).select_related("student")
    ]
    rows = [
        {
            "student": student,
            "value": entered.get(student.id, existing.get(student.id, "")),
        }
        for student in students
    ]
    return render(
        request,
        "core/assessment_scores.html",
        {"assessment": assessment, "section": section, "rows": rows},
    )


@login_required
def student_report(request, student_id):
    student = get_object_or_404(Student, pk=student_id)
    year = services.current_academic_year() or AcademicYear.objects.order_by(
        "-start_date"
    ).first()
    if year is None:
        messages.error(request, "No academic year exists yet — the office must create one.")
        return redirect("core:home")
    if not services.can_view_student_report(request.user, student, year):
        raise PermissionDenied("You can only view reports for your own homeroom students.")

    report = services.student_term_report(student, year)
    summary = services.attendance_summary(student, year)
    summary_rows = [
        {"label": label, "count": summary.get(value, 0), "key": value}
        for value, label in AttendanceRecord.Status.choices
    ]
    return render(
        request,
        "core/student_report.html",
        {
            "student": student,
            "year": year,
            "report": report,
            "summary_rows": summary_rows,
            "terms": year.terms.all(),
        },
    )


def _pdf_response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def report_card_pdf(request, student_id, term_id):
    student = get_object_or_404(Student, pk=student_id)
    term = get_object_or_404(Term.objects.select_related("academic_year"), pk=term_id)
    if not services.can_view_student_report(request.user, student, term.academic_year):
        raise PermissionDenied("You can only view reports for your own homeroom students.")
    card = services.student_term_report_card(student, term)
    if card is None:
        messages.error(
            request, f"{student.full_name} has no class in {term.academic_year}."
        )
        return redirect("core:student-report", student_id=student.id)
    pdf_bytes = reporting.build_student_report_card(
        student, term, card, services.term_attendance_summary(student, term)
    )
    year_slug = term.academic_year.name.replace("/", "-")
    return _pdf_response(
        pdf_bytes, f"report-card-{student.student_id}-{year_slug}-term{term.number}.pdf"
    )


@login_required
def class_report_cards_pdf(request, class_id, term_id):
    school_class = get_object_or_404(
        SchoolClass.objects.select_related("academic_year"), pk=class_id
    )
    term = get_object_or_404(Term, pk=term_id, academic_year=school_class.academic_year)
    if not services.can_take_attendance(request.user, school_class):
        raise PermissionDenied(
            "Only this class's homeroom teacher or the office prints its report cards."
        )
    students = [
        e.student
        for e in Enrollment.objects.filter(
            school_class=school_class, student__status=Student.Status.ACTIVE
        ).select_related("student")
    ]
    cards = [
        (student, services.student_term_report_card(student, term),
         services.term_attendance_summary(student, term))
        for student in students
    ]
    pdf_bytes = reporting.build_class_report_cards(school_class, term, cards)
    year_slug = school_class.academic_year.name.replace("/", "-")
    class_slug = school_class.name.lower().replace(" ", "-")
    return _pdf_response(
        pdf_bytes, f"report-cards-{class_slug}-{year_slug}-term{term.number}.pdf"
    )
