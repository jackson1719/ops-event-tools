"""In-app scheduled backups — no external cron/systemd.

A daemon thread (started with the web server, see sync/apps.py) wakes every
15 minutes and takes a backup when the newest one is older than
BACKUP_INTERVAL_HOURS. Each backup is a single tar.gz in BACKUP_DIR holding a
hot SQLite snapshot (sqlite3 backup API — safe while the app is running) and
the media directory. Oldest archives beyond BACKUP_KEEP are pruned.

A lock directory guards against multiple gunicorn workers backing up at once.
"""
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import time
from datetime import datetime

from django.conf import settings

log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 15 * 60
LOCK_STALE_SECONDS = 30 * 60
BACKUP_PREFIX = "backup-"


def _backup_files() -> list:
    if not settings.BACKUP_DIR.is_dir():
        return []
    return sorted(
        p for p in settings.BACKUP_DIR.iterdir()
        if p.name.startswith(BACKUP_PREFIX) and p.name.endswith(".tar.gz")
    )


def last_backup_time() -> datetime | None:
    files = _backup_files()
    if not files:
        return None
    return datetime.fromtimestamp(files[-1].stat().st_mtime)


def perform_backup() -> str:
    """Take a backup now. Returns the archive path. Raises on failure."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = settings.BACKUP_DIR / f"{BACKUP_PREFIX}{stamp}.tar.gz"

    db = settings.DATABASES["default"]
    with tempfile.TemporaryDirectory() as tmp:
        members = []

        if db["ENGINE"].endswith("sqlite3"):
            snapshot = os.path.join(tmp, "db.sqlite3")
            src = sqlite3.connect(db["NAME"])
            try:
                dest = sqlite3.connect(snapshot)
                with dest:
                    src.backup(dest)
                dest.close()
            finally:
                src.close()
            members.append((snapshot, "db.sqlite3"))
        else:
            log.warning("Backup: non-SQLite database (%s) — dump it separately; archiving media only.",
                        db["ENGINE"])

        tmp_archive = os.path.join(tmp, "archive.tar.gz")
        with tarfile.open(tmp_archive, "w:gz") as tar:
            for path, arcname in members:
                tar.add(path, arcname=arcname)
            if settings.MEDIA_ROOT and os.path.isdir(settings.MEDIA_ROOT):
                tar.add(settings.MEDIA_ROOT, arcname="media")

        shutil.move(tmp_archive, archive_path)

    # Retention
    files = _backup_files()
    for old in files[: max(0, len(files) - settings.BACKUP_KEEP)]:
        old.unlink(missing_ok=True)
        log.info("Backup retention: removed %s", old.name)

    log.info("Backup written: %s (%.1f MB)", archive_path.name, archive_path.stat().st_size / 1e6)
    return str(archive_path)


def _acquire_lock() -> bool:
    lock_dir = settings.BACKUP_DIR / ".lock"
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        lock_dir.mkdir()
        return True
    except FileExistsError:
        # Break stale locks from crashed workers
        try:
            if time.time() - lock_dir.stat().st_mtime > LOCK_STALE_SECONDS:
                lock_dir.rmdir()
                lock_dir.mkdir()
                return True
        except OSError:
            pass
        return False


def _release_lock():
    try:
        (settings.BACKUP_DIR / ".lock").rmdir()
    except OSError:
        pass


def _backup_due() -> bool:
    last = last_backup_time()
    if last is None:
        return True
    age_hours = (datetime.now() - last).total_seconds() / 3600
    return age_hours >= settings.BACKUP_INTERVAL_HOURS


def _scheduler_loop():
    while True:
        try:
            if _backup_due() and _acquire_lock():
                try:
                    # Re-check under the lock — another worker may have just finished
                    if _backup_due():
                        perform_backup()
                finally:
                    _release_lock()
        except Exception:
            log.exception("Scheduled backup failed")
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_backup_scheduler():
    if not settings.BACKUP_ENABLED:
        log.info("Backups disabled (BACKUP_ENABLED=false)")
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="backup-scheduler")
    t.start()
    log.info("Backup scheduler started (every %dh, keep %d, dir %s)",
             settings.BACKUP_INTERVAL_HOURS, settings.BACKUP_KEEP, settings.BACKUP_DIR)
