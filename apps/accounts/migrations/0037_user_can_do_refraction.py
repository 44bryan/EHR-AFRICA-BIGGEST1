from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0036_user_signature'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_do_refraction',
            field=models.BooleanField(
                default=False,
                help_text='Allow this doctor to also perform refraction (sphere, cylinder, axis, add) '
                          'directly from their consultation workstation. Intended for VIP doctors who '
                          'handle parameters, refraction and consultation in one room.',
            ),
        ),
    ]
