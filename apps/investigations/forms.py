from django import forms
from .models import InvestigationOrder, InvestigationResult, InvestigationType


class InvestigationOrderForm(forms.ModelForm):
    # Explicitly declared so empty_label and queryset are guaranteed correct
    investigation_type = forms.ModelChoiceField(
        queryset=InvestigationType.objects.filter(is_active=True).order_by('category', 'name'),
        empty_label='--- Select Investigation Type ---',
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True,
    )

    class Meta:
        model = InvestigationOrder
        fields = ['investigation_type', 'urgency', 'clinical_indication', 'eye', 'notes']
        widgets = {
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
