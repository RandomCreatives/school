from datetime import date, timedelta

import pytest
from django.utils import timezone

from core import services
from core.models import AttendanceRecord
from tests.factories import AcademicYearFactory, AttendanceRecordFactory, SchoolClassFactory


@pytest.mark.django_db
class TestSaveAttendance:
    def test_writes_one_record_per_student_and_counts(self, school):
        students = school.students
        statuses = {students[0].id: "present", students[1].id: "absent", students[2].id: "late"}
        counts = services.save_attendance(
            school.school_class, timezone.localdate(), statuses, taken_by=school.teacher
        )
        assert counts == {"present": 1, "absent": 1, "late": 1}
        assert AttendanceRecord.objects.count() == 3
        record = AttendanceRecord.objects.get(student=students[1])
        assert record.status == "absent"
        assert record.taken_by == school.teacher

    def test_saving_again_updates_in_place(self, school):
        today = timezone.localdate()
        statuses = {s.id: "present" for s in school.students}
        services.save_attendance(school.school_class, today, statuses, taken_by=school.teacher)

        statuses[school.students[0].id] = "excused"
        services.save_attendance(school.school_class, today, statuses, taken_by=school.teacher)

        assert AttendanceRecord.objects.count() == 3
        assert AttendanceRecord.objects.get(student=school.students[0]).status == "excused"

    def test_future_date_rejected(self, school):
        with pytest.raises(ValueError, match="future"):
            services.save_attendance(
                school.school_class,
                timezone.localdate() + timedelta(days=1),
                {},
                taken_by=school.teacher,
            )

    def test_date_outside_the_year_rejected(self, school):
        with pytest.raises(ValueError, match="outside"):
            services.save_attendance(
                school.school_class, date(1999, 1, 1), {}, taken_by=school.teacher
            )

    def test_unknown_student_rejected(self, school):
        with pytest.raises(ValueError, match="not actively enrolled"):
            services.save_attendance(
                school.school_class,
                timezone.localdate(),
                {999999: "present"},
                taken_by=school.teacher,
            )

    def test_unknown_status_rejected_and_nothing_written(self, school):
        with pytest.raises(ValueError, match="Unknown attendance status"):
            services.save_attendance(
                school.school_class,
                timezone.localdate(),
                {school.students[0].id: "slept-in"},
                taken_by=school.teacher,
            )
        assert AttendanceRecord.objects.count() == 0


@pytest.mark.django_db
class TestAttendanceSummary:
    def test_counts_per_status_within_the_year(self, school):
        student = school.students[0]
        today = timezone.localdate()
        AttendanceRecordFactory(
            student=student, school_class=school.school_class, date=today, status="present"
        )
        AttendanceRecordFactory(
            student=student,
            school_class=school.school_class,
            date=today - timedelta(days=1),
            status="absent",
        )
        # a record outside the year doesn't count
        AttendanceRecordFactory(
            student=student,
            school_class=SchoolClassFactory(
                academic_year=AcademicYearFactory(start_date=date(2020, 1, 1),
                                                  end_date=date(2020, 12, 31))
            ),
            date=date(2020, 3, 3),
            status="absent",
        )
        summary = services.attendance_summary(student, school.year)
        assert summary == {"present": 1, "absent": 1, "late": 0, "excused": 0}

    def test_str(self, school):
        record = AttendanceRecordFactory(student=school.students[0],
                                         school_class=school.school_class)
        assert "Present" in str(record)
