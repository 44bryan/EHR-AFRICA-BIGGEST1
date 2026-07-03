from django import forms
from django.forms import inlineformset_factory
from .models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription

DOSE_CHOICES = [
    ('', '— Dose —'),
    ('1 drop', '1 drop'),
    ('2 drops', '2 drops'),
    ('3 drops', '3 drops'),
    ('1 tablet', '1 tablet'),
    ('2 tablets', '2 tablets'),
    ('1/2 tablet', '1/2 tablet'),
    ('1 capsule', '1 capsule'),
    ('2 capsules', '2 capsules'),
    ('1 application', '1 application'),
    ('1 sachet', '1 sachet'),
    ('5 ml', '5 ml'),
    ('10 ml', '10 ml'),
    ('1 ampule', '1 ampule'),
    ('1 unit', '1 unit'),
]

FREQUENCY_CHOICES = [
    ('', '— Frequency —'),
    ('OD', 'OD — Once daily'),
    ('BD', 'BD — Twice daily'),
    ('TDS', 'TDS — Three times daily'),
    ('QID', 'QID — Four times daily'),
    ('Q4H', 'Q4H — Every 4 hours'),
    ('Q6H', 'Q6H — Every 6 hours'),
    ('Q8H', 'Q8H — Every 8 hours'),
    ('Nocte', 'Nocte — At night'),
    ('Mane', 'Mane — Morning'),
    ('PRN', 'PRN — As needed'),
    ('STAT', 'STAT — Immediately'),
    ('Weekly', 'Weekly'),
    ('Twice weekly', 'Twice weekly'),
    ('Monthly', 'Monthly'),
    ('As directed', 'As directed'),
]

DURATION_CHOICES = [
    ('', '— Duration —'),
    ('1 day', '1 day'),
    ('2 days', '2 days'),
    ('3 days', '3 days'),
    ('5 days', '5 days'),
    ('7 days', '7 days (1 week)'),
    ('10 days', '10 days'),
    ('14 days', '14 days (2 weeks)'),
    ('3 weeks', '3 weeks'),
    ('4 weeks', '4 weeks (1 month)'),
    ('6 weeks', '6 weeks'),
    ('2 months', '2 months'),
    ('3 months', '3 months'),
    ('6 months', '6 months'),
    ('Until review', 'Until review'),
    ('Ongoing', 'Ongoing'),
]


class DrugPrescriptionForm(forms.ModelForm):
    class Meta:
        model = DrugPrescription
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Additional notes...'}),
        }


class DrugPrescriptionItemForm(forms.ModelForm):
    dose = forms.ChoiceField(
        choices=DOSE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    duration = forms.ChoiceField(
        choices=DURATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )

    class Meta:
        model = DrugPrescriptionItem
        fields = ['drug_name', 'drug_form', 'concentration', 'dose', 'frequency', 'duration', 'route', 'eye', 'quantity', 'special_instructions']
        widgets = {
            'drug_name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Drug name'}),
            'drug_form': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'concentration': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 0.5%'}),
            'route': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'eye': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 1}),
            'special_instructions': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 1}),
        }


DrugItemFormSet = inlineformset_factory(
    DrugPrescription,
    DrugPrescriptionItem,
    form=DrugPrescriptionItemForm,
    extra=3,
    can_delete=True,
)


class OpticalPrescriptionForm(forms.ModelForm):
    class Meta:
        model = OpticalPrescription
        exclude = ['consultation', 'patient', 'prescribed_by', 'prescription_date', 'is_dispensed',
                   'created_at', 'updated_at', 'created_by', 'updated_by', 'is_deleted', 'deleted_at', 'id']
        widgets = {
            'prescription_type': forms.Select(attrs={'class': 'form-select'}),
            're_sphere': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            're_cylinder': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '-0.00'}),
            're_axis': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 180, 'placeholder': '0–180'}),
            're_add': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            're_visual_acuity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6/6'}),
            're_sphere_near': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            're_cylinder_near': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            're_axis_near': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 180}),
            're_va_near': forms.TextInput(attrs={'class': 'form-control'}),
            'le_sphere': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            'le_cylinder': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '-0.00'}),
            'le_axis': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 180, 'placeholder': '0–180'}),
            'le_add': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            'le_visual_acuity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6/6'}),
            'le_sphere_near': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            'le_cylinder_near': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25'}),
            'le_axis_near': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 180}),
            'le_va_near': forms.TextInput(attrs={'class': 'form-control'}),
            'interpupillary_distance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'mm'}),
            'near_ipd': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'mm'}),
            'lens_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Single Vision, Progressive'}),
            'frame_advice': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
