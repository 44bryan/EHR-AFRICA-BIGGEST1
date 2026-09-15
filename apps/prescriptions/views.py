import json
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_GET
from django.utils import timezone
from .models import DrugPrescription, DrugPrescriptionItem, OpticalPrescription
from .forms import DrugPrescriptionForm, DrugItemFormSet, OpticalPrescriptionForm
from apps.consultations.models import Consultation
from apps.core.context_processors import qms_active as _qms_active


def _auto_route_to_pharmacy(consultation, issued_by):
    """
    After a drug prescription is saved, automatically route the patient to pharmacy:
      - Update visit status → PHARMACY
      - Update visit department → Pharmacy dept (if it exists)
      - If QMS is on, create a PHARMACY queue token
    Safe to call multiple times — skips if visit is already at PHARMACY or beyond.
    """
    try:
        visit = getattr(consultation, 'visit', None)
        if not visit:
            return
        # Don't re-route if patient already left pharmacy or further along
        skip_statuses = {'PHARMACY', 'BILLING', 'COMPLETED', 'DISCHARGED',
                         'COUNSELING', 'ADMITTED', 'IN_THEATRE'}
        if visit.status in skip_statuses:
            return

        from apps.departments.models import Department
        pharmacy_dept = Department.objects.filter(code='PHARMACY', is_active=True).first()

        visit.status = 'PHARMACY'
        update_fields = ['status', 'updated_at']
        if pharmacy_dept:
            visit.department = pharmacy_dept
            update_fields.append('department')
        visit.save(update_fields=update_fields)

        # QMS token for pharmacy queue (only when QMS is on)
        if _qms_active():
            try:
                from apps.qms.models import (
                    QueueToken, DailyTokenSequence, IssuancePoint, TokenStatus
                )
                token_number = DailyTokenSequence.next_dept_token('PHARMACY')
                QueueToken.objects.create(
                    token_number=token_number,
                    service_type='PHARMACY',
                    patient=consultation.patient,
                    visit=visit,
                    service_tier=visit.service_tier if hasattr(visit, 'service_tier') else 'STANDARD',
                    issuance_point=IssuancePoint.SYSTEM,
                    status=TokenStatus.WAITING,
                    created_by=issued_by,
                )
            except Exception:
                pass
    except Exception:
        pass  # Never block prescription save


def _check_allergy(patient, drug_name):
    """
    Return list of matching PatientAllergy records for this drug name.
    Matches if the allergen name appears in the drug name or vice-versa (case-insensitive).
    """
    from apps.patients.models import PatientAllergy
    allergens = PatientAllergy.objects.filter(patient=patient)
    drug_lower = drug_name.lower()
    return [a for a in allergens if a.allergen.lower() in drug_lower or drug_lower in a.allergen.lower()]


@login_required
def drug_prescription_new(request, consultation_pk):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)

    patient = consultation.patient
    allergies = list(patient.allergies.all())

    if request.method == 'POST':
        form = DrugPrescriptionForm(request.POST)
        formset = DrugItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            prescription = form.save(commit=False)
            prescription.consultation = consultation
            prescription.patient = patient
            prescription.prescribed_by = request.user
            prescription.created_by = request.user
            prescription.save()
            formset.instance = prescription
            formset.save()
            # Allergy check across all saved items
            for item in prescription.items.all():
                hits = _check_allergy(patient, item.drug_name)
                for a in hits:
                    messages.warning(
                        request,
                        f"⚠️ ALLERGY ALERT: {item.drug_name} may match recorded allergy "
                        f"'{a.allergen}' ({a.get_severity_display()}). Verify before dispensing."
                    )
            _auto_route_to_pharmacy(consultation, request.user)
            messages.success(request, 'Drug prescription created. Patient routed to Pharmacy.')
            return redirect('consultations:detail', pk=consultation_pk)
    else:
        form = DrugPrescriptionForm()
        formset = DrugItemFormSet()

    # Pharmacy drugs with current stock — for the select dropdown
    from apps.pharmacy.models import Drug
    stocked_drugs = Drug.objects.filter(
        is_active=True, is_deleted=False,
        stock_items__expiry_date__gte=timezone.localdate(),
        stock_items__quantity_remaining__gt=0,
        stock_items__is_deleted=False,
    ).distinct().order_by('name')
    drugs_json = json.dumps([{
        'name': str(d),
        'strength': d.strength,
        'form': d.form,
        'stock': d.current_stock,
    } for d in stocked_drugs])

    return render(request, 'prescriptions/drug_form.html', {
        'form': form,
        'formset': formset,
        'consultation': consultation,
        'allergies': allergies,
        'drugs_json': drugs_json,
    })


