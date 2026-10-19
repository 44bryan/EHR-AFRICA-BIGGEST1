"""
Fix missing created_by_id / updated_by_id on laboratory_labresultamendment.

Migration 0007 was recorded as applied in django_migrations but the two FK
columns were never physically created on the table (confirmed via \d on prod).
Using RunSQL with IF NOT EXISTS makes this safe to re-run.
"""  # noqa: W605
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('laboratory', '0009_antibioticsensitivity_deleted_by_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE laboratory_labresultamendment
                    ADD COLUMN IF NOT EXISTS created_by_id uuid
                        REFERENCES accounts_user(id)
                        ON DELETE SET NULL
                        DEFERRABLE INITIALLY DEFERRED;

                ALTER TABLE laboratory_labresultamendment
                    ADD COLUMN IF NOT EXISTS updated_by_id uuid
                        REFERENCES accounts_user(id)
                        ON DELETE SET NULL
                        DEFERRABLE INITIALLY DEFERRED;

                CREATE INDEX IF NOT EXISTS
                    laboratory_labresultamendment_created_by_id_idx
                    ON laboratory_labresultamendment (created_by_id);

                CREATE INDEX IF NOT EXISTS
                    laboratory_labresultamendment_updated_by_id_idx
                    ON laboratory_labresultamendment (updated_by_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS laboratory_labresultamendment_created_by_id_idx;
                DROP INDEX IF EXISTS laboratory_labresultamendment_updated_by_id_idx;
                ALTER TABLE laboratory_labresultamendment DROP COLUMN IF EXISTS created_by_id;
                ALTER TABLE laboratory_labresultamendment DROP COLUMN IF EXISTS updated_by_id;
            """,
        ),
    ]
