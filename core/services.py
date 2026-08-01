"""Business operations that span models — kept out of views and admin.

Add attendance/gradebook operations here in M3.
"""
from .models import Section, Subject


def generate_sections_for_class(school_class) -> int:
    """Create sections for every subject × every term of the class's year.

    Idempotent: existing sections (and their teacher assignments) are left
    untouched. Returns the number of sections created.
    """
    created = 0
    for term in school_class.academic_year.terms.all():
        for subject in Subject.objects.all():
            _, was_created = Section.objects.get_or_create(
                school_class=school_class, subject=subject, term=term
            )
            created += was_created
    return created
