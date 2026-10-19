"""
Outreach module views — activities, individual patient records,
ophthalmology examinations, referrals, sync API, field sync dashboard.
"""
import uuid
import json
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Q
from django.db import transaction

from .models import (
    OutreachActivity, OutreachRecord, OutreachPatient, OutreachExamination,
    OutreachReferral, OutreachSyncLog,
    OutreachStatus, OutreachType, ReferralUrgency, ReferralStatus,
    SyncStatus, DIAGNOSIS_CHOICES, VA_CHOICES, IOPMethod,
    PrincipalCause, PupilReaction, ConfVF, ColorVision,
    _va_to_who_grade, WHO_VI_GRADE_LABELS,
)


# ─── Access helpers ───────────────────────────────────────────────────────────

def _can_manage(user):
    return (user.is_super_admin or user.is_medical_director
            or user.is_admin_staff or user.can_see_everything)


def _can_examine(user):
    """Clinicians who can record ophthalmology examinations."""
    return (user.is_doctor or user.is_medical_director or user.is_super_admin)


# ─── Activity views ───────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    today = timezone.localdate()
    year  = int(request.GET.get('year', today.year))

    activities = OutreachActivity.objects.prefetch_related('patients', 'records')
    upcoming    = activities.filter(status=OutreachStatus.PLANNED,
                                    activity_date__gte=today).order_by('activity_date')[:5]
    recent      = activities.filter(status=OutreachStatus.COMPLETED
                                    ).order_by('-activity_date')[:6]
    in_progress = activities.filter(status=OutreachStatus.IN_PROGRESS)

    year_patients = OutreachPatient.objects.filter(activity__activity_date__year=year)
    year_agg = year_patients.aggregate(
        total=Count('id'),
        male=Count('id', filter=Q(sex='M')),
        female=Count('id', filter=Q(sex='F')),
        children=Count('id', filter=Q(age_years__lt=18)),
        elderly=Count('id', filter=Q(age_years__gte=60)),
        examined=Count('examination'),
    )

    year_referrals = OutreachReferral.objects.filter(
        patient__activity__activity_date__year=year)
    referral_agg = year_referrals.aggregate(
        total=Count('id'),
        arrived=Count('id', filter=Q(status__in=['ARRIVED', 'IN_TREATMENT', 'COMPLETED'])),
        pending=Count('id', filter=Q(status='PENDING')),
    )
    conversion_rate = 0
    if referral_agg['total']:
        conversion_rate = round(referral_agg['arrived'] / referral_agg['total'] * 100, 1)

    monthly_data = []
    for m in range(1, 13):
        monthly_data.append(
            year_patients.filter(activity__activity_date__month=m).count())

    by_type = (OutreachActivity.objects.filter(activity_date__year=year)
               .values('activity_type').annotate(count=Count('id')).order_by('-count'))
    type_label = dict(OutreachType.choices)
    for t in by_type:
        t['label'] = type_label.get(t['activity_type'], t['activity_type'])

    last_sync         = OutreachSyncLog.objects.filter(sync_status=SyncStatus.SUCCESS).first()
    pending_sync_count = OutreachPatient.objects.filter(is_synced=False).count()

    return render(request, 'outreach/dashboard.html', {
        'upcoming': upcoming,
        'recent': recent,
        'in_progress': in_progress,
        'year_agg': year_agg,
        'referral_agg': referral_agg,
        'conversion_rate': conversion_rate,
        'monthly_data': monthly_data,
        'monthly_labels': ['Jan','Feb','Mar','Apr','May','Jun',
                           'Jul','Aug','Sep','Oct','Nov','Dec'],
        'by_type': list(by_type),
        'year': year,
        'today': today,
        'last_sync': last_sync,
        'pending_sync_count': pending_sync_count,
        'total_activities_year': OutreachActivity.objects.filter(
            activity_date__year=year).count(),
        'completed_year': OutreachActivity.objects.filter(
            activity_date__year=year, status=OutreachStatus.COMPLETED).count(),
        'can_manage': _can_manage(request.user),
    })


@login_required
def activity_list(request):
    qs       = OutreachActivity.objects.prefetch_related('patients').select_related('team_leader')
    status_f = request.GET.get('status', '')
    type_f   = request.GET.get('type', '')
    year_f   = request.GET.get('year', str(timezone.localdate().year))
    if status_f:
        qs = qs.filter(status=status_f)
    if type_f:
        qs = qs.filter(activity_type=type_f)
    if year_f:
        qs = qs.filter(activity_date__year=year_f)
    return render(request, 'outreach/list.html', {
        'activities': qs[:100],
        'status_choices': OutreachStatus.choices,
        'type_choices': OutreachType.choices,
        'status_f': status_f, 'type_f': type_f, 'year_f': year_f,
        'can_manage': _can_manage(request.user),
    })


@login_required
def activity_create(request):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        p   = request.POST
        act = OutreachActivity.objects.create(
            title           = p.get('title', '').strip(),
            activity_type   = p.get('activity_type', OutreachType.EYE_CAMP),
            status          = OutreachStatus.PLANNED,
            location_name   = p.get('location_name', '').strip(),
            region          = p.get('region', '').strip(),
            town            = p.get('town', '').strip(),
            gps_coordinates = p.get('gps_coordinates', '').strip(),
            activity_date   = p.get('activity_date'),
            end_date        = p.get('end_date') or None,
            start_time      = p.get('start_time') or None,
            end_time        = p.get('end_time') or None,
            partner_org     = p.get('partner_org', '').strip(),
            sponsor         = p.get('sponsor', '').strip(),
            sponsor_amount  = p.get('sponsor_amount') or 0,
            budget_fcfa     = p.get('budget_fcfa') or 0,
            target_screened = p.get('target_screened') or 0,
            objectives      = p.get('objectives', '').strip(),
            vehicle_details = p.get('vehicle_details', '').strip(),
            equipment_notes = p.get('equipment_notes', '').strip(),
        )
        leader_id = p.get('team_leader')
        if leader_id:
            from apps.accounts.models import User
            try:
                act.team_leader = User.objects.get(pk=leader_id)
                act.save(update_fields=['team_leader'])
            except User.DoesNotExist:
                pass
        messages.success(request, f'Activity "{act.title}" created.')
        return redirect('outreach:detail', pk=act.pk)
    from apps.accounts.models import User
    staff = User.objects.filter(is_active=True).order_by('last_name')
    return render(request, 'outreach/create.html', {
        'type_choices': OutreachType.choices,
        'staff': staff,
    })


