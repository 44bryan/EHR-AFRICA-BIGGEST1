"""Add hospital_logo and hospital_tagline to HospitalConfig for PDF letterheads."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0040_add_procurement_officer_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_tagline',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='Tagline / Motto'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_logo',
            field=models.ImageField(blank=True, null=True, upload_to='hospital/', verbose_name='Hospital Logo'),
        ),
    ]
