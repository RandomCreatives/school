from django.conf import settings
from django.db import models


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
    """A staff member who teaches; linked 1:1 to a login account.

    Subject specialties arrive with the Subject model in M2.
    """

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
