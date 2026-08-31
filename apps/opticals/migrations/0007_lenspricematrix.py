"""Add LensPriceMatrix model."""
import django.db.models
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('opticals', '0006_order_measurements_qc'),
    ]

    operations = [
        migrations.CreateModel(
            name='LensPriceMatrix',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='accounts.user',
                )),
                ('lens_type', models.CharField(
                    choices=[
                        ('SV', 'Single Vision'), ('BIFOCAL', 'Bifocal'),
                        ('PROGRESSIVE', 'Progressive'), ('OCCUPATIONAL', 'Occupational'),
                        ('CONTACT', 'Contact Lens'),
                    ],
                    max_length=20,
                )),
                ('refractive_index', models.DecimalField(
                    decimal_places=2, max_digits=4,
                    help_text='e.g. 1.50, 1.56, 1.60, 1.67, 1.74',
                )),
                ('coating', models.CharField(
                    choices=[
                        ('NONE', 'No Coating'), ('AR', 'Anti-Reflective'),
                        ('BLUE', 'Blue-Light Filter'), ('PHOTO', 'Photochromic (Transitions)'),
                        ('POLAR', 'Polarised'), ('UV400', 'UV400'),
                        ('SCRATCH', 'Scratch-Resistant'), ('HYDRO', 'Hydrophobic'),
                    ],
                    default='NONE', max_length=20,
                )),
                ('power_band', models.CharField(
                    choices=[
                        ('LOW', '0.00 to ±3.00'), ('MED', '±3.25 to ±6.00'),
                        ('HIGH', '±6.25 to ±10.00'), ('VHIGH', '±10.25 and above'),
                    ],
                    default='LOW', max_length=10,
                )),
                ('price', models.DecimalField(
                    decimal_places=2, max_digits=10,
                    help_text='Selling price in FCFA',
                )),
            ],
            options={
                'ordering': ['lens_type', 'refractive_index', 'coating', 'power_band'],
                'unique_together': {('lens_type', 'refractive_index', 'coating', 'power_band')},
                'verbose_name': 'Lens Price Matrix Entry',
                'verbose_name_plural': 'Lens Price Matrix',
            },
        ),
    ]