@login_required
def drug_prescription_detail(request, pk):
    prescription = get_object_or_404(DrugPrescription.objects.prefetch_related('items'), pk=pk)
    return render(request, 'prescriptions/drug_detail.html', {'prescription': prescription})


@login_required
def optical_prescription_new(request, consultation_pk):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)
    refraction_hint = None

    if request.method == 'POST':
        form = OpticalPrescriptionForm(request.POST)
        if form.is_valid():
            rx = form.save(commit=False)
            rx.consultation = consultation
            rx.patient = consultation.patient
            rx.prescribed_by = request.user
            rx.created_by = request.user
            rx.save()
            # Auto-route patient to Optical
            try:
                visit = getattr(consultation, 'visit', None)
                if visit:
                    skip = {'OPTICAL', 'BILLING', 'COMPLETED', 'DISCHARGED',
                            'COUNSELING', 'ADMITTED', 'IN_THEATRE'}
                    if visit.status not in skip:
                        from apps.departments.models import Department
                        from apps.core.patient_flow import close_stage_token as _close_opt
                        _close_opt(visit.patient, prev_status=visit.status)
                        opt_dept = Department.objects.filter(code='OPTICAL', is_active=True).first()
                        visit.status = 'OPTICAL'
                        update_fields = ['status', 'updated_at']
                        if opt_dept:
                            visit.department = opt_dept
                            update_fields.append('department')
                        visit.save(update_fields=update_fields)
                        if _qms_active():
                            try:
                                from apps.qms.models import (
                                    QueueToken, DailyTokenSequence, IssuancePoint, TokenStatus
                                )
                                token_number = DailyTokenSequence.next_dept_token('OPTICAL')
                                QueueToken.objects.create(
                                    token_number=token_number,
                                    service_type='OPTICAL',
                                    patient=consultation.patient,
                                    visit=visit,
                                    service_tier=visit.service_tier if hasattr(visit, 'service_tier') else 'STANDARD',
                                    issuance_point=IssuancePoint.SYSTEM,
                                    status=TokenStatus.WAITING,
                                    created_by=request.user,
                                )
                            except Exception:
                                pass
            except Exception:
                pass
            messages.success(request, 'Optical prescription created. Patient routed to Optical.')
            return redirect('consultations:detail', pk=consultation_pk)
    else:
        # Pre-fill from refractionist data if available for the same visit
        initial = {}
        refraction_hint = None
        try:
            from apps.consultations.models import Consultation as _C
            visit = getattr(consultation, 'visit', None)
            if visit:
                ref_consult = _C.objects.filter(
                    visit=visit,
                    consulting_doctor__role__in=['optometrist', 'pediatric_refractionist', 'orthoptist'],
                    is_deleted=False,
                ).order_by('-consultation_date').first()
                if not ref_consult:
                    # Fall back to any REFRAC/PEDS_REFRAC dept consultation this visit
                    ref_consult = _C.objects.filter(
                        visit=visit,
                        department__code__in=['REFRAC', 'PEDS_REFRAC'],
                        is_deleted=False,
                    ).order_by('-consultation_date').first()
                if ref_consult:
                    d = ref_consult.department_specific_data or {}
                    # Refractionist stores final Rx as final_sph_od/os, final_cyl_od/os, final_axis_od/os
                    # IPD stored as pd_dist_od + pd_dist_os (split PD)
                    # Support both new field names (pg_*) and old fallback names
                    pd_od = d.get('pd_od') or d.get('pd_dist_od', '')
                    pd_os = d.get('pd_os') or d.get('pd_dist_os', '')
                    # Use single numeric value only — combined "od/os" format fails DecimalField
                    if pd_od and not pd_os:
                        ipd = pd_od
                    elif pd_os and not pd_od:
                        ipd = pd_os
                    else:
                        ipd = ''  # Both monocular PDs present — leave blank for manual entry
                    initial = {
                        're_sphere':    (d.get('pg_sph_dist_od') or d.get('sub_sph_dist_od')
                                         or d.get('final_sph_od', '')),
                        're_cylinder':  (d.get('pg_cyl_dist_od') or d.get('sub_cyl_dist_od')
                                         or d.get('final_cyl_od', '')),
                        're_axis':      (d.get('pg_axis_dist_od') or d.get('sub_axis_dist_od')
                                         or d.get('final_axis_od', '')),
                        're_add':       (d.get('sub_add_od') or d.get('pg_add_od')
                                         or d.get('add_od', '')),
                        're_visual_acuity': (d.get('pg_va_dist_od') or d.get('sub_va_dist_od')
                                             or d.get('bcva_od')
                                             or d.get('va_corrected_od', '')),
                        're_sphere_near':   (d.get('pg_sph_near_od')
                                             or d.get('sub_sph_near_od', '')),
                        're_cylinder_near': (d.get('pg_cyl_near_od')
                                             or d.get('sub_cyl_near_od', '')),
                        're_axis_near':     (d.get('pg_axis_near_od')
                                             or d.get('sub_axis_near_od', '')),
                        're_va_near':       (d.get('pg_va_near_od')
                                             or d.get('sub_va_near_od', '')),
                        'le_sphere':    (d.get('pg_sph_dist_os') or d.get('sub_sph_dist_os')
                                         or d.get('final_sph_os', '')),
                        'le_cylinder':  (d.get('pg_cyl_dist_os') or d.get('sub_cyl_dist_os')
                                         or d.get('final_cyl_os', '')),
                        'le_axis':      (d.get('pg_axis_dist_os') or d.get('sub_axis_dist_os')
                                         or d.get('final_axis_os', '')),
                        'le_add':       (d.get('sub_add_os') or d.get('pg_add_os')
                                         or d.get('add_os', '')),
                        'le_visual_acuity': (d.get('pg_va_dist_os') or d.get('sub_va_dist_os')
                                             or d.get('bcva_os')
                                             or d.get('va_corrected_os', '')),
                        'le_sphere_near':   (d.get('pg_sph_near_os')
                                             or d.get('sub_sph_near_os', '')),
                        'le_cylinder_near': (d.get('pg_cyl_near_os')
                                             or d.get('sub_cyl_near_os', '')),
                        'le_axis_near':     (d.get('pg_axis_near_os')
                                             or d.get('sub_axis_near_os', '')),
                        'le_va_near':       (d.get('pg_va_near_os')
                                             or d.get('sub_va_near_os', '')),
                        'lens_type':              d.get('lens_type', ''),
                        'interpupillary_distance': ipd,
                    }
                    # Also check near PD
                    pd_near_od = d.get('pd_near_od', '')
                    pd_near_os = d.get('pd_near_os', '')
                    if pd_near_od and not pd_near_os:
                        initial['near_ipd'] = pd_near_od
                    elif pd_near_os and not pd_near_od:
                        initial['near_ipd'] = pd_near_os
                    # Remove blank values so form doesn't override model defaults
                    initial = {k: v for k, v in initial.items() if v}
                    refraction_hint = ref_consult.consulting_doctor.full_name
        except Exception:
            pass
        form = OpticalPrescriptionForm(initial=initial)

    return render(request, 'prescriptions/optical_form.html', {
        'form': form,
        'consultation': consultation,
        'refraction_hint': refraction_hint,
    })


