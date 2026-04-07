"""
CSSD - Central Sterile Services Department
Instrument tracking, sterilization cycles, dispatch management.
"""
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel, AuditModel


class InstrumentStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available (Sterile)'
    IN_USE = 'IN_USE', 'In Use'
    DIRTY = 'DIRTY', 'Returned / Dirty'
    WASHING = 'WASHING', 'Washing'
    PACKING = 'PACKING', 'Packing'
    STERILIZING = 'STERILIZING', 'Sterilizing'
    QUARANTINE = 'QUARANTINE', 'Quarantine'
    CONDEMNED = 'CONDEMNED', 'Condemned'


class Instrument(AuditModel):
    name = models.CharField(max_length=200)
    instrument_code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='cssd_instruments'
    )
    status = models.CharField(max_length=20, choices=InstrumentStatus.choices, default=InstrumentStatus.AVAILABLE)
    last_sterilized = models.DateTimeField(null=True, blank=True)
    sterilization_expiry = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.instrument_code} - {self.name}"

    @property
    def is_sterile(self):
        if not self.sterilization_expiry:
            return False
        return self.sterilization_expiry > timezone.now() and self.status == InstrumentStatus.AVAILABLE


class InstrumentSet(AuditModel):
    """A set/tray of instruments used together"""
    name = models.CharField(max_length=200)
    set_code = models.CharField(max_length=50, unique=True)
    instruments = models.ManyToManyField(Instrument, blank=True, related_name='sets')
    department = models.ForeignKey(
        'departments.Department', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='instrument_sets'
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.set_code} - {self.name}"


class SterilizationMethod(models.TextChoices):
    AUTOCLAVE = 'AUTOCLAVE', 'Autoclave (Steam)'
    DRY_HEAT = 'DRY_HEAT', 'Dry Heat Oven'
    ETO = 'ETO', 'Ethylene Oxide'
    PLASMA = 'PLASMA', 'Hydrogen Peroxide Plasma'
    CHEMICAL = 'CHEMICAL', 'Chemical Disinfection'


class SterilizationCycle(AuditModel):
    cycle_number = models.CharField(max_length=30, unique=True)
    method = models.CharField(max_length=20, choices=SterilizationMethod.choices)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    temperature = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    pressure = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    operator = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='sterilization_cycles'
    )
    is_successful = models.BooleanField(default=True)
    bi_test_result = models.CharField(max_length=20, choices=[
        ('PASS', 'Pass'), ('FAIL', 'Fail'), ('PENDING', 'Pending')
    ], default='PENDING')
    instruments = models.ManyToManyField(Instrument, blank=True, related_name='sterilization_cycles')
    sets = models.ManyToManyField(InstrumentSet, blank=True, related_name='sterilization_cycles')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Cycle {self.cycle_number} - {self.get_method_display()}"

    def save(self, *args, **kwargs):
        if not self.cycle_number:
            today = timezone.localdate()
            count = SterilizationCycle.objects.filter(start_time__date=today).count() + 1
            self.cycle_number = f"CSSD-{today.strftime('%Y%m%d')}-{count:03d}"
        super().save(*args, **kwargs)


class DispatchRecord(AuditModel):
    """Record of instruments/sets dispatched to departments"""
    dispatch_number = models.CharField(max_length=30, unique=True)
    to_department = models.ForeignKey(
        'departments.Department', on_delete=models.PROTECT, related_name='cssd_dispatches'
    )
    dispatch_time = models.DateTimeField(default=timezone.now)
    return_time = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='cssd_dispatches'
    )
    received_by = models.CharField(max_length=200, blank=True)
    instruments = models.ManyToManyField(Instrument, blank=True, related_name='dispatches')
    sets = models.ManyToManyField(InstrumentSet, blank=True, related_name='dispatches')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispatch_time']

    def save(self, *args, **kwargs):
        if not self.dispatch_number:
            today = timezone.localdate()
            count = DispatchRecord.objects.filter(dispatch_time__date=today).count() + 1
            self.dispatch_number = f"DISP-{today.strftime('%Y%m%d')}-{count:03d}"
        super().save(*args, **kwargs)
