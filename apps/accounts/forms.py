from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field, HTML
from .models import User


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_('Username'),
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter your username',
            'autofocus': True,
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
            'id': 'id_password',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_tag = False


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'username',
            'employee_id', 'role', 'department', 'phone_number', 'profile_photo',
            'cashier_station', 'consultation_unit', 'patient_tier',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select', 'id': 'id_role'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'cashier_station': forms.Select(attrs={'class': 'form-select', 'id': 'id_cashier_station'}),
            'consultation_unit': forms.Select(attrs={'class': 'form-select', 'id': 'id_consultation_unit'}),
            'patient_tier': forms.Select(attrs={'class': 'form-select', 'id': 'id_patient_tier'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make email, phone and employee_id optional
        self.fields['email'].required = False
        self.fields['phone_number'].required = False
        self.fields['employee_id'].required = False

    def clean_cashier_station(self):
        # Always return a valid non-empty value — default to 'ALL' for non-cashier roles
        val = self.cleaned_data.get('cashier_station')
        return val if val else 'ALL'

    def clean_patient_tier(self):
        val = self.cleaned_data.get('patient_tier')
        return val if val else 'ALL'

    def clean_email(self):
        val = (self.cleaned_data.get('email') or '').strip()
        return val if val else None

    def clean_employee_id(self):
        val = (self.cleaned_data.get('employee_id') or '').strip()
        if not val:
            return None
        # Check uniqueness only if a value is provided
        qs = User.objects.filter(employee_id=val)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A user with this employee ID already exists.')
        return val

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.must_change_password = False
        # Guarantee cashier_station is never empty — the DB column is NOT NULL
        if not user.cashier_station:
            user.cashier_station = 'ALL'
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email',
            'role', 'department', 'phone_number', 'profile_photo', 'is_active',
            'cashier_station', 'consultation_unit', 'patient_tier', 'can_do_reception', 'can_do_refraction',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select', 'id': 'id_role'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'cashier_station': forms.Select(attrs={'class': 'form-select', 'id': 'id_cashier_station'}),
            'consultation_unit': forms.Select(attrs={'class': 'form-select', 'id': 'id_consultation_unit'}),
            'patient_tier': forms.Select(attrs={'class': 'form-select', 'id': 'id_patient_tier'}),
        }

    def clean_email(self):
        val = (self.cleaned_data.get('email') or '').strip()
        return val if val else None

    def clean_cashier_station(self):
        val = self.cleaned_data.get('cashier_station')
        return val if val else 'ALL'

    def clean_patient_tier(self):
        val = self.cleaned_data.get('patient_tier')
        return val if val else 'ALL'


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'profile_photo', 'signature']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }
