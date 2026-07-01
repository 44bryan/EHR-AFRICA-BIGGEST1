from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0025_alter_user_must_change_password'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='employee_id',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
    ]
