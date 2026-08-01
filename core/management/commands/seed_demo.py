"""Scaffold a complete demo school in one command.

Creates a full year structure (3 terms with dates), 8 subjects, grades 1–8
with A/B classes and homeroom teachers, 24 students per class, 10 school days
of morning attendance, and assessments + scores for completed terms (plus a
partial start on the current term, so dashboard gaps are visible).

    python manage.py seed_demo            # refuses if data already exists
    python manage.py seed_demo --fresh    # wipes all app data, then seeds

Demo logins (demo only, never for production):
    office / office1234                 — office superuser
    <printed at the end>  / demo1234    — a Grade 7A homeroom teacher
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core import services
from core.models import (
    AcademicYear,
    Assessment,
    AttendanceRecord,
    Enrollment,
    SchoolClass,
    Score,
    Section,
    Student,
    Subject,
    Teacher,
    Term,
)

MALE_NAMES = [
    "Abel", "Yonas", "Dawit", "Samuel", "Henok", "Natnael", "Bereket", "Eyob",
    "Fikru", "Girma", "Kaleb", "Kirubel", "Melaku", "Tesfaye", "Wendimu",
    "Zelalem", "Biniyam", "Dagmawi", "Ermias", "Fitsum", "Getachew", "Amanuel",
    "Brook", "Nahom", "Robel", "Surafel", "Temesgen", "Yohannes", "Haile",
    "Mesfin",
]
FEMALE_NAMES = [
    "Hana", "Meron", "Sara", "Bethlehem", "Selam", "Tigist", "Almaz",
    "Frehiwot", "Hanna", "Mahlet", "Rediet", "Tsion", "Yordanos", "Zewditu",
    "Aster", "Chaltu", "Edom", "Feven", "Hirut", "Kidist", "Lulit", "Martha",
    "Mekdes", "Nardos", "Rahel", "Senait", "Sofia", "Wubalem", "Yemisrach",
    "Bezawit",
]
FATHER_NAMES = [
    "Bekele", "Tesfaye", "Girma", "Haile", "Kebede", "Mekonnen", "Alemu",
    "Tadesse", "Worku", "Asefa", "Desta", "Gebremariam", "Hailu", "Lemma",
    "Molla", "Negash", "Tsegaye", "Woldu", "Yimer", "Zewdu", "Abera",
    "Demeke", "Eshetu", "Fikadu", "Gebre", "Mulugeta", "Seifu", "Tilahun",
    "Wondimu", "Yilma", "Aschalew", "Belay", "Chala", "Derese", "Kassahun",
]
SUBJECTS = [
    ("English", "ENG"), ("Amharic", "AMH"), ("Mathematics", "MATH"),
    ("Science", "SCI"), ("Social Studies", "SOC"), ("HPE", "HPE"),
    ("ICT", "ICT"), ("Art", "ART"),
]
# Subjects whose current-term grading hasn't started — keeps the office
# dashboard's "sections without grades" card populated in the demo.
UNGRADED_THIS_TERM = {"ART", "HPE"}

GRADES = range(1, 9)
LETTERS = ("A", "B")
STUDENTS_PER_CLASS = 24
ATTENDANCE_DAYS = 10
DEMO_TEACHER_PASSWORD = "demo1234"

User = get_user_model()


def year_window(today):
    """The school year containing ``today``: Sep 1 – Aug 31."""
    start_year = today.year if today.month >= 9 else today.year - 1
    return start_year, date(start_year, 9, 1), date(start_year + 1, 8, 31)


def term_bounds(start_year):
    return [
        (date(start_year, 9, 1), date(start_year, 12, 31)),
        (date(start_year + 1, 1, 1), date(start_year + 1, 4, 30)),
        (date(start_year + 1, 5, 1), date(start_year + 1, 8, 31)),
    ]


def recent_school_days(today, count):
    days = []
    current = today
    while len(days) < count:
        if current.weekday() < 5:  # Mon–Fri
            days.append(current)
        current -= timedelta(days=1)
    return days


class Command(BaseCommand):
    help = "Seed a complete demo school (see module docstring for logins)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Wipe all existing app data before seeding.",
        )

    def handle(self, fresh=False, **options):
        random.seed(20260801)
        if Student.objects.exists() and not fresh:
            raise CommandError(
                "Data already exists — rerun with --fresh to wipe and reseed."
            )
        with transaction.atomic():
            if fresh:
                self._wipe()
            summary = self._seed()
        for line in summary:
            self.stdout.write(line)

    def _wipe(self):
        self.stdout.write("Wiping existing data…")
        for model in (
            Score, Assessment, AttendanceRecord, Enrollment, Section,
            SchoolClass, Term, AcademicYear, Subject, Student, Teacher,
        ):
            model.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def _seed(self):
        today = timezone.localdate()
        start_year, year_start, year_end = year_window(today)

        year = AcademicYear.objects.create(
            name=f"{start_year}/{str(start_year + 1)[2:]}",
            start_date=year_start,
            end_date=year_end,
            is_current=True,
        )
        bounds = term_bounds(start_year)
        for term, (term_start, term_end) in zip(year.terms.all(), bounds, strict=True):
            term.start_date = term_start
            term.end_date = term_end
            term.save()

        subjects = [
            Subject.objects.create(name=name, code=code) for name, code in SUBJECTS
        ]

        teacher_hash = make_password(DEMO_TEACHER_PASSWORD)
        teachers = []
        for _ in range(len(GRADES) * len(LETTERS)):
            first = random.choice(MALE_NAMES + FEMALE_NAMES)
            last = random.choice(FATHER_NAMES)
            username = f"{first}.{last}".lower()
            suffix = 1
            while User.objects.filter(username=username).exists():
                suffix += 1
                username = f"{first}.{last}{suffix}".lower()
            user = User(
                username=username, first_name=first, last_name=last,
                password=teacher_hash,
            )
            user.save()
            teachers.append(Teacher.objects.create(user=user))

        classes = []
        teacher_iter = iter(teachers)
        for grade in GRADES:
            for letter in LETTERS:
                classes.append(SchoolClass.objects.create(
                    academic_year=year,
                    grade_level=grade,
                    letter=letter,
                    homeroom_teacher=next(teacher_iter),
                ))
        for school_class in classes:
            services.generate_sections_for_class(school_class)

        # Spread section teaching across the staff, deterministically.
        all_sections = list(Section.objects.select_related("school_class"))
        for index, section in enumerate(all_sections):
            section.teacher_id = teachers[index % len(teachers)].id
        Section.objects.bulk_update(all_sections, ["teacher"])

        # Students + enrollments.
        student_counter = 0
        students_by_class = {}
        for school_class in classes:
            new_students = []
            for _ in range(STUDENTS_PER_CLASS):
                student_counter += 1
                gender = random.choice(["F", "M"])
                first = random.choice(FEMALE_NAMES if gender == "F" else MALE_NAMES)
                father = random.choice(FATHER_NAMES)
                birth_year = start_year - (school_class.grade_level + 6) + random.randint(0, 1)
                new_students.append(Student(
                    student_id=f"S{student_counter:04d}",
                    first_name=first,
                    last_name=father,
                    date_of_birth=date(
                        birth_year, random.randint(1, 12), random.randint(1, 28)
                    ),
                    gender=gender,
                    guardian_name=f"{father} {random.choice(FATHER_NAMES)}",
                    guardian_phone=f"+2519{random.randint(10_000_000, 99_999_999)}",
                    admission_date=date(start_year - school_class.grade_level + 1, 9, 5),
                ))
            Student.objects.bulk_create(new_students)
            Enrollment.objects.bulk_create(
                Enrollment(student=student, school_class=school_class)
                for student in new_students
            )
            students_by_class[school_class.id] = new_students

        # Attendance for the last ATTENDANCE_DAYS school days (incl. today).
        attendance = []
        for school_class in classes:
            for day in recent_school_days(today, ATTENDANCE_DAYS):
                for student in students_by_class[school_class.id]:
                    roll = random.random()
                    status = (
                        "absent" if roll < 0.03
                        else "late" if roll < 0.07
                        else "excused" if roll < 0.08
                        else "present"
                    )
                    attendance.append(AttendanceRecord(
                        school_class=school_class, student_id=student.id, date=day,
                        status=status, taken_by_id=school_class.homeroom_teacher_id,
                    ))
        AttendanceRecord.objects.bulk_create(attendance, batch_size=1000)

        # Assessments + scores: full grading for completed terms, a partial
        # start on the current one (some subjects intentionally ungraded).
        def school_day_between(start, end):
            while True:
                day = start + timedelta(days=random.randint(0, (end - start).days))
                if day.weekday() < 5:
                    return day

        score_batch = []
        for term in year.terms.all():
            if term.end_date < today:
                plan = [("Quiz 1", 1), ("Quiz 2", 1), ("Midterm Exam", 2)]
            else:
                plan = [("Quiz 1", 1)]
            for section in [s for s in all_sections if s.term_id == term.id]:
                if term.end_date >= today and section.subject.code in UNGRADED_THIS_TERM:
                    continue
                window_end = min(term.end_date, today)
                assessments = [
                    Assessment.objects.create(
                        section=section, name=name, weight=weight,
                        date=school_day_between(term.start_date, window_end),
                    )
                    for name, weight in plan
                ]
                students = students_by_class[section.school_class_id]
                for assessment in assessments:
                    for student in students:
                        value = max(35, min(100, round(random.gauss(76, 13) * 2) / 2))
                        score_batch.append(Score(
                            assessment=assessment, student_id=student.id,
                            value=Decimal(str(value)),
                        ))
                        if len(score_batch) >= 2000:
                            Score.objects.bulk_create(score_batch)
                            score_batch = []
        if score_batch:
            Score.objects.bulk_create(score_batch)

        office, _ = User.objects.get_or_create(
            username="office", defaults={"is_staff": True, "is_superuser": True}
        )
        office.set_password("office1234")
        office.is_staff = office.is_superuser = True
        office.save()

        showcase = SchoolClass.objects.get(grade_level=7, letter="A").homeroom_teacher
        return [
            "Demo school seeded:",
            f"  Year {year} ({year_start} → {year_end}), 3 terms with dates",
            f"  {len(subjects)} subjects · {len(classes)} classes (grades 1–8, A/B)",
            f"  {len(teachers)} teachers · {student_counter} students enrolled",
            f"  {Section.objects.count()} sections · {Assessment.objects.count()} assessments",
            f"  {Score.objects.count()} scores · "
            f"{AttendanceRecord.objects.count()} attendance records",
            "",
            "Log in (demo passwords only):",
            "  office / office1234        → office dashboard, admin, all PDFs",
            f"  {showcase.user.username} / {DEMO_TEACHER_PASSWORD}  → Grade 7A homeroom teacher",
        ]
