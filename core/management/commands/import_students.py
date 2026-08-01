"""Import or update students from a CSV file.

Upserts by ``student_id``: rows with an existing ID update that student,
new IDs create students. Bad rows are reported and skipped without
aborting the import.

Expected columns (header row required)::

    student_id,first_name,last_name,date_of_birth,gender,guardian_name,guardian_phone,admission_date

``guardian_name``, ``guardian_phone`` and ``admission_date`` are optional.
Dates are ``YYYY-MM-DD``; gender is ``F`` or ``M``.
"""
import csv
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Student

REQUIRED_COLUMNS = {"student_id", "first_name", "last_name", "date_of_birth", "gender"}


def _parse_date(value, field):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from None


def parse_row(row):
    """Validate one CSV row and return (student_id, defaults) for an upsert."""
    student_id = (row.get("student_id") or "").strip()
    if not student_id:
        raise ValueError("student_id is required")

    first_name = (row.get("first_name") or "").strip()
    last_name = (row.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise ValueError("first_name and last_name are required")

    gender = (row.get("gender") or "").strip().upper()
    if gender not in {Student.Gender.FEMALE, Student.Gender.MALE}:
        raise ValueError(f"gender must be F or M, got {gender!r}")

    date_of_birth = _parse_date(row.get("date_of_birth"), "date_of_birth")
    if date_of_birth is None:
        raise ValueError("date_of_birth is required")

    return student_id, {
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": date_of_birth,
        "gender": gender,
        "guardian_name": (row.get("guardian_name") or "").strip(),
        "guardian_phone": (row.get("guardian_phone") or "").strip(),
        "admission_date": _parse_date(row.get("admission_date"), "admission_date"),
    }


class Command(BaseCommand):
    help = "Import or update students from a CSV file (upsert by student_id)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path, help="Path to the CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report counts without writing to the database.",
        )

    def handle(self, csv_path, dry_run=False, **options):
        if not csv_path.is_file():
            raise CommandError(f"File not found: {csv_path}")

        created = updated = 0
        errors = []

        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing required columns: {', '.join(sorted(missing))}")

            with transaction.atomic():
                for line, row in enumerate(reader, start=2):  # line 1 is the header
                    try:
                        student_id, defaults = parse_row(row)
                    except ValueError as exc:
                        errors.append(f"line {line}: {exc}")
                        continue
                    _, was_created = Student.objects.update_or_create(
                        student_id=student_id, defaults=defaults
                    )
                    created += was_created
                    updated += not was_created
                if dry_run:
                    transaction.set_rollback(True)

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(f"{verb} {created}, updated {updated}, skipped {len(errors)} row(s).")
        for error in errors:
            self.stderr.write(self.style.WARNING(error))
        if errors:
            raise CommandError(f"{len(errors)} row(s) failed validation; see above.")
