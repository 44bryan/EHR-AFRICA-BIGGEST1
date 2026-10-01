"""
Add missing AuditModel fields to MaintenanceSchedule and MaintenanceWorkOrder tables.
These were omitted from the hand-written 0035_asset_maintenance migration.
"""
from django.conf import settings
from django.db import migrations


MAINTENANCE_TABLES = [
    'billing_maintenanceschedule',
    'billing_maintenanceworkorder',
]

forward_sql = []
for table in MAINTENANCE_TABLES:
    forward_sql += [
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deletion_reason text NOT NULL DEFAULT '';",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
    ]


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0035_asset_maintenance'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql='\n'.join(forward_sql),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
