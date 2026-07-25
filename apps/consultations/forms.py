from django import forms
from .models import Consultation, ConsultationNote, Diagnosis


class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = [
            'department',
            'presenting_complaint',
            'history_of_presenting_complaint',
            'ocular_history',
            'systemic_history',
            'drug_history',
            'family_history',
            'social_history',
            'management_plan',
            'follow_up_date',
            'follow_up_instructions',
            'referral_department',
            'referral_reason',
        ]
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'presenting_complaint': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'history_of_presenting_complaint': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'ocular_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'systemic_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'drug_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'family_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'social_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'management_plan': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'follow_up_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'follow_up_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'referral_department': forms.Select(attrs={'class': 'form-select'}),
            'referral_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # department is nullable in the model — allow form submission without it
        self.fields['department'].required = False


class ConsultationNoteForm(forms.ModelForm):
    class Meta:
        model = ConsultationNote
        fields = ['note_type', 'content']
        widgets = {
            'note_type': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter note...'}),
        }


class DiagnosisForm(forms.Form):
    """Add a diagnosis to a consultation."""
    diagnosis_id = forms.UUIDField(widget=forms.HiddenInput())
    is_primary = forms.BooleanField(required=False)
    laterality = forms.ChoiceField(
        choices=[('RE', 'Right Eye'), ('LE', 'Left Eye'), ('BE', 'Both Eyes'), ('NA', 'N/A')],
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Notes'})
    )
