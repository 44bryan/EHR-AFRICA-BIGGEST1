from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0034_visit_referring_doctor'),
    ]

    operations = [
        migrations.AddField(
            model_name='visit',
            name='routing_note',
            field=models.TextField(blank=True, help_text='Note from the routing doctor visible to the receiving department.'),
        ),
    ]
