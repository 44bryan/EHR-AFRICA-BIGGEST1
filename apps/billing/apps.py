from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing'

    def ready(self):
        from django.db.models.signals import post_save
        from apps.billing.models import Payment, Expense, APPayment, APBill
        from apps.billing import gl_service

        def on_payment_saved(sender, instance, created, **kwargs):
            if created:
                gl_service.post_payment(instance)

        def on_expense_approved(sender, instance, created, **kwargs):
            # Post to GL when expense is approved (approved_by is set)
            if not created and instance.approved_by:
                # Only post once — check no existing GL entry for this expense
                from apps.billing.models import JournalEntry
                if not JournalEntry.objects.filter(
                    source_type='expense', source_id=str(instance.pk)
                ).exists():
                    gl_service.post_expense(instance)

        def on_ap_payment_saved(sender, instance, created, **kwargs):
            if created:
                gl_service.post_ap_payment(instance)

        def on_ap_bill_saved(sender, instance, created, **kwargs):
            if created and instance.status not in ('DRAFT', 'VOID'):
                gl_service.post_ap_bill(instance)

        post_save.connect(on_payment_saved,    sender=Payment)
        post_save.connect(on_expense_approved, sender=Expense)
        post_save.connect(on_ap_payment_saved, sender=APPayment)
        post_save.connect(on_ap_bill_saved,    sender=APBill)
