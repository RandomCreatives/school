import factory
from django.contrib.auth import get_user_model

from core.models import Student, Teacher


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")


class StudentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Student

    student_id = factory.Sequence(lambda n: f"S{n:04d}")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    date_of_birth = factory.Faker("date_of_birth", minimum_age=6, maximum_age=18)
    gender = factory.Iterator([Student.Gender.FEMALE, Student.Gender.MALE])


class TeacherFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Teacher

    user = factory.SubFactory(UserFactory)
