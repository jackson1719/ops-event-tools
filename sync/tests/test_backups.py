import tarfile

from django.conf import settings
from django.test import TestCase, override_settings

from sync.backups import _backup_files, last_backup_time, perform_backup


class BackupTests(TestCase):
    def test_backup_creates_archive_with_db(self):
        path = perform_backup()
        self.assertTrue(path.endswith(".tar.gz"))
        with tarfile.open(path) as tar:
            names = tar.getnames()
        self.assertIn("db.sqlite3", names)
        self.assertIsNotNone(last_backup_time())

    @override_settings(BACKUP_KEEP=2)
    def test_retention_prunes_oldest(self):
        for _ in range(3):
            perform_backup()
        # Same-second runs share a filename; pad if needed
        while len(_backup_files()) < 3:
            newest = _backup_files()[-1]
            clone = newest.with_name(newest.name.replace("backup-", "backup-0"))
            clone.write_bytes(newest.read_bytes())
        perform_backup()
        self.assertLessEqual(len(_backup_files()), settings.BACKUP_KEEP)