@login_required
def activity_detail(request, pk):
    act      = get_object_or_404(OutreachActivity, pk=pk)
    patients = act.patients.select_related(
        'examination', 'referral', 'registered_by'
    ).order_by('last_name', 'first_name')
    records  = act.records.select_related('recorded_by').order_by('record_date')

    total_referred = OutreachReferral.objects.filter(patient__activity=act).count()
    total_arrived  = OutreachReferral.objects.filter(
        patient__activity=act,
        status__in=['ARRIVED', 'IN_TREATMENT', 'COMPLETED']).count()
    glasses_count  = OutreachExamination.objects.filter(
        patient__activity=act, glasses_dispensed=True).count()

    return render(request, 'outreach/detail.html', {
        'act': act,
        'patients': patients,
        'records': records,
        'total_patients': patients.count(),
        'total_examined': patients.filter(examination__isnull=False).count(),
        'total_referred': total_referred,
        'total_arrived': total_arrived,
        'glasses_count': glasses_count,
        'can_manage': _can_manage(request.user),
        'can_examine': _can_examine(request.user),
    })


@login_required
def activity_edit(request, pk):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    act = get_object_or_404(OutreachActivity, pk=pk)
    if request.method == 'POST':
        p = request.POST
        act.title           = p.get('title', act.title).strip()
        act.activity_type   = p.get('activity_type', act.activity_type)
        act.status          = p.get('status', act.status)
        act.location_name   = p.get('location_name', act.location_name).strip()
        act.region          = p.get('region', '').strip()
        act.town            = p.get('town', '').strip()
        act.activity_date   = p.get('activity_date', act.activity_date)
        act.end_date        = p.get('end_date') or None
        act.partner_org     = p.get('partner_org', '').strip()
        act.sponsor         = p.get('sponsor', '').strip()
        act.sponsor_amount  = p.get('sponsor_amount') or 0
        act.budget_fcfa     = p.get('budget_fcfa') or 0
        act.target_screened = p.get('target_screened') or 0
        act.objectives      = p.get('objectives', '').strip()
        act.notes           = p.get('notes', '').strip()
        act.challenges      = p.get('challenges', '').strip()
        act.recommendations = p.get('recommendations', '').strip()
        act.save()
        messages.success(request, 'Activity updated.')
        return redirect('outreach:detail', pk=act.pk)
    from apps.accounts.models import User
    staff = User.objects.filter(is_active=True).order_by('last_name')
    return render(request, 'outreach/edit.html', {
        'act': act,
        'type_choices': OutreachType.choices,
        'status_choices': OutreachStatus.choices,
        'staff': staff,
    })


# ─── Aggregate daily record ───────────────────────────────────────────────────

@login_required
def record_add(request, pk):
    act = get_object_or_404(OutreachActivity, pk=pk)
    if request.method == 'POST':
        p        = request.POST
        rec_date = p.get('record_date', str(timezone.localdate()))
        if OutreachRecord.objects.filter(activity=act, record_date=rec_date).exists():
            messages.warning(request, f'A record for {rec_date} already exists.')
            return redirect('outreach:detail', pk=act.pk)
        OutreachRecord.objects.create(
            activity=act, record_date=rec_date, recorded_by=request.user,
            total_screened      = int(p.get('total_screened', 0) or 0),
            male_screened       = int(p.get('male_screened', 0) or 0),
            female_screened     = int(p.get('female_screened', 0) or 0),
            children_screened   = int(p.get('children_screened', 0) or 0),
            elderly_screened    = int(p.get('elderly_screened', 0) or 0),
            normal_vision       = int(p.get('normal_vision', 0) or 0),
            refractive_errors   = int(p.get('refractive_errors', 0) or 0),
            cataract            = int(p.get('cataract', 0) or 0),
            glaucoma_suspects   = int(p.get('glaucoma_suspects', 0) or 0),
            diabetic_retinopathy= int(p.get('diabetic_retinopathy', 0) or 0),
            pterygium           = int(p.get('pterygium', 0) or 0),
            trachoma            = int(p.get('trachoma', 0) or 0),
            corneal_opacity     = int(p.get('corneal_opacity', 0) or 0),
            other_pathology     = int(p.get('other_pathology', 0) or 0),
            glasses_dispensed   = int(p.get('glasses_dispensed', 0) or 0),
            medications_given   = int(p.get('medications_given', 0) or 0),
            surgeries_performed = int(p.get('surgeries_performed', 0) or 0),
            total_treated       = int(p.get('total_treated', 0) or 0),
            total_referred      = int(p.get('total_referred', 0) or 0),
            referred_cataract   = int(p.get('referred_cataract', 0) or 0),
            referred_glaucoma   = int(p.get('referred_glaucoma', 0) or 0),
            referred_retina     = int(p.get('referred_retina', 0) or 0),
            referred_other      = int(p.get('referred_other', 0) or 0),
            drugs_cost          = p.get('drugs_cost') or 0,
            transport_cost      = p.get('transport_cost') or 0,
            other_cost          = p.get('other_cost') or 0,
            notes               = p.get('notes', '').strip(),
        )
        if act.end_date and rec_date >= str(act.end_date):
            act.status = OutreachStatus.COMPLETED
            act.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Statistics record saved.')
        return redirect('outreach:detail', pk=act.pk)
    return render(request, 'outreach/record_form.html', {
        'act': act, 'today': timezone.localdate(),
    })


# ─── Patient Registration ─────────────────────────────────────────────────────

@login_required
def patient_list(request, pk):
    act      = get_object_or_404(OutreachActivity, pk=pk)
    patients = act.patients.select_related(
        'examination', 'referral', 'registered_by').order_by('-created_at')
    q = request.GET.get('q', '').strip()
    if q:
        patients = patients.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(outreach_patient_id__icontains=q) | Q(village__icontains=q))
    return render(request, 'outreach/patients.html', {
        'act': act, 'patients': patients, 'q': q,
        'can_examine': _can_examine(request.user),
        'can_manage': _can_manage(request.user),
    })


@login_required
def patient_register(request, pk):
    act = get_object_or_404(OutreachActivity, pk=pk)
    if request.method == 'POST':
        p       = request.POST
        patient = OutreachPatient.objects.create(
            activity             = act,
            registered_by        = request.user,
            first_name           = p.get('first_name', '').strip(),
            last_name            = p.get('last_name', '').strip(),
            date_of_birth        = p.get('date_of_birth') or None,
            age_years            = p.get('age_years') or None,
            sex                  = p.get('sex', 'U'),
            village              = p.get('village', '').strip(),
            district             = p.get('district', '').strip(),
            phone                = p.get('phone', '').strip(),
            next_of_kin          = p.get('next_of_kin', '').strip(),
            known_diabetic       = 'known_diabetic' in p,
            known_hypertensive   = 'known_hypertensive' in p,
            previous_eye_surgery = 'previous_eye_surgery' in p,
            chief_complaint      = p.get('chief_complaint', '').strip(),
        )
        messages.success(request,
            f'Patient {patient.full_name} registered [{patient.outreach_patient_id}].')
        if 'add_exam' in p:
            return redirect('outreach:exam_create', patient_pk=patient.pk)
        return redirect('outreach:patient_list', pk=act.pk)
    return render(request, 'outreach/patient_form.html', {
        'act': act, 'today': timezone.localdate(),
    })


@login_required
def patient_detail(request, patient_pk):
    patient = get_object_or_404(
        OutreachPatient.objects.select_related(
            'activity', 'examination', 'referral', 'referral__referred_by',
            'registered_by', 'hospital_patient'),
        pk=patient_pk)
    return render(request, 'outreach/patient_detail.html', {
        'patient': patient,
        'can_examine': _can_examine(request.user),
        'can_manage': _can_manage(request.user),
        'diag_map': dict(DIAGNOSIS_CHOICES),
    })


# ─── Examination ──────────────────────────────────────────────────────────────

@login_required
def exam_create(request, patient_pk):
    if not _can_examine(request.user):
        return HttpResponseForbidden()
    patient = get_object_or_404(OutreachPatient, pk=patient_pk)
    if hasattr(patient, 'examination'):
        return redirect('outreach:exam_edit', patient_pk=patient.pk)

    if request.method == 'POST':
        p    = request.POST
        exam = OutreachExamination.objects.create(
            patient=patient, examiner=request.user, created_by=request.user,
            exam_date                = p.get('exam_date') or timezone.localdate(),
            va_re_distance           = p.get('va_re_distance', ''),
            va_le_distance           = p.get('va_le_distance', ''),
            va_re_distance_ph        = p.get('va_re_distance_ph', ''),
            va_le_distance_ph        = p.get('va_le_distance_ph', ''),
            va_re_distance_corrected = p.get('va_re_distance_corrected', ''),
            va_le_distance_corrected = p.get('va_le_distance_corrected', ''),
            va_re_near               = p.get('va_re_near', ''),
            va_le_near               = p.get('va_le_near', ''),
            re_sphere    = p.get('re_sphere') or None,
            re_cylinder  = p.get('re_cylinder') or None,
            re_axis      = p.get('re_axis') or None,
            le_sphere    = p.get('le_sphere') or None,
            le_cylinder  = p.get('le_cylinder') or None,
            le_axis      = p.get('le_axis') or None,
            add_power    = p.get('add_power') or None,
            glasses_dispensed = 'glasses_dispensed' in p,
            rx_frame_type     = p.get('rx_frame_type', ''),
            iop_re     = p.get('iop_re') or None,
            iop_le     = p.get('iop_le') or None,
            iop_method = p.get('iop_method', ''),
            ant_segment_re   = p.get('ant_segment_re', ''),
            ant_segment_le   = p.get('ant_segment_le', ''),
            post_segment_re  = p.get('post_segment_re', ''),
            post_segment_le  = p.get('post_segment_le', ''),
            diagnoses_re     = ','.join(p.getlist('diagnoses_re')),
            diagnoses_le     = ','.join(p.getlist('diagnoses_le')),
            medications_given = p.get('medications_given', ''),
            surgery_performed = 'surgery_performed' in p,
            surgery_type      = p.get('surgery_type', ''),
            needs_referral    = 'needs_referral' in p,
            referral_urgency  = p.get('referral_urgency', ''),
            referral_reason   = p.get('referral_reason', ''),
            clinical_notes    = p.get('clinical_notes', ''),
            # WHO / ICD-11 advanced fields
            principal_cause_vi    = p.get('principal_cause_vi', ''),
            pupil_re              = p.get('pupil_re', ''),
            pupil_le              = p.get('pupil_le', ''),
            conf_vf_re            = p.get('conf_vf_re', ''),
            conf_vf_le            = p.get('conf_vf_le', ''),
            color_vision_re       = p.get('color_vision_re', ''),
            color_vision_le       = p.get('color_vision_le', ''),
            external_exam         = p.get('external_exam', ''),
            informed_consent      = 'informed_consent' in p,
            consent_date          = p.get('consent_date') or None,
            low_vision_referral   = 'low_vision_referral' in p,
            examiner_designation  = p.get('examiner_designation', ''),
        )
        # Auto-create referral when flagged
        if exam.needs_referral and not hasattr(patient, 'referral'):
            OutreachReferral.objects.create(
                patient=patient, referred_by=request.user,
                urgency=exam.referral_urgency or ReferralUrgency.ROUTINE,
                diagnosis=', '.join(exam.diagnoses_re_list + exam.diagnoses_le_list),
                reason=exam.referral_reason,
            )
            messages.info(request, 'Referral letter auto-generated.')
        messages.success(request, 'Examination saved.')
        return redirect('outreach:patient_detail', patient_pk=patient.pk)

    return render(request, 'outreach/exam_form.html', {
        'patient': patient, 'va_choices': VA_CHOICES,
        'diag_choices': DIAGNOSIS_CHOICES, 'iop_methods': IOPMethod.choices,
        'urgency_choices': ReferralUrgency.choices, 'today': timezone.localdate(),
        'principal_cause_choices': PrincipalCause.choices,
        'pupil_choices': PupilReaction.choices,
        'conf_vf_choices': ConfVF.choices,
        'color_vision_choices': ColorVision.choices,
    })


