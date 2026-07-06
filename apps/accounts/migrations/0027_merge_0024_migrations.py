# Merge: 0024_add_general_physician_role + 0024_hospitalconfig_settings -> 0026_employee_id_optional chain

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0024_add_general_physician_role'),
        ('accounts', '0026_employee_id_optional'),
    ]

    operations = [
    ]
