from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('telemedicine', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='teleappointment',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='telesessionnote',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
