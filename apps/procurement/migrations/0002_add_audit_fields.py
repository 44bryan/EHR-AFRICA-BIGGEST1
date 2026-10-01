"""
Add missing AuditModel fields (deleted_by_id, deletion_reason, updated_by_id, created_by_id)
that were omitted from the hand-written 0001_initial migration.
"""
from django.conf import settings
from django.db import migrations


PROCUREMENT_TABLES = [
    'procurement_purchaserequest',
    'procurement_purchaserequestitem',
    'procurement_purchaseorder',
    'procurement_poitem',
    'procurement_goodsreceivednote',
    'procurement_grnitem',
]

forward_sql = []
for table in PROCUREMENT_TABLES:
    forward_sql += [
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deleted_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS deletion_reason text NOT NULL DEFAULT '';",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_by_id uuid REFERENCES accounts_user(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;",
    ]


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql='\n'.join(forward_sql),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
