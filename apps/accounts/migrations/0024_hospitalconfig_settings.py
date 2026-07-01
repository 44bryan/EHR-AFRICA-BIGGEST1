from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0023_add_consultation_nurse_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_name',
            field=models.CharField(default='EHR Africa Hospital', max_length=200, verbose_name='Hospital Name'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_address',
            field=models.TextField(blank=True, default='', verbose_name='Address'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_phone',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Phone'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_email',
            field=models.EmailField(blank=True, default='', max_length=254, verbose_name='Email'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_website',
            field=models.URLField(blank=True, default='', verbose_name='Website'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='hospital_tax_id',
            field=models.CharField(blank=True, default='', max_length=60, verbose_name='Tax ID / NIU'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='session_timeout_hours',
            field=models.PositiveSmallIntegerField(default=8, verbose_name='Session Timeout (hours)'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='max_failed_logins',
            field=models.PositiveSmallIntegerField(default=5, verbose_name='Max Failed Login Attempts'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='account_lockout_minutes',
            field=models.PositiveSmallIntegerField(default=30, verbose_name='Account Lockout (minutes)'),
        ),
        migrations.AddField(
            model_name='hospitalconfig',
            name='backup_keep_days',
            field=models.PositiveSmallIntegerField(default=30, verbose_name='Keep Backups (days)'),
        ),
    ]
