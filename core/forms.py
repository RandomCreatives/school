from django import forms

from .models import Assessment


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["name", "date", "weight", "max_score"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }
