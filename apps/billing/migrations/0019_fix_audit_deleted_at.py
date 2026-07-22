"""
Migration 0019 — Add missing deleted_at field to the 4 new AuditModel subclasses
added in 0018 (CashDesk, CashierSession, DiscountApproval, InvoiceTierChange).

AuditModel inherits TimeStampedModel which has:
  - created_at  (auto_now_add)
  - updated_at  (auto_now)
  - is_deleted  (BooleanField)
  - deleted_at  (DateTimeField null/blank)  ← was missing from 0018

DeskReceiptSequence uses plain models.Model so it is not affected.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0018_cash_desk_session'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashdesk',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='cashiersession',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='discountapproval',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='invoicetierchange',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
