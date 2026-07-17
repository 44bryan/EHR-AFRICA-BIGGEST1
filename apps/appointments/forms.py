from django import forms
from .models import Appointment


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'department', 'doctor', 'appointment_date', 'appointment_time',
                  'appointment_type', 'service_tier', 'reason', 'duration_minutes', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'doctor': forms.Select(attrs={'class': 'form-select'}),
            'appointment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'appointment_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'appointment_type': forms.Select(attrs={'class': 'form-select'}),
            'service_tier': forms.Select(attrs={'class': 'form-select'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # department and doctor are optional — model allows null
        self.fields['department'].required = False
        self.fields['doctor'].required = False
        # service_tier has a model default (STANDARD); pre-select it so user doesn't get a required error
        self.fields['service_tier'].required = False
        self.fields['service_tier'].initial = 'STANDARD'
