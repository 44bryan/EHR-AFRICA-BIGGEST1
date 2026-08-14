from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0035_hospitalconfig_teleconsultation_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='signature',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='staff/signatures/',
                help_text='Upload a PNG/JPG of your handwritten signature (transparent background preferred). '
                          'This will appear on prescriptions, lab reports, and investigation reports.',
            ),
        ),
    ]
