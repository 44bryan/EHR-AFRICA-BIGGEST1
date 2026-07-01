"""
Management command: python manage.py backup_db

Creates a timestamped PostgreSQL dump and (optionally) rotates old backups.

Usage:
    python manage.py backup_db
    python manage.py backup_db --output-dir /var/backups/ehr
    python manage.py backup_db --keep 14            # keep last 14 backups
    python manage.py backup_db --no-rotate          # skip rotation

Requirements:
    pg_dump must be installed on the server (comes with PostgreSQL client tools).
    DATABASE_URL must use postgres:// scheme.
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create a timestamped PostgreSQL backup and rotate old ones'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default=str(settings.BASE_DIR / 'backups'),
            help='Directory to store backup files (default: <project>/backups/)',
        )
        parser.add_argument(
            '--keep',
            type=int,
            default=30,
            help='Number of most-recent backups to retain (default: 30)',
        )
        parser.add_argument(
            '--no-rotate',
            action='store_true',
            help='Skip deletion of old backups',
        )

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        # ── Parse DATABASE_URL ────────────────────────────────────────────────
        db = settings.DATABASES.get('default', {})
        engine = db.get('ENGINE', '')

        if 'postgresql' not in engine and 'postgis' not in engine:
            raise CommandError(
                'backup_db only supports PostgreSQL. '
                f'Current engine: {engine}'
            )

        host     = db.get('HOST', 'localhost')
        port     = str(db.get('PORT', 5432))
        name     = db.get('NAME', '')
        user     = db.get('USER', '')
        password = db.get('PASSWORD', '')

        if not name:
            raise CommandError('DATABASE_URL / DATABASES["default"]["NAME"] is not set.')

        # ── Build filename ────────────────────────────────────────────────────
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename  = f'ehr_backup_{timestamp}.dump'
        filepath  = output_dir / filename

        # ── Run pg_dump ───────────────────────────────────────────────────────
        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password

        cmd = [
            'pg_dump',
            '--format=custom',          # compressed binary format — best for pg_restore
            '--no-password',
            f'--host={host}',
            f'--port={port}',
            f'--username={user}',
            f'--file={filepath}',
            name,
        ]

        self.stdout.write(f'Backing up database "{name}" → {filepath} …')

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,            # 10-minute timeout
            )
        except FileNotFoundError:
            raise CommandError(
                'pg_dump not found. Install PostgreSQL client tools:\n'
                '  Ubuntu/Debian: sudo apt install postgresql-client\n'
                '  RHEL/CentOS:   sudo yum install postgresql\n'
            )
        except subprocess.TimeoutExpired:
            raise CommandError('pg_dump timed out after 10 minutes.')

        if result.returncode != 0:
            raise CommandError(
                f'pg_dump failed (exit {result.returncode}):\n{result.stderr}'
            )

        size_mb = filepath.stat().st_size / (1024 * 1024)
        self.stdout.write(
            self.style.SUCCESS(f'  Backup complete: {filename} ({size_mb:.1f} MB)')
        )

        # ── Rotate old backups ────────────────────────────────────────────────
        if not options['no_rotate']:
            keep = options['keep']
            dumps = sorted(output_dir.glob('ehr_backup_*.dump'))
            to_delete = dumps[:-keep] if len(dumps) > keep else []
            for old in to_delete:
                old.unlink()
                self.stdout.write(f'  Removed old backup: {old.name}')
            remaining = len(dumps) - len(to_delete)
            self.stdout.write(f'  Rotation complete: {remaining} backup(s) retained.')

        self.stdout.write(self.style.SUCCESS('\nBackup finished successfully.'))
        self.stdout.write(
            f'  Restore with:\n'
            f'    pg_restore --host={host} --port={port} --username={user} '
            f'--dbname={name} --clean {filepath}'
        )