@login_required
def optical_prescription_detail(request, pk):
    rx = get_object_or_404(OpticalPrescription, pk=pk)
    return render(request, 'prescriptions/optical_detail.html', {'rx': rx})


@login_required
def inline_drug_prescribe(request, consultation_pk):
    """
    Quick inline prescription — single drug added directly from consultation detail tab.
    POST-only. Creates DrugPrescription + one DrugPrescriptionItem, then redirects back.
    """
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk, is_deleted=False)

    if request.method != 'POST':
        return redirect('consultations:detail', pk=consultation_pk)

    drug_name = request.POST.get('drug_name', '').strip()
    if not drug_name:
        messages.error(request, 'Drug name is required.')
        return redirect('consultations:detail', pk=consultation_pk)

    # Allergy check before saving
    allergy_hits = _check_allergy(consultation.patient, drug_name)
    for a in allergy_hits:
        messages.warning(
            request,
            f"⚠️ ALLERGY ALERT: {drug_name} may match recorded allergy "
            f"'{a.allergen}' ({a.get_severity_display()}). Verify before dispensing."
        )

    prescription = DrugPrescription.objects.create(
        consultation=consultation,
        patient=consultation.patient,
        prescribed_by=request.user,
        created_by=request.user,
        notes=request.POST.get('rx_notes', '').strip(),
    )
    DrugPrescriptionItem.objects.create(
        prescription=prescription,
        drug_name=drug_name,
        drug_form=request.POST.get('drug_form', 'OTHER'),
        concentration=request.POST.get('concentration', '').strip(),
        dose=request.POST.get('dose', '').strip() or '1 application',
        frequency=request.POST.get('frequency', '').strip() or 'As directed',
        duration=request.POST.get('duration', '').strip() or 'Until review',
        route=request.POST.get('route', 'TOPICAL'),
        eye=request.POST.get('eye', 'NA'),
        quantity=max(1, int(request.POST.get('quantity', 1) or 1)),
        special_instructions=request.POST.get('special_instructions', '').strip(),
    )
    _auto_route_to_pharmacy(consultation, request.user)
    messages.success(request, f'Prescription for {drug_name} added. Patient routed to Pharmacy.')
    return redirect('consultations:detail', pk=consultation_pk)


