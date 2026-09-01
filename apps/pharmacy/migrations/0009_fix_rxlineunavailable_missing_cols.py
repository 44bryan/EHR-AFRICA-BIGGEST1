from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0033_hospitalconfig_enterprise_modules'),
        ('pharmacy', '0008_otc_and_unavailable_lines'),
    ]

    operations = [
        migrations.AddField(
            model_name='rxlineunavailable',
            name='deleted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rxlineunavailable',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to='accounts.user',
            ),
        ),
    ]
