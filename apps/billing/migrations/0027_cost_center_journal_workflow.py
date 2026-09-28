# Cost Center model + Journal Entry 3-tier approval workflow
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0026_recategorize_clinical_exams'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── CostCenter model ─────────────────────────────────────────────
        migrations.CreateModel(
            name='CostCenter',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('code', models.CharField(help_text='e.g. CC-OPD, CC-SURG, CC-ADMIN', max_length=20, unique=True)),
                ('name', models.CharField(max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('description', models.TextField(blank=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='billing.costcenter')),
                ('manager', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='managed_cost_centers', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['code'],
            },
        ),
        # ── Journal Entry: cost_center FK ─────────────────────────────────
        migrations.AddField(
            model_name='journalentry',
            name='cost_center',
            field=models.ForeignKey(blank=True, null=True, help_text='Cost center for departmental cost allocation', on_delete=django.db.models.deletion.SET_NULL, related_name='journal_entries', to='billing.costcenter'),
        ),
        # ── Journal Entry: 3-tier approval workflow fields ────────────────
        migrations.AddField(
            model_name='journalentry',
            name='status',
            field=models.CharField(choices=[('DRAFT', 'Draft — Recorded by Accountant'), ('REVIEWED', 'Reviewed by Senior Accountant'), ('POSTED', 'Posted by Finance Director'), ('REJECTED', 'Rejected')], default='POSTED', help_text='Approval status — auto entries are POSTED, manual entries start as DRAFT', max_length=10),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='recorded_by',
            field=models.ForeignKey(blank=True, null=True, help_text='Accountant who recorded this entry', on_delete=django.db.models.deletion.SET_NULL, related_name='journal_entries_recorded', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, help_text='Senior Accountant who reviewed this entry', on_delete=django.db.models.deletion.SET_NULL, related_name='journal_entries_reviewed', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='review_notes',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='journalentry',
            name='posted_by',
            field=models.ForeignKey(blank=True, null=True, help_text='Finance Director who approved and posted this entry', on_delete=django.db.models.deletion.SET_NULL, related_name='journal_entries_posted', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='posted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='journalentry',
            name='rejection_reason',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
    ]
