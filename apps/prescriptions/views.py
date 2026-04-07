from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden
from .models import DrugPrescription, OpticalPrescription
from .forms import DrugPrescriptionForm, DrugItemFormSet, OpticalPrescriptionForm
from apps.consultations.models import Consultation


@login_required
def drug_prescription_new(request, consultation_pk):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk)

    if request.method == 'POST':
        form = DrugPrescriptionForm(request.POST)
        formset = DrugItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            prescription = form.save(commit=False)
            prescription.consultation = consultation
            prescription.patient = consultation.patient
            prescription.prescribed_by = request.user
            prescription.created_by = request.user
            prescription.save()
            formset.instance = prescription
            formset.save()
            messages.success(request, 'Drug prescription created.')
            return redirect('consultations:detail', pk=consultation_pk)
    else:
        form = DrugPrescriptionForm()
        formset = DrugItemFormSet()

    return render(request, 'prescriptions/drug_form.html', {
        'form': form,
        'formset': formset,
        'consultation': consultation,
    })


@login_required
def drug_prescription_detail(request, pk):
    prescription = get_object_or_404(DrugPrescription.objects.prefetch_related('items'), pk=pk)
    return render(request, 'prescriptions/drug_detail.html', {'prescription': prescription})


@login_required
def optical_prescription_new(request, consultation_pk):
    if not request.user.can_create_consultation():
        return HttpResponseForbidden()

    consultation = get_object_or_404(Consultation, pk=consultation_pk)

    if request.method == 'POST':
        form = OpticalPrescriptionForm(request.POST)
        if form.is_valid():
            rx = form.save(commit=False)
            rx.consultation = consultation
            rx.patient = consultation.patient
            rx.prescribed_by = request.user
            rx.created_by = request.user
            rx.save()
            messages.success(request, 'Optical prescription created.')
            return redirect('consultations:detail', pk=consultation_pk)
    else:
        form = OpticalPrescriptionForm()

    return render(request, 'prescriptions/optical_form.html', {
        'form': form,
        'consultation': consultation,
    })


@login_required
def optical_prescription_detail(request, pk):
    rx = get_object_or_404(OpticalPrescription, pk=pk)
    return render(request, 'prescriptions/optical_detail.html', {'rx': rx})
