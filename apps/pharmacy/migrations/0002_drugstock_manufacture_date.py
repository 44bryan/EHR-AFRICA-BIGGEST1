from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacy', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='drugstock',
            name='manufacture_date',
            field=models.DateField(
                blank=True, null=True,
                help_text='Manufacturing / production date on the package'
            ),
        ),
    ]
