from django import forms
from .models import LabOrder, SampleCollection


class LabOrderForm(forms.ModelForm):
    class Meta:
        model = LabOrder
        fields = ['urgency', 'clinical_indication', 'notes']
        widgets = {
            'urgency': forms.Select(attrs={'class': 'form-select'}),
            'clinical_indication': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class SampleCollectionForm(forms.ModelForm):
    class Meta:
        model = SampleCollection
        fields = ['sample_type', 'notes']
        widgets = {
            'sample_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class LabResultFormSet:
    """Handled manually in the view for flexibility."""
    pass
