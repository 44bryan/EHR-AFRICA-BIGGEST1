from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0018_preregistration_arrival_tracking'),
        ('departments', '0005_consultationroom'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='consultation_room',
            field=models.ForeignKey(
                blank=True,
                help_text='Consultation room the triage nurse sent this patient to',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='visits',
                to='departments.consultationroom',
            ),
        ),
    ]
