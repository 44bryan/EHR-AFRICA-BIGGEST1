from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing'

    def ready(self):
        from django.db.models.signals import post_save
        from apps.billing.models import (
            Invoice, Payment, Expense, APPayment, APBill,
            Refund, PettyCashEntry, PettyCashFund, WalletTransaction,
        )
        from apps.billing import gl_service

        def on_invoice_saved(sender, instance, created, **kwargs):
            """Post receivable to GL when invoice is issued (not draft)."""
            from apps.billing.models import InvoiceStatus, JournalEntry
            if instance.status in (InvoiceStatus.ISSUED, InvoiceStatus.PAID, InvoiceStatus.PARTIALLY_PAID):
                if not JournalEntry.objects.filter(
                    source_type='invoice', source_id=str(instance.pk)
                ).exists():
                    gl_service.post_invoice_issued(instance)

        def on_payment_saved(sender, instance, created, **kwargs):
            if created:
                gl_service.post_payment(instance)

        def on_expense_approved(sender, instance, created, **kwargs):
            if not created and instance.approved_by:
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

        def on_refund_saved(sender, instance, created, **kwargs):
            if created:
                gl_service.post_refund(instance)

        def on_petty_cash_entry_saved(sender, instance, created, **kwargs):
            if created:
                gl_service.post_petty_cash_entry(instance)

        def on_petty_cash_fund_saved(sender, instance, created, **kwargs):
            if created and instance.opening_balance > 0:
                gl_service.post_petty_cash_fund_creation(instance)

        def on_wallet_txn_saved(sender, instance, created, **kwargs):
            if created:
                from apps.billing.models import WalletTransactionType
                if instance.transaction_type == WalletTransactionType.DEPOSIT:
                    gl_service.post_wallet_deposit(instance)
                elif instance.transaction_type in (
                    WalletTransactionType.DEDUCTION,
                    WalletTransactionType.WITHDRAWAL,
                ):
                    gl_service.post_wallet_deduction(instance)

        post_save.connect(on_invoice_saved,     sender=Invoice)
        post_save.connect(on_payment_saved,    sender=Payment)
        post_save.connect(on_expense_approved, sender=Expense)
        post_save.connect(on_ap_payment_saved, sender=APPayment)
        post_save.connect(on_ap_bill_saved,    sender=APBill)
        post_save.connect(on_refund_saved,     sender=Refund)
        post_save.connect(on_petty_cash_entry_saved, sender=PettyCashEntry)
        post_save.connect(on_petty_cash_fund_saved,  sender=PettyCashFund)
        post_save.connect(on_wallet_txn_saved, sender=WalletTransaction)
