from django.contrib import admin

from .models import (
    AcademicYear,
    Enrollment,
    SchoolClass,
    Section,
    Student,
    Subject,
    Teacher,
    Term,
)
from .services import generate_sections_for_class


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    autocomplete_fields = ("student",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "student_id",
        "last_name",
        "first_name",
        "gender",
        "status",
        "guardian_phone",
    )
    list_filter = ("status", "gender")
    search_fields = ("student_id", "first_name", "last_name", "guardian_name")
    ordering = ("last_name", "first_name")
    inlines = (EnrollmentInline,)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "hired_on")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)


class TermInline(admin.TabularInline):
    model = Term
    extra = 0  # the year's 3 terms are auto-created; just fill in dates


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_current")
    inlines = (TermInline,)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    autocomplete_fields = ("subject", "teacher")


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "homeroom_teacher", "enrollment_count")
    list_filter = ("academic_year", "grade_level")
    autocomplete_fields = ("homeroom_teacher",)
    inlines = (EnrollmentInline, SectionInline)
    actions = ("generate_sections",)

    @admin.display(description="Students")
    def enrollment_count(self, obj):
        return obj.enrollments.count()

    @admin.action(description="Generate sections (all subjects × terms)")
    def generate_sections(self, request, queryset):
        created = sum(generate_sections_for_class(school_class) for school_class in queryset)
        self.message_user(request, f"Created {created} section(s) — existing ones untouched.")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("subject", "school_class", "term", "teacher")
    list_filter = ("term__academic_year", "term", "subject")
    autocomplete_fields = ("subject", "teacher")
