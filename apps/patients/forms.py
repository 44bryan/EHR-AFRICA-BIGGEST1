from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Patient, NextOfKin, InsuranceInfo, MedicalHistory, Visit


CAMEROON_REGIONS = [
    ('', '-- Select Region --'),
    ('Adamawa', 'Adamawa'),
    ('Centre', 'Centre'),
    ('East', 'East (Est)'),
    ('Far North', 'Far North (Extrême-Nord)'),
    ('Littoral', 'Littoral'),
    ('North', 'North (Nord)'),
    ('North West', 'North West (Nord-Ouest)'),
    ('South', 'South (Sud)'),
    ('South West', 'South West (Sud-Ouest)'),
    ('West', 'West (Ouest)'),
]


class PatientRegistrationForm(forms.ModelForm):
    region = forms.ChoiceField(
        choices=CAMEROON_REGIONS, required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    # date_of_birth not required at form level — view handles approximate modes
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )

    class Meta:
        model = Patient
        fields = [
            'first_name', 'middle_name', 'last_name',
            'date_of_birth', 'gender', 'marital_status',
            'phone_number', 'phone_number_2', 'phone_is_whatsapp', 'email',
            'quarter', 'village_town', 'region', 'country',
            'nationality', 'occupation', 'religion',
            'blood_group', 'genotype', 'photo',
        ]
        widgets = {
            'first_name':       forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name':      forms.TextInput(attrs={'class': 'form-control'}),
            'last_name':        forms.TextInput(attrs={'class': 'form-control'}),
            'gender':           forms.Select(attrs={'class': 'form-select'}),
            'marital_status':   forms.Select(attrs={'class': 'form-select'}),
            'phone_number':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6XXXXXXXX'}),
            'phone_number_2':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6XXXXXXXX'}),
            'phone_is_whatsapp':forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email':            forms.EmailInput(attrs={'class': 'form-control'}),
            'quarter':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bastos, Biyem-Assi'}),
            'village_town':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Yaoundé, Douala'}),
            'country':          forms.TextInput(attrs={'class': 'form-control'}),
            'nationality':      forms.TextInput(attrs={'class': 'form-control'}),
            'occupation':       forms.TextInput(attrs={'class': 'form-control'}),
            'religion':         forms.TextInput(attrs={'class': 'form-control'}),
            'blood_group':      forms.Select(attrs={'class': 'form-select'}),
            'genotype':         forms.Select(attrs={'class': 'form-select'}),
        }


class NextOfKinForm(forms.ModelForm):
    class Meta:
        model = NextOfKin
        fields = ['full_name', 'relationship', 'phone_number', 'email', 'address']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'relationship': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Spouse, Parent, Sibling'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class MedicalHistoryForm(forms.ModelForm):
    class Meta:
        model = MedicalHistory
        exclude = ['patient', 'created_by', 'updated_by', 'created_at', 'updated_at', 'is_deleted', 'deleted_at', 'id']
        widgets = {
            'known_allergies': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Drug/food/environmental allergies. Enter NKDA if none.'}),
            'previous_eye_surgeries': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'previous_eye_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'spectacle_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'chronic_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'e.g. Diabetes Mellitus Type 2, Hypertension'}),
            'previous_surgeries': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'current_medications': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'family_ocular_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'social_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'systemic_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class VitalSignsForm(forms.Form):
    """Triage vital signs form."""
    visual_acuity_right = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6/6'}),
        label='VA Right Eye'
    )
    visual_acuity_left = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6/6'}),
        label='VA Left Eye'
    )
    intraocular_pressure_right = forms.CharField(
        max_length=10, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mmHg'}),
        label='IOP Right Eye (mmHg)'
    )
    intraocular_pressure_left = forms.CharField(
        max_length=10, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mmHg'}),
        label='IOP Left Eye (mmHg)'
    )
    iop_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control form-control-sm', 'type': 'time'}),
        label='IOP Time Taken'
    )
    blood_pressure = forms.CharField(
        max_length=15, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '120/80'}),
        label='Blood Pressure'
    )
    pulse = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'bpm'}),
        label='Pulse (bpm)'
    )
    temperature = forms.DecimalField(
        max_digits=4, decimal_places=1, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '°C', 'step': '0.1'}),
        label='Temperature (°C)'
    )
    weight = forms.DecimalField(
        max_digits=5, decimal_places=1, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'kg', 'step': '0.1'}),
        label='Weight (kg)'
    )
    height = forms.DecimalField(
        max_digits=5, decimal_places=1, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'cm', 'step': '0.1'}),
        label='Height (cm)'
    )