@login_required
def exam_edit(request, patient_pk):
    if not _can_examine(request.user):
        return HttpResponseForbidden()
    patient = get_object_or_404(OutreachPatient, pk=patient_pk)
    exam    = get_object_or_404(OutreachExamination, patient=patient)

    if request.method == 'POST':
        p = request.POST
        exam.exam_date                = p.get('exam_date') or exam.exam_date
        exam.va_re_distance           = p.get('va_re_distance', '')
        exam.va_le_distance           = p.get('va_le_distance', '')
        exam.va_re_distance_ph        = p.get('va_re_distance_ph', '')
        exam.va_le_distance_ph        = p.get('va_le_distance_ph', '')
        exam.va_re_distance_corrected = p.get('va_re_distance_corrected', '')
        exam.va_le_distance_corrected = p.get('va_le_distance_corrected', '')
        exam.va_re_near               = p.get('va_re_near', '')
        exam.va_le_near               = p.get('va_le_near', '')
        exam.re_sphere    = p.get('re_sphere') or None
        exam.re_cylinder  = p.get('re_cylinder') or None
        exam.re_axis      = p.get('re_axis') or None
        exam.le_sphere    = p.get('le_sphere') or None
        exam.le_cylinder  = p.get('le_cylinder') or None
        exam.le_axis      = p.get('le_axis') or None
        exam.add_power    = p.get('add_power') or None
        exam.glasses_dispensed = 'glasses_dispensed' in p
        exam.rx_frame_type     = p.get('rx_frame_type', '')
        exam.iop_re    = p.get('iop_re') or None
        exam.iop_le    = p.get('iop_le') or None
        exam.iop_method = p.get('iop_method', '')
        exam.ant_segment_re   = p.get('ant_segment_re', '')
        exam.ant_segment_le   = p.get('ant_segment_le', '')
        exam.post_segment_re  = p.get('post_segment_re', '')
        exam.post_segment_le  = p.get('post_segment_le', '')
        exam.diagnoses_re     = ','.join(p.getlist('diagnoses_re'))
        exam.diagnoses_le     = ','.join(p.getlist('diagnoses_le'))
        exam.medications_given = p.get('medications_given', '')
        exam.surgery_performed = 'surgery_performed' in p
        exam.surgery_type      = p.get('surgery_type', '')
        exam.needs_referral    = 'needs_referral' in p
        exam.referral_urgency  = p.get('referral_urgency', '')
        exam.referral_reason   = p.get('referral_reason', '')
        exam.clinical_notes    = p.get('clinical_notes', '')
        # WHO / ICD-11 advanced fields
        exam.principal_cause_vi   = p.get('principal_cause_vi', '')
        exam.pupil_re             = p.get('pupil_re', '')
        exam.pupil_le             = p.get('pupil_le', '')
        exam.conf_vf_re           = p.get('conf_vf_re', '')
        exam.conf_vf_le           = p.get('conf_vf_le', '')
        exam.color_vision_re      = p.get('color_vision_re', '')
        exam.color_vision_le      = p.get('color_vision_le', '')
        exam.external_exam        = p.get('external_exam', '')
        exam.informed_consent     = 'informed_consent' in p
        exam.consent_date         = p.get('consent_date') or None
        exam.low_vision_referral  = 'low_vision_referral' in p
        exam.examiner_designation = p.get('examiner_designation', '')
        exam.updated_by = request.user
        exam.save()
        messages.success(request, 'Examination updated.')
        return redirect('outreach:patient_detail', patient_pk=patient.pk)

    return render(request, 'outreach/exam_form.html', {
        'patient': patient, 'exam': exam, 'va_choices': VA_CHOICES,
        'diag_choices': DIAGNOSIS_CHOICES, 'iop_methods': IOPMethod.choices,
        'urgency_choices': ReferralUrgency.choices, 'today': timezone.localdate(),
        'edit': True,
        'principal_cause_choices': PrincipalCause.choices,
        'pupil_choices': PupilReaction.choices,
        'conf_vf_choices': ConfVF.choices,
        'color_vision_choices': ColorVision.choices,
    })


# ─── Referral ─────────────────────────────────────────────────────────────────

@login_required
def referral_create(request, patient_pk):
    patient = get_object_or_404(OutreachPatient, pk=patient_pk)
    if hasattr(patient, 'referral'):
        return redirect('outreach:referral_letter', patient_pk=patient.pk)
    if request.method == 'POST':
        p = request.POST
        OutreachReferral.objects.create(
            patient=patient, referred_by=request.user,
            urgency=p.get('urgency', ReferralUrgency.ROUTINE),
            diagnosis=p.get('diagnosis', '').strip(),
            reason=p.get('reason', '').strip(),
            recommendations=p.get('recommendations', '').strip(),
        )
        messages.success(request, 'Referral created.')
        return redirect('outreach:referral_letter', patient_pk=patient.pk)
    exam = getattr(patient, 'examination', None)
    return render(request, 'outreach/referral_create.html', {
        'patient': patient, 'exam': exam,
        'urgency_choices': ReferralUrgency.choices,
        'diag_choices': DIAGNOSIS_CHOICES,
    })


