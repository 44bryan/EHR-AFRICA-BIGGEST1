# EHR Africa — Visit-Centric Architecture Audit

## Current Data Model (as of 2026-09-23)

### Linking Structure

```
Visit (patients.Visit)
  ├── Consultation (consultations.Consultation)   — visit FK ✓
  │     ├── InvestigationOrder                    — consultation FK (nullable)
  │     ├── LabOrder                              — consultation FK (not nullable)
  │     ├── DrugPrescription                      — consultation FK
  │     └── OpticalPrescription                   — consultation FK
  └── VisitStop (patients.VisitStop)              — visit FK ✓
```

### Gap: No direct Visit FK on orders

- `InvestigationOrder.consultation` is nullable (nurse orders have `consultation=None`)
- `LabOrder.consultation` is NOT nullable
- Neither has a `visit` FK → must traverse `order.consultation.visit`
- When `consultation=None`, system falls back to `patient + created_at__date`

### Fragile matching patterns (patient + today)

| File | Line | Pattern | Purpose |
|------|------|---------|---------|
| consultations/views.py | ~275 | `patient=patient, created_at__date=today` | Find pending exam for form override |
| consultations/views.py | ~500 | `patient=patient, created_at__date=today` | Mark orders COMPLETED on consult save |
| consultations/views.py | ~1059 | `patient=patient, created_at__date=today` | Mark orders COMPLETED on consult edit |
| core/patient_flow.py | ~257 | `Q(consultation__visit) \| Q(patient, date)` | check_and_autoreturn_to_doctor |
| billing/views.py | ~1935 | `patient_id, created_at__date=now.date()` | Bridge: match unpaid orders after payment |
| billing/views.py | ~2005 | `patient_id, created_at__date=_today` | Bridge: check if all orders paid |

### Three kinds of clinical work

| Type | Who | Record model | Form | Produces |
|------|-----|-------------|------|----------|
| Consultation | Doctor | Consultation (dept: GEN_OPH, RETINA, etc.) | Full clinical form | Diagnosis, plan, Rx |
| Clinical Exam | Optometrist/Orthoptist | Consultation (dept: REFRAC, LOW_VIS, ORTHO) | Dept-specific form | Structured measurements |
| Investigation | Technician | InvestigationResult | Structured result or upload | Report, images |

### Routing functions

| Function | File | Fires when |
|----------|------|-----------|
| `_auto_route_to_dept()` | core/patient_flow.py | Generic dept routing |
| `auto_route_to_investigation()` | core/patient_flow.py | After exam/investigation ordered |
| `check_and_autoreturn_to_doctor()` | core/patient_flow.py | After exam/investigation completed |
| `_bridge_work_order_to_clinical()` | billing/views.py | After cashier payment |
| `_route_patient_after_payment()` | billing/views.py | Default post-payment routing |

### Risk: `_route_patient_after_payment` can overwrite bridge routing
Both functions run after payment. If the bridge sets REFRACTION but `_route_patient_after_payment` runs after, it can reset to PARAMETERS.

## Stage Plan

- **Stage 1**: Visit Summary page (read-only, zero risk) ← CURRENT
- **Stage 2**: Add `visit` FK to InvestigationOrder + LabOrder
- **Stage 3**: Consultation.record_type = CONSULTATION | CLINICAL_EXAM
- **Stage 4**: Routing unification (on_exam_completed, on_orders_paid)
- **Stage 5**: Patient record = list of visits
- **Stage 6**: Cleanup (remove fallback matching)
