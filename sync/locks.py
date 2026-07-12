"""Filesystem locks (fcntl.flock) shared across gunicorn workers and both
systemd units on the same box.

- single_runner(): non-blocking; the first process to acquire it runs the
  periodic scheduler loop, the rest skip — so with N workers × 2 units we get
  exactly one backup loop and one renewal loop per machine.
- exclusive(): context manager for one-shot critical sections (a backup run, a
  certificate issuance) so manual triggers can't race the scheduler or a
  double-click. Kernel-released on crash — no staleness heuristics.
"""
import contextlib
import fcntl
import logging

from django.conf import settings

log = logging.getLogger(__name__)

# Long-lived handles for single_runner locks must outlive the function call,
# or the FD closes and the lock releases. Keep references here.
_held = []


def _lock_path(name: str):
    return settings.BASE_DIR / f".{name}.lock"


def single_runner(name: str) -> bool:
    """Try to become the sole runner of `name`. Returns True if acquired.
    The lock is held for the process lifetime (never released)."""
    fh = open(_lock_path(name), "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _held.append(fh)  # keep FD open → keep the lock
    return True


@contextlib.contextmanager
def exclusive(name: str, blocking: bool = False):
    """Hold an exclusive lock for a critical section. With blocking=False,
    raises Locked if another holder is active."""
    fh = open(_lock_path(name), "w")
    flags = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        fcntl.flock(fh, flags)
    except OSError:
        fh.close()
        raise Locked(name)
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


class Locked(Exception):
    pass
