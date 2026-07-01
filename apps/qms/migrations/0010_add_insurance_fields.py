from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0009_alter_queuetoken_service_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='queuetoken',
            name='is_insured',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='queuetoken',
            name='insurance_company',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
