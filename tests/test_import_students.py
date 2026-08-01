import io
from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Student

HEADER = (
    "student_id,first_name,last_name,date_of_birth,"
    "gender,guardian_name,guardian_phone,admission_date\n"
)
ROW = "S0001,Hana,Tesfaye,2013-03-14,F,Tesfaye Alemu,+251911234567,2023-09-11\n"


def write_csv(tmp_path, content):
    path = tmp_path / "students.csv"
    path.write_text(content)
    return path


def run_import(path, **kwargs):
    out = io.StringIO()
    call_command("import_students", path, stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
class TestImportStudents:
    def test_creates_students(self, tmp_path):
        run_import(write_csv(tmp_path, HEADER + ROW))
        student = Student.objects.get(student_id="S0001")
        assert student.first_name == "Hana"
        assert student.last_name == "Tesfaye"
        assert student.date_of_birth == date(2013, 3, 14)
        assert student.gender == Student.Gender.FEMALE
        assert student.guardian_name == "Tesfaye Alemu"
        assert student.admission_date == date(2023, 9, 11)

    def test_rerun_updates_instead_of_duplicating(self, tmp_path):
        path = write_csv(tmp_path, HEADER + ROW)
        run_import(path)
        path.write_text(HEADER + ROW.replace("Hana", "Hanan"))
        run_import(path)
        assert Student.objects.count() == 1
        assert Student.objects.get(student_id="S0001").first_name == "Hanan"

    def test_bad_rows_are_reported_and_good_rows_still_import(self, tmp_path):
        bad_row = "S0002,Yonas,Girma,not-a-date,M,,,\n"
        path = write_csv(tmp_path, HEADER + bad_row + ROW)
        with pytest.raises(CommandError, match="1 row"):
            call_command("import_students", path, stdout=io.StringIO(), stderr=io.StringIO())
        assert Student.objects.filter(student_id="S0001").exists()
        assert not Student.objects.filter(student_id="S0002").exists()

    def test_dry_run_writes_nothing(self, tmp_path):
        path = write_csv(tmp_path, HEADER + ROW)
        call_command("import_students", path, dry_run=True, stdout=io.StringIO())
        assert Student.objects.count() == 0

    def test_missing_required_column_rejected(self, tmp_path):
        path = write_csv(tmp_path, "student_id,first_name\nS0001,Hana\n")
        with pytest.raises(CommandError, match="Missing required columns"):
            call_command("import_students", path, stdout=io.StringIO())

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(CommandError, match="File not found"):
            call_command("import_students", tmp_path / "nope.csv", stdout=io.StringIO())
