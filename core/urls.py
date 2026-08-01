from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("attendance/<int:class_id>/", views.attendance_sheet, name="attendance-sheet"),
    path("sections/<int:section_id>/gradebook/", views.gradebook, name="gradebook"),
    path(
        "assessments/<int:assessment_id>/scores/",
        views.assessment_scores,
        name="assessment-scores",
    ),
    path("students/<int:student_id>/report/", views.student_report, name="student-report"),
]
