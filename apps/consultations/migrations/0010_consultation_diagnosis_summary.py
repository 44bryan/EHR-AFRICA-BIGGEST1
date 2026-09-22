from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0009_add_follow_up_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='consultation',
            name='diagnosis_summary',
            field=models.CharField(
                blank=True,
                help_text='Quick diagnosis summary e.g. "RE: Glaucoma suspect | LE: Dry eye"',
                max_length=500,
            ),
        ),
    ]
