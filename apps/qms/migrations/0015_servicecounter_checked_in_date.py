from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0014_queuetoken_origin_zone'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicecounter',
            name='checked_in_date',
            field=models.DateField(
                null=True, blank=True,
                help_text='Date the currently assigned staff checked in. Auto-set on check-in, cleared on check-out.'
            ),
        ),
    ]
