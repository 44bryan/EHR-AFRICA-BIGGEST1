from django import forms
from .models import InvestigationOrder, InvestigationResult


class InvestigationOrderForm(forms.ModelForm):
    class Meta:
        model = InvestigationOrder
        fields = ['investigation_type', 'urgency', 'clinical_indication', 'eye', 'notes']
        widgets = {
            'investigation_type': forms.Select(attrs={'class': 'form-select'}),
            'urgency': forms.Select(attrs={'class': 'form-select'}),
            'clinical_indication': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'eye': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class InvestigationResultForm(forms.ModelForm):
    result_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label='Upload File (image or PDF)',
    )

    class Meta:
        model = InvestigationResult
        fields = ['interpretation', 'is_normal']
        widgets = {
            'interpretation': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'is_normal': forms.Select(
                choices=[('', '-- Select --'), (True, 'Normal'), (False, 'Abnormal')],
                attrs={'class': 'form-select'},
            ),
        }
