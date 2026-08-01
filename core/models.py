from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Student(models.Model):
    """A student enrolled (or formerly enrolled) at the school."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LEFT = "left", "Left"
        GRADUATED = "graduated", "Graduated"

    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"

    student_id = models.CharField(max_length=20, unique=True, help_text="School-issued ID")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    guardian_name = models.CharField(max_length=200, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Teacher(models.Model):
    """A staff member who teaches; linked 1:1 to a login account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    phone = models.CharField(max_length=30, blank=True)
    hired_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class AcademicYear(models.Model):
    """A school year, e.g. "2024/25". Saving a new year auto-creates its
    3 terms — the school's fixed term structure (confirmed with the school)."""

    TERMS_PER_YEAR = 3

    name = models.CharField(max_length=20, unique=True, help_text='e.g. "2024/25"')
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False, help_text="Only one year can be current.")

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="single_current_academic_year",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "End date must be after start date."})

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.terms.exists():
            Term.objects.bulk_create(
                Term(academic_year=self, number=n) for n in range(1, self.TERMS_PER_YEAR + 1)
            )


class Term(models.Model):
    """One of the 3 terms within an academic year."""

    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="terms")
    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(AcademicYear.TERMS_PER_YEAR)]
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["academic_year", "number"]
        constraints = [
            models.UniqueConstraint(fields=["academic_year", "number"], name="unique_term_number")
        ]

    def __str__(self):
        return f"{self.academic_year} · Term {self.number}"

    def clean(self):
        super().clean()
        year = self.academic_year
        if year.pk:
            for field in ("start_date", "end_date"):
                value = getattr(self, field)
                if value and not (year.start_date <= value <= year.end_date):
                    raise ValidationError({field: f"Must fall within {year.name}."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})


class Subject(models.Model):
    """The subject catalog: Mathematics, English, Amharic, …"""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text='e.g. "MATH"')

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    """A homeroom group within an academic year, e.g. "Grade 7B"."""

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="classes"
    )
    grade_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    letter = models.CharField(max_length=2, help_text='Section letter, e.g. "B" in "Grade 7B"')
    homeroom_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="homeroom_classes",
        help_text="The 'main teacher' — takes morning attendance for this class.",
    )

    class Meta:
        ordering = ["grade_level", "letter"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "grade_level", "letter"],
                name="unique_class_per_year",
            ),
            models.UniqueConstraint(
                fields=["academic_year", "homeroom_teacher"],
                condition=Q(homeroom_teacher__isnull=False),
                name="one_homeroom_per_teacher_per_year",
            ),
        ]

    def __str__(self):
        return f"{self.name} · {self.academic_year}"

    @property
    def name(self):
        return f"Grade {self.grade_level}{self.letter}"

    def save(self, *args, **kwargs):
        self.letter = self.letter.strip().upper()
        super().save(*args, **kwargs)


class Section(models.Model):
    """A subject taught to a class in a term, by a (possibly not-yet-assigned)
    teacher: e.g. Mathematics · Grade 7B · Term 1.

    There is no per-student roster table: every student enrolled in the class
    is a member of all its sections. Students with individual subject choices
    would require a roster table — deferred until the school needs it.
    """

    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="sections")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="sections")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="sections")
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teaching_sections",
        help_text="May be assigned later, once staffing is decided.",
    )

    class Meta:
        ordering = [
            "school_class__grade_level",
            "school_class__letter",
            "subject__name",
            "term__number",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "subject", "term"], name="unique_section_offering"
            )
        ]

    def __str__(self):
        return f"{self.subject} · {self.school_class.name} · Term {self.term.number}"


class Enrollment(models.Model):
    """A student's membership in a class for an academic year.

    Section membership is *derived* from this, so enrolling a student places
    them in every section of the class automatically.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, related_name="enrollments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["school_class__grade_level", "school_class__letter", "student__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "school_class"], name="unique_enrollment")
        ]

    def __str__(self):
        return f"{self.student} in {self.school_class}"

    def clean(self):
        super().clean()
        if self.student_id and self.school_class_id:
            conflict = (
                Enrollment.objects.filter(
                    student=self.student,
                    school_class__academic_year=self.school_class.academic_year,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if conflict:
                raise ValidationError(
                    "This student is already enrolled in a class for "
                    f"{self.school_class.academic_year}."
                )

    @property
    def sections(self):
        """The sections this enrollment places the student in (derived)."""
        return self.school_class.sections.select_related("subject", "term", "teacher")
