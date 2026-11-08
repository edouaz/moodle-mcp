"""One browser operation at a time, across CLI and MCP processes (Mac/Linux)."""
from i18n import translate as tr
import fcntl
from contextlib import contextmanager
from pathlib import Path

LOCK_PATH = Path(__file__).parent / ".moodle.lock"

@contextmanager
def session_lock():
    with LOCK_PATH.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('MOODLE_BUSY: another Moodle operation is in progress; try again.')) from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
