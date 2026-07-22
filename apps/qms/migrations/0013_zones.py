"""
Migration 0013: Zone-based routing architecture.

Adds:
  - Zone model (physical/organisational hospital section)
  - TierZoneMapping model (admin-configurable tier → zone)
  - ServiceCounter.zone FK
  - ServiceCounter.station_type CharField
  - ServiceCounter.anti_starvation_minutes PositiveSmallIntegerField
  - QueueToken.zone FK
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0012_queuetoken_assigned_doctor'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Zone ──────────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Zone',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('code', models.CharField(max_length=30, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('color', models.CharField(
                    default='secondary', max_length=20,
                    help_text='Bootstrap colour name: primary | success | warning | danger | info | secondary | dark'
                )),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),

        # ── 2. TierZoneMapping ───────────────────────────────────────────────
        migrations.CreateModel(
            name='TierZoneMapping',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tier', models.CharField(
                    choices=[
                        ('STANDARD', 'Standard'),
                        ('EXPRESS', 'Express'),
                        ('FAST_TRACK', 'Fast Track'),
                        ('VIP', 'VIP'),
                    ],
                    max_length=20, unique=True
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('zone', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='tier_mappings',
                    to='qms.zone',
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='tier_zone_changes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['tier'],
            },
        ),

        # ── 3. ServiceCounter: add zone FK ───────────────────────────────────
        migrations.AddField(
            model_name='servicecounter',
            name='zone',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='counters',
                to='qms.zone',
                help_text='Physical zone this station belongs to.',
            ),
        ),

        # ── 4. ServiceCounter: add station_type ──────────────────────────────
        migrations.AddField(
            model_name='servicecounter',
            name='station_type',
            field=models.CharField(
                blank=True, max_length=20,
                choices=[
                    ('RECEPTION', 'Reception Desk'),
                    ('TRIAGE', 'Triage / Parameters'),
                    ('CASHIER', 'Cashier Counter'),
                    ('CONSULTATION', 'Consultation Room'),
                    ('SPECIALIST', 'Specialist Room'),
                    ('REFRACTION', 'Refraction / Optometry Room'),
                    ('LAB', 'Laboratory'),
                    ('INVESTIGATION', 'Investigation Room'),
                    ('PHARMACY', 'Pharmacy Counter'),
                    ('OPTICAL', 'Optical Counter'),
                    ('COUNSELING', 'Counseling Room'),
                    ('ADMISSION', 'Admission Desk'),
                    ('NURSING', 'Nursing Station'),
                ],
                help_text='Type of service point (consultation room, cashier, triage, lab…)',
            ),
        ),

        # ── 5. ServiceCounter: add anti_starvation_minutes ───────────────────
        migrations.AddField(
            model_name='servicecounter',
            name='anti_starvation_minutes',
            field=models.PositiveSmallIntegerField(
                default=45,
                help_text="Shared services only: after this many minutes, a lower-tier patient's effective priority is boosted one level.",
            ),
        ),

        # ── 6. QueueToken: add zone FK ───────────────────────────────────────
        migrations.AddField(
            model_name='queuetoken',
            name='zone',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tokens',
                to='qms.zone',
                help_text='Zone resolved from patient tier at ticket issuance.',
            ),
        ),
    ]
