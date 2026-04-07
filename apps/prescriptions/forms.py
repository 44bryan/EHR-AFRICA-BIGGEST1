from django import forms
from django.forms import inlineformset_factory
from .models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription


class DrugPrescriptionForm(forms.ModelForm):
    class Meta:
        model = DrugPrescription
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Additional notes...'}),
        }


class DrugPrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = DrugPrescriptionItem
        fields = ['drug_name', 'drug_form', 'concentration', 'dose', 'frequency', 'duration', 'route', 'eye', 'quantity', 'special_instructions']
        widgets = {
            'drug_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Drug name'}),
            'drug_form': forms.Select(attrs={'class': 'form-select'}),
            'concentration': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0.5%'}),
            'dose': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1 drop'}),
            'frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. TDS'}),
            'duration': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 7 days'}),
            'route': forms.Select(attrs={'class': 'form-select'}),
            'eye': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'special_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 1}),
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
            'le_sphere': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            'le_cylinder': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '-0.00'}),
            'le_axis': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 180, 'placeholder': '0–180'}),
            'le_add': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.25', 'placeholder': '+0.00'}),
            'le_visual_acuity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '6/6'}),
            'interpupillary_distance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'mm'}),
            'near_ipd': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'mm'}),
            'lens_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Single Vision, Progressive'}),
            'frame_advice': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
