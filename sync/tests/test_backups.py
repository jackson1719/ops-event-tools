import tarfile

from django.test import TransactionTestCase

from accounts.models import SiteConfig
from sync.backups import _backup_files, last_backup_time, perform_backup


class BackupTests(TransactionTestCase):
    """TransactionTestCase: perform_backup snapshots via Django's own sqlite
    connection, which deadlocks inside TestCase's wrapping transaction (an
    environment production never runs in — views/scheduler call it outside
    any transaction)."""
    def test_backup_creates_archive_with_db(self):
        path = perform_backup()
        self.assertTrue(path.endswith(".tar.gz"))
        with tarfile.open(path) as tar:
            names = tar.getnames()
        self.assertIn("db.sqlite3", names)
        self.assertIsNotNone(last_backup_time())

    def test_retention_prunes_oldest(self):
        from django.conf import settings

        cfg = SiteConfig.load()
        cfg.backup_keep = 2
        cfg.save()

        settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(4):
            (settings.BACKUP_DIR / f"backup-2020010{i}-000000.tar.gz").write_bytes(b"old")

        perform_backup()
        files = _backup_files()
        self.assertEqual(len(files), 2)
        # The newly written archive survives; the oldest fakes are pruned
        self.assertGreater(files[-1].stat().st_size, 3)
