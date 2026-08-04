from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('patients', '0029_patientdocument'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MortuaryAdmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('body_number', models.CharField(max_length=30, unique=True)),
                ('full_name', models.CharField(max_length=200)),
                ('age_years', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('gender', models.CharField(choices=[('M', 'Male'), ('F', 'Female'), ('U', 'Unknown')], max_length=10)),
                ('date_of_death', models.DateTimeField()),
                ('place_of_death', models.CharField(blank=True, max_length=200)),
                ('cause_of_death', models.CharField(
                    choices=[
                        ('NATURAL', 'Natural'), ('ACCIDENT', 'Accident'),
                        ('HOMICIDE', 'Homicide'), ('SUICIDE', 'Suicide'),
                        ('UNDETERMINED', 'Undetermined'), ('PENDING', 'Pending Investigation'),
                    ],
                    default='PENDING', max_length=20
                )),
                ('provisional_cause_text', models.TextField(blank=True)),
                ('body_condition', models.CharField(
                    choices=[
                        ('GOOD', 'Good'), ('DECOMPOSED', 'Decomposed'), ('BURNED', 'Burned'),
                        ('TRAUMATIC', 'Traumatic Injuries'), ('OTHER', 'Other'),
                    ],
                    default='GOOD', max_length=20
                )),
                ('identifying_marks', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('RECEIVED', 'Received'), ('IN_STORAGE', 'In Storage'),
                        ('POST_MORTEM', 'Post-Mortem Pending'), ('RELEASED', 'Released'),
                        ('TRANSFERRED', 'Transferred'),
                    ],
                    default='RECEIVED', max_length=20
                )),
                ('received_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('next_of_kin_name', models.CharField(blank=True, max_length=200)),
                ('next_of_kin_phone', models.CharField(blank=True, max_length=20)),
                ('next_of_kin_relationship', models.CharField(blank=True, max_length=100)),
                ('police_case_number', models.CharField(blank=True, max_length=50)),
                ('doctor_who_certified', models.CharField(blank=True, max_length=200)),
                ('notes', models.TextField(blank=True)),
                ('patient', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='mortuary_admissions', to='patients.patient'
                )),
                ('received_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='bodies_received', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-received_at']},
        ),
        migrations.CreateModel(
            name='MortuaryStorage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('compartment_number', models.CharField(max_length=20, unique=True)),
                ('section', models.CharField(blank=True, max_length=50)),
                ('status', models.CharField(
                    choices=[
                        ('AVAILABLE', 'Available'), ('OCCUPIED', 'Occupied'), ('MAINTENANCE', 'Under Maintenance'),
                    ],
                    default='AVAILABLE', max_length=20
                )),
                ('temperature_celsius', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('notes', models.TextField(blank=True)),
                ('current_body', models.OneToOneField(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='storage_compartment', to='mortuary.mortuaryadmission'
                )),
            ],
            options={'ordering': ['compartment_number']},
        ),
        migrations.CreateModel(
            name='PostMortemRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('pm_type', models.CharField(
                    choices=[
                        ('CLINICAL', 'Clinical / Hospital'), ('MEDICOLEGAL', 'Medico-Legal'),
                        ('CORONER', "Coroner's Request"),
                    ],
                    max_length=20
                )),
                ('status', models.CharField(
                    choices=[
                        ('REQUESTED', 'Requested'), ('APPROVED', 'Approved'),
                        ('IN_PROGRESS', 'In Progress'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled'),
                    ],
                    default='REQUESTED', max_length=20
                )),
                ('pathologist', models.CharField(blank=True, max_length=200)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('reason', models.TextField()),
                ('findings', models.TextField(blank=True)),
                ('final_cause_of_death', models.CharField(blank=True, max_length=300)),
                ('report_reference', models.CharField(blank=True, max_length=100)),
                ('admission', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='post_mortem', to='mortuary.mortuaryadmission'
                )),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pm_requests_approved', to=settings.AUTH_USER_MODEL
                )),
                ('requested_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pm_requests_made', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='BodyRelease',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('released_to_name', models.CharField(max_length=200)),
                ('released_to_id_type', models.CharField(blank=True, max_length=50)),
                ('released_to_id_number', models.CharField(blank=True, max_length=50)),
                ('released_to_phone', models.CharField(blank=True, max_length=20)),
                ('relationship', models.CharField(blank=True, max_length=100)),
                ('funeral_home', models.CharField(blank=True, max_length=200)),
                ('transport_provider', models.CharField(blank=True, max_length=200)),
                ('released_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('death_certificate_issued', models.BooleanField(default=False)),
                ('certificate_number', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('admission', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='release', to='mortuary.mortuaryadmission'
                )),
                ('released_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='bodies_released', to=settings.AUTH_USER_MODEL
                )),
                ('created_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
                ('updated_by', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL
                )),
            ],
            options={'ordering': ['-released_at']},
        ),
    ]
