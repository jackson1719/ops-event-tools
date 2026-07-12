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


def _config():
    from accounts.models import SiteConfig
    return SiteConfig.load()


def perform_backup() -> str:
    """Take a backup now. Returns the archive path. Raises on failure."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = settings.BACKUP_DIR / f"{BACKUP_PREFIX}{stamp}.tar.gz"

    db = settings.DATABASES["default"]
    with tempfile.TemporaryDirectory() as tmp:
        members = []

        if db["ENGINE"].endswith("sqlite3"):
            # Snapshot through Django's own connection: the sqlite backup API
            # is safe mid-use on the same connection, and opening a second
            # connection to the file can deadlock against an open write
            # transaction (e.g. the surrounding test-case transaction).
            from django.db import connection as django_connection

            snapshot = os.path.join(tmp, "db.sqlite3")
            django_connection.ensure_connection()
            dest = sqlite3.connect(snapshot)
            try:
                with dest:
                    django_connection.connection.backup(dest)
            finally:
                dest.close()
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

        # Land under a temp name on the destination filesystem, then atomically
        # rename — a crash mid-copy can't leave a truncated "latest" archive
        # that would suppress future backups.
        staging = settings.BACKUP_DIR / f".{BACKUP_PREFIX}{stamp}.tar.gz.partial"
        shutil.move(tmp_archive, staging)
        os.replace(staging, archive_path)

    # Retention (never delete below 1, even if misconfigured to 0)
    keep = max(1, _config().backup_keep)
    files = _backup_files()
    for old in files[: max(0, len(files) - keep)]:
        old.unlink(missing_ok=True)
        log.info("Backup retention: removed %s", old.name)

    log.info("Backup written: %s (%.1f MB)", archive_path.name, archive_path.stat().st_size / 1e6)
    return str(archive_path)


def perform_backup_locked() -> str:
    """perform_backup guarded by the shared exclusive lock so a manual trigger
    and the scheduler (or two clicks) can never run concurrently."""
    from .locks import Locked, exclusive

    try:
        with exclusive("backup"):
            return perform_backup()
    except Locked:
        log.info("Backup already in progress; skipping.")
        return ""


def _backup_due(cfg) -> bool:
    last = last_backup_time()
    if last is None:
        return True
    age_hours = (datetime.now() - last).total_seconds() / 3600
    return age_hours >= cfg.backup_interval_hours


def _scheduler_loop():
    from django.db import connection

    while True:
        try:
            cfg = _config()
            if cfg.backup_enabled and _backup_due(cfg):
                perform_backup_locked()
        except Exception:
            log.exception("Scheduled backup failed")
        finally:
            connection.close()
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_backup_scheduler():
    """Started with the server. A single-runner flock ensures only ONE process
    across all gunicorn workers and both systemd units runs the loop; the rest
    skip. Enable/disable and pacing come from SiteConfig, re-checked each cycle."""
    from .locks import single_runner

    if not single_runner("backup-scheduler"):
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="backup-scheduler")
    t.start()
    log.info("Backup scheduler started (config from Site Settings, dir %s)", settings.BACKUP_DIR)
