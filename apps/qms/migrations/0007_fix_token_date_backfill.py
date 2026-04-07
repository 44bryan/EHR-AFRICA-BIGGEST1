"""
Data migration: set token_date = issued_at__date for all existing tokens.
The previous migration 0006 set token_date = migration run date for all rows,
which breaks the daily-unique constraint once new tickets are issued.
"""
from django.db import migrations


def fix_token_dates(apps, schema_editor):
    QueueToken = apps.get_model('qms', 'QueueToken')
    for token in QueueToken.objects.all():
        correct_date = token.issued_at.date()
        if token.token_date != correct_date:
            token.token_date = correct_date
            token.save(update_fields=['token_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('qms', '0006_fix_token_number_daily_unique'),
    ]

    operations = [
        migrations.RunPython(fix_token_dates, migrations.RunPython.noop),
    ]
