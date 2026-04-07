from django.contrib import admin
from .models import Ward, Bed, Admission, NursingNote, MAREntry, SurgicalBooking


class BedInline(admin.TabularInline):
    model = Bed
    extra = 1
    fields = ['bed_number', 'status', 'price_override', 'notes']
    readonly_fields = []


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ['name', 'ward_type', 'floor', 'total_beds', 'price_per_night', 'available_beds', 'is_active']
    list_editable = ['price_per_night', 'is_active']
    list_filter = ['ward_type', 'is_active']
    search_fields = ['name']
    inlines = [BedInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'ward_type', 'floor', 'total_beds', 'is_active'),
        }),
        ('Pricing & Description', {
            'fields': ('price_per_night', 'description'),
            'description': (
                'Set the nightly rate for this ward/room. '
                'Individual beds can have their own price override below.'
            ),
        }),
    )


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ['bed_number', 'ward', 'status', 'nightly_rate', 'price_override', 'notes']
    list_filter = ['ward', 'status']
    list_editable = ['price_override']
    search_fields = ['bed_number', 'ward__name']


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ['admission_number', 'patient', 'bed', 'admitting_doctor',
                    'surgical_booking', 'admission_date', 'status', 'los_days']
    list_filter = ['status', 'admission_date']
    search_fields = ['admission_number', 'patient__first_name', 'patient__last_name']
    date_hierarchy = 'admission_date'
    raw_id_fields = ['surgical_booking']


@admin.register(SurgicalBooking)
class SurgicalBookingAdmin(admin.ModelAdmin):
    list_display = ['booking_number', 'patient', 'procedure', 'surgery_category',
                    'surgery_date', 'status', 'total_amount', 'deposit_paid']
    list_filter = ['status', 'surgery_category', 'surgery_date']
    search_fields = ['booking_number', 'patient__first_name', 'patient__last_name', 'procedure']
    date_hierarchy = 'surgery_date'


@admin.register(NursingNote)
class NursingNoteAdmin(admin.ModelAdmin):
    list_display = ['admission', 'note_type', 'nurse', 'note_time']
    list_filter = ['note_type']


@admin.register(MAREntry)
class MARAdmin(admin.ModelAdmin):
    list_display = ['admission', 'drug_name', 'dose', 'scheduled_time', 'status', 'administered_by']
    list_filter = ['status']