@login_required
def referral_letter(request, patient_pk):
    """Printable referral letter."""
    patient  = get_object_or_404(OutreachPatient.objects.select_related(
        'activity', 'examination', 'referral', 'referral__referred_by'), pk=patient_pk)
    referral = get_object_or_404(OutreachReferral, patient=patient)
    exam     = getattr(patient, 'examination', None)
    from apps.accounts.models import HospitalConfig
    hospital = HospitalConfig.get()
    return render(request, 'outreach/referral_letter.html', {
        'patient': patient, 'referral': referral, 'exam': exam,
        'hospital': hospital, 'diag_map': dict(DIAGNOSIS_CHOICES),
    })


@login_required
def referral_lookup(request):
    """Receptionist looks up a referral code when a patient arrives."""
    code     = request.GET.get('code', '').strip().upper()
    referral = None
    if code:
        referral = OutreachReferral.objects.select_related(
            'patient__activity', 'patient__examination'
        ).filter(referral_code=code).first()
        if referral and request.method == 'POST':
            referral.status       = ReferralStatus.ARRIVED
            referral.arrived_date = timezone.localdate()
            referral.received_by  = request.user
            referral.save(update_fields=['status', 'arrived_date', 'received_by', 'updated_at'])
            messages.success(request,
                f'Referral {code} marked Arrived — {referral.patient.full_name}.')
    return render(request, 'outreach/referral_lookup.html', {
        'code': code, 'referral': referral, 'diag_map': dict(DIAGNOSIS_CHOICES),
    })


@login_required
def referral_status_update(request, referral_pk):
    if not (_can_manage(request.user) or getattr(request.user, 'is_receptionist', False)):
        return HttpResponseForbidden()
    referral = get_object_or_404(OutreachReferral, pk=referral_pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(ReferralStatus.choices):
            referral.status       = new_status
            referral.outcome_notes = request.POST.get('outcome_notes', referral.outcome_notes)
            referral.save(update_fields=['status', 'outcome_notes', 'updated_at'])
            messages.success(request, 'Referral status updated.')
    return redirect('outreach:patient_detail', patient_pk=referral.patient.pk)


# ─── Stats ────────────────────────────────────────────────────────────────────

@login_required
def stats_view(request):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    today = timezone.localdate()
    year  = int(request.GET.get('year', today.year))

    records   = OutreachRecord.objects.filter(activity__activity_date__year=year)
    acts_qs   = OutreachActivity.objects.filter(activity_date__year=year)
    patients  = OutreachPatient.objects.filter(activity__activity_date__year=year)
    referrals = OutreachReferral.objects.filter(patient__activity__activity_date__year=year)

    totals = records.aggregate(
        screened=Sum('total_screened'), male=Sum('male_screened'),
        female=Sum('female_screened'), children=Sum('children_screened'),
        elderly=Sum('elderly_screened'), treated=Sum('total_treated'),
        referred=Sum('total_referred'), surgeries=Sum('surgeries_performed'),
        glasses=Sum('glasses_dispensed'), ref_cataract=Sum('referred_cataract'),
        ref_glaucoma=Sum('referred_glaucoma'), ref_retina=Sum('referred_retina'),
        ref_other=Sum('referred_other'), cost_drugs=Sum('drugs_cost'),
        cost_transport=Sum('transport_cost'), cost_other=Sum('other_cost'),
    )
    pt_agg = patients.aggregate(
        total=Count('id'), male=Count('id', filter=Q(sex='M')),
        female=Count('id', filter=Q(sex='F')), examined=Count('examination'),
    )
    ref_agg = referrals.aggregate(
        total=Count('id'),
        arrived=Count('id', filter=Q(status__in=['ARRIVED', 'IN_TREATMENT', 'COMPLETED'])),
    )
    conversion = (round(ref_agg['arrived'] / ref_agg['total'] * 100, 1)
                  if ref_agg['total'] else 0)
    path_totals = records.aggregate(
        normal=Sum('normal_vision'), refractive=Sum('refractive_errors'),
        cataract=Sum('cataract'), glaucoma=Sum('glaucoma_suspects'),
        dr=Sum('diabetic_retinopathy'), pterygium=Sum('pterygium'),
        trachoma=Sum('trachoma'), corneal=Sum('corneal_opacity'),
        other=Sum('other_pathology'),
    )
    monthly = []
    for m in range(1, 13):
        agg = records.filter(record_date__month=m).aggregate(
            s=Sum('total_screened'), t=Sum('total_treated'), r=Sum('total_referred'))
        monthly.append({'month': m, 'screened': agg['s'] or 0,
                        'treated': agg['t'] or 0, 'referred': agg['r'] or 0})
    by_type = []
    for at, label in OutreachType.choices:
        agg = records.filter(activity__activity_type=at).aggregate(
            count=Count('id'), s=Sum('total_screened'), t=Sum('total_treated'))
        if agg['count']:
            by_type.append({'type': at, 'label': label, **agg})

    # ── WHO-standard metrics (from individual examination records) ─────────────
    exams_qs = OutreachExamination.objects.filter(
        patient__activity__activity_date__year=year
    )
    total_exams = exams_qs.count()

    # WHO Visual Impairment grading — iterate once over exams with VA data
    who_counts  = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}   # grade → count (better eye)
    blind_total = 0
    avoidable_blind = 0
    vi_total    = 0

    # Principal cause of VI distribution
    cause_counts = {}
    for cause, label in PrincipalCause.choices:
        cause_counts[cause] = 0

    # RAAB7 age brackets (population survey standard)
    raab_brackets = {'<40': 0, '40-49': 0, '50-59': 0, '60-69': 0, '70-79': 0, '>=80': 0}

    # CSC numerator (cataract operated) = patients with surgery_type containing cataract
    cataract_operated = exams_qs.filter(
        surgery_type__icontains='cataract'
    ).count()
    # CSC denominator = patients with cataract diagnosis (RE or LE)
    cataract_need = exams_qs.filter(
        Q(diagnoses_re__icontains='CATARACT') | Q(diagnoses_le__icontains='CATARACT')
    ).count()

    # eREC: glasses dispensed / total needing refractive correction
    refractive_need = exams_qs.filter(
        Q(diagnoses_re__icontains='REFRACTIVE_ERROR') | Q(diagnoses_le__icontains='REFRACTIVE_ERROR')
    ).count()
    glasses_given   = exams_qs.filter(glasses_dispensed=True).count()

    # Iterate for WHO grades + cause distribution
    for ex in exams_qs.values('patient__date_of_birth', 'patient__age_years',
                               'va_re_distance', 'va_le_distance',
                               'principal_cause_vi'):
        # WHO better eye grade
        g_re = _va_to_who_grade(ex['va_re_distance'])
        g_le = _va_to_who_grade(ex['va_le_distance'])
        grade = None
        if g_re is not None and g_le is not None:
            grade = min(g_re, g_le)
        elif g_re is not None:
            grade = g_re
        elif g_le is not None:
            grade = g_le

        if grade is not None:
            who_counts[grade] = who_counts.get(grade, 0) + 1
            if grade >= 1:
                vi_total += 1
            if grade >= 4:
                blind_total += 1
                if ex['principal_cause_vi'] in {
                    PrincipalCause.CATARACT, PrincipalCause.REFRACTIVE_ERROR,
                    PrincipalCause.TRACHOMA, PrincipalCause.CORNEAL_OPACITY,
                    PrincipalCause.DIABETIC_RETINOPATHY,
                }:
                    avoidable_blind += 1

        # Principal cause
        cause = ex['principal_cause_vi']
        if cause in cause_counts:
            cause_counts[cause] = cause_counts[cause] + 1

        # RAAB age bracket
        from datetime import date as _date
        dob  = ex['patient__date_of_birth']
        age  = ex['patient__age_years']
        if dob:
            age = (_date.today() - dob).days // 365
        if age is not None:
            if age < 40:   raab_brackets['<40']   += 1
            elif age < 50: raab_brackets['40-49']  += 1
            elif age < 60: raab_brackets['50-59']  += 1
            elif age < 70: raab_brackets['60-69']  += 1
            elif age < 80: raab_brackets['70-79']  += 1
            else:          raab_brackets['>=80']   += 1

    # CSC / eREC rates
    csc  = round(cataract_operated / cataract_need * 100, 1) if cataract_need else None
    erec = round(glasses_given / refractive_need * 100, 1) if refractive_need else None

    # Cause-of-blindness chart data (label, count) sorted descending
    cause_chart = sorted(
        [{'label': PrincipalCause(c).label, 'code': c, 'count': n}
         for c, n in cause_counts.items() if n > 0],
        key=lambda x: x['count'], reverse=True
    )

    who_grade_chart = [
        {'grade': g, 'label': WHO_VI_GRADE_LABELS[g][0],
         'color': WHO_VI_GRADE_LABELS[g][1], 'count': who_counts.get(g, 0)}
        for g in range(5)
    ]

    _out_ctx = {
        'year': year, 'totals': totals, 'path_totals': path_totals,
        'pt_agg': pt_agg, 'ref_agg': ref_agg, 'conversion': conversion,
        'monthly': monthly, 'by_type': by_type,
        'activities_count': acts_qs.count(),
        'completed_count': acts_qs.filter(status=OutreachStatus.COMPLETED).count(),
        'today': today,
        'total_exams': total_exams,
        'who_counts': who_counts,
        'who_grade_chart': who_grade_chart,
        'vi_total': vi_total,
        'blind_total': blind_total,
        'avoidable_blind': avoidable_blind,
        'cause_chart': cause_chart,
        'raab_brackets': raab_brackets,
        'csc': csc, 'csc_num': cataract_operated, 'csc_den': cataract_need,
        'erec': erec, 'erec_num': glasses_given, 'erec_den': refractive_need,
    }
    if request.GET.get('pdf'):
        from apps.reports.views import render_pdf
        _out_ctx['pdf_filename'] = 'outreach-stats.pdf'
        return render_pdf('outreach/stats_pdf.html', _out_ctx)
    return render(request, 'outreach/stats.html', _out_ctx)


