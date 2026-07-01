"""
Core Celery tasks: automated database backup, external drive copy.
"""
import os
import shutil
import time
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('apps.core')


@shared_task(name='core.daily_backup', bind=True, max_retries=2, default_retry_delay=300)
def daily_backup_task(self):
    """
    Daily automated PostgreSQL backup.
    - Runs pg_dump via the backup_db management command
    - Logs result to BackupLog
    - Optionally copies to BACKUP_EXTERNAL_PATH (e.g. /mnt/external_drive/backups)
    Scheduled via Celery Beat: every day at 02:00 Africa/Douala
    """
    from apps.core.models import BackupLog
    import subprocess

    start_time = time.time()
    backup_dir = Path(getattr(settings, 'BACKUP_DIR', settings.BASE_DIR / 'backups'))
    backup_dir.mkdir(parents=True, exist_ok=True)

    log = BackupLog.objects.create(
        status=BackupLog.Status.RUNNING,
        trigger=BackupLog.TriggerSource.CELERY,
    )

    try:
        # Build the pg_dump command directly (mirrors backup_db management command)
        db = settings.DATABASES.get('default', {})
        engine = db.get('ENGINE', '')

        if 'postgresql' not in engine and 'postgis' not in engine:
            raise RuntimeError(f'daily_backup_task: not a PostgreSQL database (engine={engine})')

        host     = db.get('HOST', 'localhost')
        port     = str(db.get('PORT', 5432))
        name     = db.get('NAME', '')
        user     = db.get('USER', '')
        password = db.get('PASSWORD', '')

        timestamp = timezone.localtime(timezone.now()).strftime('%Y%m%d_%H%M%S')
        filename  = f'ehr_backup_{timestamp}.dump'
        filepath  = backup_dir / filename

        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password

        cmd = [
            'pg_dump',
            '--format=custom',
            '--no-password',
            f'--host={host}',
            f'--port={port}',
            f'--username={user}',
            f'--file={filepath}',
            name,
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            raise RuntimeError(f'pg_dump exit {result.returncode}: {result.stderr[:500]}')

        size_mb = filepath.stat().st_size / (1024 * 1024)
        duration = time.time() - start_time

        # Rotate old backups — keep last 30
        keep = getattr(settings, 'BACKUP_KEEP', 30)
        dumps = sorted(backup_dir.glob('ehr_backup_*.dump'))
        for old in dumps[:-keep]:
            old.unlink(missing_ok=True)

        # Copy to external drive if configured
        external_path_str = getattr(settings, 'BACKUP_EXTERNAL_PATH', '')
        copied = False
        ext_dest = ''
        if external_path_str:
            external_dir = Path(external_path_str)
            if external_dir.exists():
                ext_dest = str(external_dir / filename)
                shutil.copy2(str(filepath), ext_dest)
                copied = True
                logger.info('Backup copied to external: %s', ext_dest)
            else:
                logger.warning('External backup path not found: %s', external_path_str)

        log.filename = filename
        log.output_path = str(filepath)
        log.size_mb = round(size_mb, 2)
        log.status = BackupLog.Status.SUCCESS
        log.duration_seconds = round(duration, 1)
        log.copied_to_external = copied
        log.external_path = ext_dest
        log.save()

        logger.info('daily_backup_task completed: %s (%.1f MB, %.1fs)', filename, size_mb, duration)
        return {'status': 'success', 'filename': filename, 'size_mb': round(size_mb, 2)}

    except Exception as exc:
        duration = time.time() - start_time
        log.status = BackupLog.Status.FAILED
        log.error_message = str(exc)
        log.duration_seconds = round(duration, 1)
        log.save()
        logger.error('daily_backup_task FAILED: %s', exc)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {'status': 'failed', 'error': str(exc)}
