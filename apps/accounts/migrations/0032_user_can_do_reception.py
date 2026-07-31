from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0031_email_nullable'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_do_reception',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Allow this cashier to also register patients and perform reception tasks '
                    '(useful for VIP desks or small departments where one person covers both roles).'
                ),
            ),
        ),
    ]