# ─── Sync Dashboard ───────────────────────────────────────────────────────────

@login_required
@require_POST
def sync_now(request):
    """
    One-click sync from the field app UI.
    Collects all unsynced local records and POSTs them to the hospital server.
    Only works when HOSPITAL_SERVER_URL is set (i.e. running in field-app mode).
    """
    if not _can_manage(request.user):
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    from django.conf import settings as djsettings
    server_url = getattr(djsettings, 'HOSPITAL_SERVER_URL', None)
    if not server_url:
        return JsonResponse({
            'success': False,
            'error': 'HOSPITAL_SERVER_URL is not set. This button only works on the field laptop.',
        })

    sync_token   = getattr(djsettings, 'OUTREACH_SYNC_TOKEN', '')
    device_id    = getattr(djsettings, 'FIELD_DEVICE_ID', 'UNKNOWN-DEVICE')
    device_label = getattr(djsettings, 'FIELD_DEVICE_LABEL', 'Field Laptop')

    def _str(v): return str(v) if v is not None else None
    def _date(v): return str(v) if v else None

    # Collect unsynced data
    activities_data = [
        {'id': str(a.id), 'title': a.title, 'activity_type': a.activity_type,
         'status': a.status, 'location_name': a.location_name, 'region': a.region,
         'town': a.town, 'activity_date': _date(a.activity_date), 'objectives': a.objectives}
        for a in OutreachActivity.objects.all()
    ]
    patients_data = [
        {'id': str(pt.id), 'activity_id': str(pt.activity_id),
         'outreach_patient_id': pt.outreach_patient_id,
         'first_name': pt.first_name, 'last_name': pt.last_name,
         'date_of_birth': _date(pt.date_of_birth), 'age_years': pt.age_years,
         'sex': pt.sex, 'village': pt.village, 'district': pt.district,
         'phone': pt.phone, 'chief_complaint': pt.chief_complaint,
         'known_diabetic': pt.known_diabetic, 'known_hypertensive': pt.known_hypertensive,
         'previous_eye_surgery': pt.previous_eye_surgery}
        for pt in OutreachPatient.objects.filter(is_synced=False)
    ]
    exams_data = []
    for ex in OutreachExamination.objects.filter(patient__is_synced=False):
        exams_data.append({
            'id': str(ex.id), 'patient_id': str(ex.patient_id),
            'exam_date': _date(ex.exam_date),
            'va_re_distance': ex.va_re_distance, 'va_le_distance': ex.va_le_distance,
            're_sphere': float(ex.re_sphere) if ex.re_sphere is not None else None,
            're_cylinder': float(ex.re_cylinder) if ex.re_cylinder is not None else None,
            're_axis': ex.re_axis,
            'le_sphere': float(ex.le_sphere) if ex.le_sphere is not None else None,
            'le_cylinder': float(ex.le_cylinder) if ex.le_cylinder is not None else None,
            'le_axis': ex.le_axis,
            'iop_re': float(ex.iop_re) if ex.iop_re is not None else None,
            'iop_le': float(ex.iop_le) if ex.iop_le is not None else None,
            'diagnoses_re': ex.diagnoses_re, 'diagnoses_le': ex.diagnoses_le,
            'needs_referral': ex.needs_referral, 'referral_urgency': ex.referral_urgency,
            'referral_reason': ex.referral_reason, 'clinical_notes': ex.clinical_notes,
        })
    referrals_data = [
        {'id': str(ref.id), 'patient_id': str(ref.patient_id),
         'referral_code': ref.referral_code, 'urgency': ref.urgency,
         'diagnosis': ref.diagnosis, 'reason': ref.reason}
        for ref in OutreachReferral.objects.filter(is_synced=False)
    ]

    payload = {
        'device_id': device_id, 'device_label': device_label,
        'activities': activities_data, 'patients': patients_data,
        'examinations': exams_data, 'referrals': referrals_data, 'records': [],
    }

    import urllib.request as urllib_req
    sync_url = f"{server_url.rstrip('/')}/outreach/api/sync/"
    try:
        data    = json.dumps(payload).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if sync_token:
            headers['Authorization'] = f'Bearer {sync_token}'
        req = urllib_req.Request(sync_url, data=data, headers=headers, method='POST')
        with urllib_req.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            if result.get('status') in ('ok', 'partial'):
                OutreachPatient.objects.filter(is_synced=False).update(is_synced=True)
                OutreachReferral.objects.filter(is_synced=False).update(is_synced=True)
            c = result.get('created', {})
            return JsonResponse({
                'success': True,
                'status': result.get('status', 'ok'),
                'patients': c.get('patients', 0),
                'examinations': c.get('examinations', 0),
                'referrals': c.get('referrals', 0),
                'errors': result.get('errors', [])[:5],
            })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def sync_dashboard(request):
    if not _can_manage(request.user):
        return HttpResponseForbidden()
    logs             = OutreachSyncLog.objects.select_related('synced_by').order_by('-created_at')[:20]
    pending_patients = OutreachPatient.objects.filter(is_synced=False).count()
    pending_refs     = OutreachReferral.objects.filter(is_synced=False).count()
    last_success     = OutreachSyncLog.objects.filter(sync_status=SyncStatus.SUCCESS).first()
    return render(request, 'outreach/sync.html', {
        'logs': logs, 'pending_patients': pending_patients,
        'pending_referrals': pending_refs, 'last_success': last_success,
    })