@require_GET
@login_required
def drug_search_ajax(request):
    """AJAX: return matching drug names from pharmacy formulary for autocomplete."""
    from apps.pharmacy.models import Drug
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    from django.db.models import Q
    qs = Drug.objects.filter(is_active=True).filter(
        Q(name__icontains=q) | Q(generic_name__icontains=q) | Q(brand_name__icontains=q)
    ).values('name', 'generic_name', 'form', 'strength')[:12]
    results = []
    for d in qs:
        results.append({
            'name': d['name'],
            'generic_name': d['generic_name'],
            'form': d['form'],
            'strength': d['strength'],
            'concentration': d['strength'],
        })
    return JsonResponse({'results': results})


@require_GET
@login_required
def drug_interaction_check_ajax(request):
    """
    AJAX: check for interactions between two drugs (JCI MMU.7).
    Query params: drug_a=<name>&drug_b=<name>
    Returns list of interaction objects with severity, description, management.
    """
    from .models import DrugInteraction
    drug_a = request.GET.get('drug_a', '').strip()
    drug_b = request.GET.get('drug_b', '').strip()
    if not drug_a or not drug_b:
        return JsonResponse({'interactions': [], 'checked': False})
    interactions = DrugInteraction.find_interactions([drug_a, drug_b])
    data = [{
        'drug_a': i.drug_a,
        'drug_b': i.drug_b,
        'severity': i.severity,
        'severity_label': i.get_severity_display(),
        'description': i.description,
        'clinical_effects': i.clinical_effects,
        'management': i.management,
    } for i in interactions]
    return JsonResponse({'interactions': data, 'checked': True})


@require_GET
@login_required
def drug_interactions_bulk_check_ajax(request):
    """
    AJAX: check all pairwise interactions for a list of drugs.
    Query param: drugs=drug1,drug2,drug3,...
    """
    from .models import DrugInteraction
    drugs_raw = request.GET.get('drugs', '')
    drug_names = [d.strip() for d in drugs_raw.split(',') if d.strip()]
    if len(drug_names) < 2:
        return JsonResponse({'interactions': [], 'checked': False})
    interactions = DrugInteraction.find_interactions(drug_names)
    severity_order = {'CONTRAINDICATED': 0, 'MAJOR': 1, 'MODERATE': 2, 'MINOR': 3}
    data = sorted([{
        'drug_a': i.drug_a,
        'drug_b': i.drug_b,
        'severity': i.severity,
        'severity_label': i.get_severity_display(),
        'description': i.description,
        'clinical_effects': i.clinical_effects,
        'management': i.management,
    } for i in interactions], key=lambda x: severity_order.get(x['severity'], 9))
    return JsonResponse({'interactions': data, 'checked': True, 'drug_count': len(drug_names)})
