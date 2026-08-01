"""PDF term report cards, built with reportlab (no system dependencies).

Layout is deliberately plain: information first, easy to print on any
printer, easy to restyle later once the school's letterhead/branding exists.
"""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import AttendanceRecord

DISCLAIMER = (
    "Averages are interim (weighted by assessment weight). "
    "Final term certification follows the school's own formula."
)


def _subject_table(rows):
    data = [["Subject", "Average /100"]]
    for row in rows:
        average = row["average"]
        data.append([row["subject"].name, str(average) if average is not None else "-"])
    table = Table(data, colWidths=[110 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _card_elements(student, term, card, attendance, styles):
    year = term.academic_year
    school_class = card["enrollment"].school_class
    homeroom = school_class.homeroom_teacher or "-"
    info_table = Table(
        [
            ["Student", student.full_name, "ID", student.student_id],
            ["Class", school_class.name, "Year", year.name],
            ["Term", f"Term {term.number}", "Homeroom", str(homeroom)],
            ["Generated", timezone.localdate().isoformat(), "", ""],
        ],
        colWidths=[25 * mm, 65 * mm, 25 * mm, 35 * mm],
    )
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    attendance_line = "   ".join(
        f"{label}: {attendance.get(value, 0)}"
        for value, label in AttendanceRecord.Status.choices
    )
    return [
        Paragraph("Term Report Card", styles["Title"]),
        info_table,
        Spacer(1, 6 * mm),
        _subject_table(card["rows"]) if card["rows"] else Paragraph(
            "No subjects recorded for this term.", styles["Normal"]
        ),
        Spacer(1, 6 * mm),
        Paragraph(f"<b>Attendance (this term):</b> {attendance_line}", styles["Normal"]),
        Spacer(1, 4 * mm),
        Paragraph(f"<i>{DISCLAIMER}</i>", styles["Normal"]),
    ]


def _build(elements) -> bytes:
    buffer = BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4, title="Term Report Card", topMargin=20 * mm, bottomMargin=20 * mm
    ).build(elements)
    return buffer.getvalue()


def build_student_report_card(student, term, card, attendance) -> bytes:
    """One-page report card for one student and term."""
    styles = getSampleStyleSheet()
    return _build(_card_elements(student, term, card, attendance, styles))


def build_class_report_cards(school_class, term, cards) -> bytes:
    """One PDF for a whole class: one page per student.

    ``cards`` is a list of (student, report_card_data, attendance) tuples.
    """
    styles = getSampleStyleSheet()
    elements = []
    if not cards:
        elements.append(
            Paragraph(f"No students enrolled in {school_class.name}.", styles["Normal"])
        )
    for index, (student, card, attendance) in enumerate(cards):
        if index:
            elements.append(PageBreak())
        elements.extend(_card_elements(student, term, card, attendance, styles))
    return _build(elements)