# ─── Sync API ─────────────────────────────────────────────────────────────────

@csrf_exempt
def sync_api(request):
    """
    POST /outreach/api/sync/
    Receives JSON from a field laptop and bulk-imports all records.
    Auth: session OR Bearer token (OUTREACH_SYNC_TOKEN in settings).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    from django.conf import settings as djsettings
    sync_token   = getattr(djsettings, 'OUTREACH_SYNC_TOKEN', None)
    auth_header  = request.headers.get('Authorization', '')

    if request.user.is_authenticated:
        sync_user = request.user
    elif sync_token and auth_header == f'Bearer {sync_token}':
        from apps.accounts.models import User
        sync_user = User.objects.filter(is_super_admin=True).first()
    else:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    device_id    = payload.get('device_id', 'unknown')
    device_label = payload.get('device_label', '')

    log = OutreachSyncLog.objects.create(
        device_id=device_id, device_label=device_label,
        synced_by=sync_user, sync_status=SyncStatus.PENDING,
    )
    counts = {'activities': 0, 'patients': 0, 'examinations': 0,
              'referrals': 0, 'records': 0}
    errors = []

    try:
        with transaction.atomic():
            # 1 — Activities
            for a in payload.get('activities', []):
                try:
                    _, created = OutreachActivity.objects.get_or_create(
                        id=a['id'],
                        defaults={
                            'title': a.get('title', 'Field Activity'),
                            'activity_type': a.get('activity_type', 'EYE_CAMP'),
                            'status': a.get('status', 'PLANNED'),
                            'location_name': a.get('location_name', ''),
                            'region': a.get('region', ''),
                            'town': a.get('town', ''),
                            'activity_date': a['activity_date'],
                            'objectives': a.get('objectives', ''),
                        })
                    if created:
                        counts['activities'] += 1
                except Exception as e:
                    errors.append(f'Activity {a.get("id","?")}: {e}')

            # 2 — Patients
            for pt in payload.get('patients', []):
                try:
                    act_obj = OutreachActivity.objects.get(id=pt['activity_id'])
                    patient, created = OutreachPatient.objects.get_or_create(
                        id=pt['id'],
                        defaults={
                            'activity': act_obj,
                            'outreach_patient_id': pt.get('outreach_patient_id', ''),
                            'first_name': pt.get('first_name', ''),
                            'last_name': pt.get('last_name', ''),
                            'date_of_birth': pt.get('date_of_birth') or None,
                            'age_years': pt.get('age_years') or None,
                            'sex': pt.get('sex', 'U'),
                            'village': pt.get('village', ''),
                            'district': pt.get('district', ''),
                            'phone': pt.get('phone', ''),
                            'chief_complaint': pt.get('chief_complaint', ''),
                            'known_diabetic': pt.get('known_diabetic', False),
                            'known_hypertensive': pt.get('known_hypertensive', False),
                            'previous_eye_surgery': pt.get('previous_eye_surgery', False),
                            'is_synced': True,
                            'field_device_id': device_id,
                        })
                    if created:
                        counts['patients'] += 1
                    elif not patient.is_synced:
                        patient.is_synced = True
                        patient.save(update_fields=['is_synced'])
                except Exception as e:
                    errors.append(f'Patient {pt.get("id","?")}: {e}')

            # 3 — Examinations
            for ex in payload.get('examinations', []):
                try:
                    pt_obj = OutreachPatient.objects.get(id=ex['patient_id'])
                    if not hasattr(pt_obj, 'examination'):
                        OutreachExamination.objects.create(
                            id=ex.get('id') or uuid.uuid4(),
                            patient=pt_obj, examiner=sync_user, created_by=sync_user,
                            exam_date=ex.get('exam_date') or timezone.localdate(),
                            va_re_distance=ex.get('va_re_distance', ''),
                            va_le_distance=ex.get('va_le_distance', ''),
                            va_re_distance_ph=ex.get('va_re_distance_ph', ''),
                            va_le_distance_ph=ex.get('va_le_distance_ph', ''),
                            va_re_distance_corrected=ex.get('va_re_distance_corrected', ''),
                            va_le_distance_corrected=ex.get('va_le_distance_corrected', ''),
                            va_re_near=ex.get('va_re_near', ''),
                            va_le_near=ex.get('va_le_near', ''),
                            re_sphere=ex.get('re_sphere') or None,
                            re_cylinder=ex.get('re_cylinder') or None,
                            re_axis=ex.get('re_axis') or None,
                            le_sphere=ex.get('le_sphere') or None,
                            le_cylinder=ex.get('le_cylinder') or None,
                            le_axis=ex.get('le_axis') or None,
                            add_power=ex.get('add_power') or None,
                            glasses_dispensed=ex.get('glasses_dispensed', False),
                            iop_re=ex.get('iop_re') or None,
                            iop_le=ex.get('iop_le') or None,
                            diagnoses_re=ex.get('diagnoses_re', ''),
                            diagnoses_le=ex.get('diagnoses_le', ''),
                            medications_given=ex.get('medications_given', ''),
                            surgery_performed=ex.get('surgery_performed', False),
                            needs_referral=ex.get('needs_referral', False),
                            referral_urgency=ex.get('referral_urgency', ''),
                            referral_reason=ex.get('referral_reason', ''),
                            clinical_notes=ex.get('clinical_notes', ''),
                        )
                        counts['examinations'] += 1
                except Exception as e:
                    errors.append(f'Exam {ex.get("patient_id","?")}: {e}')

            # 4 — Referrals
            for ref in payload.get('referrals', []):
                try:
                    pt_obj = OutreachPatient.objects.get(id=ref['patient_id'])
                    if not hasattr(pt_obj, 'referral'):
                        OutreachReferral.objects.create(
                            id=ref.get('id') or uuid.uuid4(),
                            patient=pt_obj, referred_by=sync_user,
                            referral_code=ref.get('referral_code', ''),
                            urgency=ref.get('urgency', 'ROUTINE'),
                            diagnosis=ref.get('diagnosis', ''),
                            reason=ref.get('reason', ''),
                            recommendations=ref.get('recommendations', ''),
                            is_synced=True,
                        )
                        counts['referrals'] += 1
                except Exception as e:
                    errors.append(f'Referral {ref.get("patient_id","?")}: {e}')

            # 5 — Daily records
            for rec in payload.get('records', []):
                try:
                    act_obj = OutreachActivity.objects.get(id=rec['activity_id'])
                    _, created = OutreachRecord.objects.get_or_create(
                        activity=act_obj, record_date=rec['record_date'],
                        defaults={
                            'recorded_by': sync_user,
                            'total_screened': rec.get('total_screened', 0),
                            'male_screened': rec.get('male_screened', 0),
                            'female_screened': rec.get('female_screened', 0),
                            'cataract': rec.get('cataract', 0),
                            'refractive_errors': rec.get('refractive_errors', 0),
                            'glaucoma_suspects': rec.get('glaucoma_suspects', 0),
                            'glasses_dispensed': rec.get('glasses_dispensed', 0),
                            'total_referred': rec.get('total_referred', 0),
                            'drugs_cost': rec.get('drugs_cost', 0),
                            'transport_cost': rec.get('transport_cost', 0),
                            'other_cost': rec.get('other_cost', 0),
                        })
                    if created:
                        counts['records'] += 1
                except Exception as e:
                    errors.append(f'Record {rec.get("activity_id","?")}: {e}')

        log.sync_status        = SyncStatus.SUCCESS if not errors else SyncStatus.PARTIAL
        log.activities_synced  = counts['activities']
        log.patients_synced    = counts['patients']
        log.examinations_synced = counts['examinations']
        log.referrals_synced   = counts['referrals']
        log.records_synced     = counts['records']
        log.error_log          = '\n'.join(errors)
        log.completed_at       = timezone.now()
        log.save()

        return JsonResponse({
            'status': 'ok' if not errors else 'partial',
            'sync_id': str(log.pk),
            'created': counts,
            'errors': errors,
        })

    except Exception as e:
        log.sync_status  = SyncStatus.FAILED
        log.error_log    = str(e)
        log.completed_at = timezone.now()
        log.save()
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
