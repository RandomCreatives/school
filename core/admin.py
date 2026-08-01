from django.contrib import admin

from .models import Student, Teacher


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


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "hired_on")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
