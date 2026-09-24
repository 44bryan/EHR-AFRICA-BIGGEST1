from django import forms
from .models import (
    InvestigationOrder, InvestigationResult, InvestigationType, Laterality,
)


class InvestigationOrderForm(forms.ModelForm):
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


class MultiExamOrderForm(forms.Form):
    """
    Multi-select exam ordering form.
    Doctor selects multiple exam types at once + shared fields.
    For optometry/orthoptics: also selects who should perform the exam.
    """
    investigation_types = forms.ModelMultipleChoiceField(
        queryset=InvestigationType.objects.filter(is_active=True).order_by('category', 'name'),
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        error_messages={'required': 'Please select at least one exam.'},
    )
    urgency = forms.ChoiceField(
        choices=InvestigationOrder.Urgency.choices,
        initial='ROUTINE',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    eye = forms.ChoiceField(
        choices=Laterality.choices,
        initial='OU',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    clinical_indication = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=True,
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False,
    )
    # For optometry: who should perform
    assigned_to = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(),
    )


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


# ── Structured Optometry Result Forms ──────────────────────────────────────

class AutorefractionResultForm(forms.Form):
    """Autorefraction / Keratometry result entry."""
    # Right Eye (OD)
    sph_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_od = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    # Left Eye (OS)
    sph_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_os = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    # Keratometry
    k1_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': 'K1'}))
    k2_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': 'K2'}))
    k1_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': 'K1'}))
    k2_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': 'K2'}))
    pd = forms.DecimalField(max_digits=5, decimal_places=1, required=False,
                             widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': 'PD (mm)'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class SubjectiveRefractionResultForm(forms.Form):
    """Subjective/manifest refraction result entry."""
    # OD
    sph_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_od = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    add_od = forms.DecimalField(max_digits=5, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'ADD'}))
    best_va_od = forms.CharField(max_length=20, required=False,
                                  widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 6/6'}))
    # OS
    sph_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_os = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    add_os = forms.DecimalField(max_digits=5, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'ADD'}))
    best_va_os = forms.CharField(max_length=20, required=False,
                                  widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 6/6'}))
    # Binocular
    pd_dist = forms.DecimalField(max_digits=5, decimal_places=1, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': 'Dist PD'}))
    pd_near = forms.DecimalField(max_digits=5, decimal_places=1, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': 'Near PD'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class CycloplegicRefractionResultForm(forms.Form):
    """Cycloplegic refraction result entry."""
    cycloplegic_agent = forms.ChoiceField(
        choices=[('', '-- Select --'), ('CYCLOPENTOLATE', 'Cyclopentolate 1%'),
                 ('ATROPINE', 'Atropine 1%'), ('TROPICAMIDE', 'Tropicamide 1%'),
                 ('HOMATROPINE', 'Homatropine 2%')],
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    instillation_time = forms.TimeField(required=False,
                                         widget=forms.TimeInput(attrs={'class': 'form-control form-control-sm', 'type': 'time'}))
    exam_time = forms.TimeField(required=False,
                                 widget=forms.TimeInput(attrs={'class': 'form-control form-control-sm', 'type': 'time'}))
    # OD
    sph_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_od = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    # OS
    sph_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_os = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class ContactLensResultForm(forms.Form):
    """Contact lens assessment result."""
    cl_type = forms.ChoiceField(
        choices=[('', '-- Select --'), ('SOFT', 'Soft'), ('RGP', 'RGP'),
                 ('SCLERAL', 'Scleral'), ('HYBRID', 'Hybrid'), ('ORTHO_K', 'Ortho-K')],
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    # OD
    base_curve_od = forms.DecimalField(max_digits=4, decimal_places=2, required=False,
                                        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'placeholder': 'BC'}))
    diameter_od = forms.DecimalField(max_digits=4, decimal_places=1, required=False,
                                      widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'placeholder': 'Dia'}))
    power_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                   widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'Power'}))
    over_refraction_od = forms.CharField(max_length=30, required=False,
                                          widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Over-Rx'}))
    # OS
    base_curve_os = forms.DecimalField(max_digits=4, decimal_places=2, required=False,
                                        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'placeholder': 'BC'}))
    diameter_os = forms.DecimalField(max_digits=4, decimal_places=1, required=False,
                                      widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'placeholder': 'Dia'}))
    power_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                   widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'Power'}))
    over_refraction_os = forms.CharField(max_length=30, required=False,
                                          widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Over-Rx'}))
    fit_assessment = forms.ChoiceField(
        choices=[('', '-- Select --'), ('GOOD', 'Good fit'), ('TIGHT', 'Tight'),
                 ('LOOSE', 'Loose'), ('DECENTERED', 'Decentered')],
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class LensometryResultForm(forms.Form):
    """Current spectacle Rx reading with lensometer."""
    # OD
    sph_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_od = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_od = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    add_od = forms.DecimalField(max_digits=5, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'ADD'}))
    # OS
    sph_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'SPH'}))
    cyl_os = forms.DecimalField(max_digits=6, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'CYL'}))
    axis_os = forms.IntegerField(min_value=0, max_value=180, required=False,
                                  widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Axis'}))
    add_os = forms.DecimalField(max_digits=5, decimal_places=2, required=False,
                                 widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.25', 'placeholder': 'ADD'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


# ── Orthoptics Result Forms ────────────────────────────────────────────────

class MotilityResultForm(forms.Form):
    """Ocular motility and EOM assessment."""
    RATING = [('', '--'), ('FULL', 'Full'), ('RESTRICTED', 'Restricted'),
              ('OVERACTING', 'Overacting'), ('PARETIC', 'Paretic')]
    # Versions (9 gaze positions)
    sr_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    ir_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    mr_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    lr_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    so_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    io_od = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    sr_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    ir_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    mr_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    lr_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    so_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    io_os = forms.ChoiceField(choices=RATING, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    saccades = forms.ChoiceField(
        choices=[('', '--'), ('NORMAL', 'Normal'), ('SLOW', 'Slow'), ('HYPOMETRIC', 'Hypometric'),
                 ('HYPERMETRIC', 'Hypermetric')],
        required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    pursuits = forms.ChoiceField(
        choices=[('', '--'), ('SMOOTH', 'Smooth'), ('SACCADIC', 'Saccadic'), ('RESTRICTED', 'Restricted')],
        required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    nystagmus = forms.CharField(max_length=200, required=False,
                                 widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Describe if present'}))
    head_posture = forms.CharField(max_length=200, required=False,
                                    widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Abnormal head posture'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class CoverTestResultForm(forms.Form):
    """Cover test / prism cover test result."""
    DEVIATION_TYPE = [('', '--'), ('ORTHO', 'Orthophoria'), ('ESO', 'Esophoria/tropia'),
                      ('EXO', 'Exophoria/tropia'), ('HYPER', 'Hyperphoria/tropia'),
                      ('HYPO', 'Hypophoria/tropia')]
    # Distance
    dist_type = forms.ChoiceField(choices=DEVIATION_TYPE, required=False,
                                   widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    dist_amount_pd = forms.IntegerField(required=False,
                                         widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'PD'}))
    dist_vertical = forms.CharField(max_length=50, required=False,
                                     widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Vertical'}))
    # Near
    near_type = forms.ChoiceField(choices=DEVIATION_TYPE, required=False,
                                   widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    near_amount_pd = forms.IntegerField(required=False,
                                         widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'PD'}))
    near_vertical = forms.CharField(max_length=50, required=False,
                                     widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Vertical'}))
    with_correction = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class StereopsisResultForm(forms.Form):
    """Stereopsis test result."""
    test_used = forms.ChoiceField(
        choices=[('', '-- Select --'), ('TITMUS', 'Titmus'), ('RANDOT', 'Randot'),
                 ('LANG', 'Lang'), ('TNO', 'TNO'), ('FRISBY', 'Frisby')],
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        required=False,
    )
    result_seconds_arc = forms.IntegerField(required=False,
                                             widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Seconds of arc'}))
    grade = forms.ChoiceField(
        choices=[('', '--'), ('FINE', 'Fine (<60")'), ('MODERATE', 'Moderate (60-200")'),
                 ('GROSS', 'Gross (200-3000")'), ('NIL', 'Nil')],
        required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class NPCResultForm(forms.Form):
    """Near Point of Convergence result."""
    break_point_cm = forms.DecimalField(max_digits=5, decimal_places=1, required=False,
                                         widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': 'Break (cm)'}))
    recovery_point_cm = forms.DecimalField(max_digits=5, decimal_places=1, required=False,
                                            widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'placeholder': 'Recovery (cm)'}))
    method = forms.ChoiceField(
        choices=[('', '--'), ('PEN_LIGHT', 'Pen Light'), ('RAF_RULE', 'RAF Rule'),
                 ('ACCOMMODATION_TARGET', 'Accommodation Target')],
        required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class FusionalVergenceResultForm(forms.Form):
    """Prism bar / fusional vergence assessment."""
    # Base Out (convergence)
    bo_break_dist = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Break'}))
    bo_recovery_dist = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Rec'}))
    bo_break_near = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Break'}))
    bo_recovery_near = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Rec'}))
    # Base In (divergence)
    bi_break_dist = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Break'}))
    bi_recovery_dist = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Rec'}))
    bi_break_near = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Break'}))
    bi_recovery_near = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Rec'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class VisualAcuityResultForm(forms.Form):
    """Visual Acuity measurement — distance and near, aided and unaided."""
    _VA_CHOICES = [
        ('', '—'),
        ('10/10', '10/10'), ('10/12.5', '10/12.5'), ('10/16', '10/16'),
        ('10/20', '10/20'), ('10/25', '10/25'), ('10/32', '10/32'),
        ('10/40', '10/40'), ('10/50', '10/50'), ('10/63', '10/63'),
        ('10/80', '10/80'), ('10/100', '10/100'), ('10/125', '10/125'),
        ('10/160', '10/160'), ('10/200', '10/200'),
        ('CF', 'CF (Count Fingers)'), ('HM', 'HM (Hand Movement)'),
        ('LP', 'LP (Light Perception)'), ('NLP', 'NLP (No Light Perception)'),
    ]
    _NEAR_VA_CHOICES = [
        ('', '—'),
        ('N5', 'N5'), ('N6', 'N6'), ('N8', 'N8'), ('N10', 'N10'),
        ('N12', 'N12'), ('N14', 'N14'), ('N18', 'N18'), ('N24', 'N24'),
        ('N36', 'N36'), ('N48', 'N48'),
    ]
    _CHART_CHOICES = [
        ('', '—'),
        ('Snellen 6m', 'Snellen 6m'), ('Snellen 3m', 'Snellen 3m'),
        ('LogMAR', 'LogMAR'), ('E-chart', 'E-chart / Tumbling E'),
        ('Landolt C', 'Landolt C'), ('Picture chart', 'Picture chart (paediatric)'),
        ('Cardiff', 'Cardiff cards'),
    ]
    _va_sel = {'class': 'form-select form-select-sm'}
    # Distance VA
    unaided_od = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    unaided_os = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    aided_od = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    aided_os = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    pinhole_od = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    pinhole_os = forms.ChoiceField(choices=_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    # Near VA
    near_od = forms.ChoiceField(choices=_NEAR_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    near_os = forms.ChoiceField(choices=_NEAR_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    chart_used = forms.ChoiceField(choices=_CHART_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class LowVisionAssessmentForm(forms.Form):
    """Low Vision Assessment — functional vision, magnification, aids."""
    _LV_VA_CHOICES = [
        ('', '—'),
        ('10/10', '10/10'), ('10/12.5', '10/12.5'), ('10/16', '10/16'),
        ('10/20', '10/20'), ('10/25', '10/25'), ('10/32', '10/32'),
        ('10/40', '10/40'), ('10/50', '10/50'), ('10/63', '10/63'),
        ('10/80', '10/80'), ('10/100', '10/100'), ('10/125', '10/125'),
        ('10/160', '10/160'), ('10/200', '10/200'), ('10/400', '10/400'),
        ('CF', 'CF (Count Fingers)'), ('HM', 'HM (Hand Movement)'),
        ('LP', 'LP (Light Perception)'), ('NLP', 'NLP (No Light Perception)'),
    ]
    _NEAR_VA_CHOICES = [
        ('', '—'),
        ('N5', 'N5'), ('N6', 'N6'), ('N8', 'N8'), ('N10', 'N10'),
        ('N12', 'N12'), ('N14', 'N14'), ('N18', 'N18'), ('N24', 'N24'),
        ('N36', 'N36'), ('N48', 'N48'),
    ]
    _va_sel = {'class': 'form-select form-select-sm'}
    distance_va_od = forms.ChoiceField(choices=_LV_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    distance_va_os = forms.ChoiceField(choices=_LV_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    near_va_od = forms.ChoiceField(choices=_NEAR_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    near_va_os = forms.ChoiceField(choices=_NEAR_VA_CHOICES, required=False, widget=forms.Select(attrs=_va_sel))
    contrast_sensitivity = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. Normal / Reduced'}))
    magnification_required = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 4x'}))
    aids_tried = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'Magnifiers, telescopes, filters tried...'}), required=False)
    functional_goals = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'Reading, writing, mobility...'}), required=False)
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


class ColourVisionResultForm(forms.Form):
    """Colour Vision Test result."""
    test_used = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Ishihara / D-15 / Farnsworth'}))
    plates_correct_od = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 14/17'}))
    plates_correct_os = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. 14/17'}))
    result_od = forms.ChoiceField(choices=[('', '—'), ('NORMAL', 'Normal'), ('DEFICIENT', 'Deficient')], required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    result_os = forms.ChoiceField(choices=[('', '—'), ('NORMAL', 'Normal'), ('DEFICIENT', 'Deficient')], required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))
    deficiency_type = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Protan / Deutan / Tritan'}))
    notes = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}), required=False)


# Map investigation type codes to their structured form classes
STRUCTURED_RESULT_FORMS = {
    # Refraction exams
    'AUTOREF': AutorefractionResultForm,
    'AUTO-REF': AutorefractionResultForm,       # DB code alias
    'SUBJ-REF': SubjectiveRefractionResultForm,
    'REF': SubjectiveRefractionResultForm,       # DB code alias
    'DRY-REF': SubjectiveRefractionResultForm,
    'CYCLO-REF': CycloplegicRefractionResultForm,
    'CL-ASSESS': ContactLensResultForm,
    'LENSOMETRY': LensometryResultForm,
    'KERAT': AutorefractionResultForm,           # Keratometry uses autorefraction form (K readings)
    'VA': VisualAcuityResultForm,                # Visual Acuity
    'LVA': LowVisionAssessmentForm,              # Low Vision Assessment
    'COL': ColourVisionResultForm,               # Colour Vision Test
    # Orthoptics exams
    'COVER': CoverTestResultForm,
    'PRISM-COVER': CoverTestResultForm,
    'MUSC-BAL': CoverTestResultForm,             # DB code alias (muscle balance)
    'NPC': NPCResultForm,
    'NPA': NPCResultForm,
    'STEREO': StereopsisResultForm,
    'BIN-VIS': StereopsisResultForm,             # DB code alias (binocular vision)
    'MOTILITY': MotilityResultForm,
    'HESS': MotilityResultForm,                  # Hess chart uses motility form
    'PRISM-BAR': FusionalVergenceResultForm,
}
