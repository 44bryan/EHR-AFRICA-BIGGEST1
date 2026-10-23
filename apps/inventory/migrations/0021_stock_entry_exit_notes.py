"""
Migration: Add StockEntryNote (BE) and StockExitNote (BS) document header models.
Adds entry_note and exit_note FKs on StockMovement to group movements per document.
OHADA/SYSCOHADA standard: every stock movement must belong to a numbered document.
"""
import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0020_alter_inventoryitem_category_and_more'),
        ('billing', '0056_serviceprice_tracking_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── StockEntryNote (Bon d'Entrée) ─────────────────────────────────────
        migrations.CreateModel(
            name='StockEntryNote',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_deleted', to=settings.AUTH_USER_MODEL)),
                ('entry_number', models.CharField(max_length=30, unique=True)),
                ('entry_date', models.DateField(default=django.utils.timezone.localdate)),
                ('source', models.CharField(choices=[('PURCHASE', 'Achat fournisseur / Purchase'), ('DONATION', 'Don / Donation'), ('TRANSFER_IN', 'Transfert entrant / Transfer In'), ('RETURN', 'Retour département / Dept Return'), ('FOUND', 'Trouvé / Found (+Adjustment)'), ('OPENING', 'Stock initial / Opening Stock'), ('OTHER', 'Autre / Other')], default='PURCHASE', max_length=20)),
                ('destination_store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='entry_notes', to='inventory.storelocation')),
                ('vendor_name', models.CharField(blank=True, max_length=200)),
                ('delivery_note', models.CharField(blank=True, max_length=100)),
                ('invoice_number', models.CharField(blank=True, max_length=100)),
                ('po_reference', models.CharField(blank=True, max_length=100)),
                ('condition', models.CharField(default='GOOD', max_length=20)),
                ('temp_check', models.CharField(blank=True, max_length=30)),
                ('total_value', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_lines', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('operation_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entry_notes', to='billing.stockoperationtype')),
                ('status', models.CharField(choices=[('PENDING', "En attente — Pending Finance Validation"), ('VALIDATED', 'Validé — GL Posted'), ('REJECTED', 'Rejeté — Rejected')], default='PENDING', max_length=20)),
                ('validated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='validated_entry_notes', to=settings.AUTH_USER_MODEL)),
                ('validated_at', models.DateTimeField(blank=True, null=True)),
                ('journal_entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entry_notes', to='billing.journalentry')),
            ],
            options={
                'ordering': ['-entry_date', '-created_at'],
            },
        ),
        # ── StockExitNote (Bon de Sortie) ──────────────────────────────────────
        migrations.CreateModel(
            name='StockExitNote',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_deleted', to=settings.AUTH_USER_MODEL)),
                ('exit_number', models.CharField(max_length=30, unique=True)),
                ('exit_date', models.DateField(default=django.utils.timezone.localdate)),
                ('reason', models.CharField(choices=[('DEPT_ISSUE', 'Sortie département / Department Issue'), ('INTERNAL', 'Consommation interne / Internal Use'), ('EXPIRED', 'Périmé / Expired Write-off'), ('DAMAGED', 'Cassé/Détérioré / Damaged'), ('LOST', 'Perdu / Lost'), ('TRANSFER_OUT', 'Transfert sortant / Transfer Out'), ('SALE', 'Vente directe / Direct Sale'), ('OTHER', 'Autre / Other')], default='DEPT_ISSUE', max_length=20)),
                ('source_store', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='exit_notes', to='inventory.storelocation')),
                ('recipient_dept', models.CharField(blank=True, max_length=100)),
                ('recipient_name', models.CharField(blank=True, max_length=200)),
                ('authorized_by', models.CharField(blank=True, max_length=200)),
                ('total_value', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('total_lines', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('operation_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exit_notes', to='billing.stockoperationtype')),
                ('status', models.CharField(choices=[('PENDING', "En attente — Pending Finance Validation"), ('VALIDATED', 'Validé — GL Posted'), ('REJECTED', 'Rejeté — Rejected')], default='PENDING', max_length=20)),
                ('validated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='validated_exit_notes', to=settings.AUTH_USER_MODEL)),
                ('validated_at', models.DateTimeField(blank=True, null=True)),
                ('journal_entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exit_notes', to='billing.journalentry')),
            ],
            options={
                'ordering': ['-exit_date', '-created_at'],
            },
        ),
        # ── FKs on StockMovement ───────────────────────────────────────────────
        migrations.AddField(
            model_name='stockmovement',
            name='entry_note',
            field=models.ForeignKey(blank=True, help_text="Bon d'Entrée this movement belongs to", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movements', to='inventory.stockentrynote'),
        ),
        migrations.AddField(
            model_name='stockmovement',
            name='exit_note',
            field=models.ForeignKey(blank=True, help_text='Bon de Sortie this movement belongs to', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movements', to='inventory.stockexitnote'),
        ),
    ]
