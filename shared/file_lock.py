"""Cross-platform advisory file locking for shared JSON files on network storage."""
import time
from contextlib import contextmanager

try:
    import msvcrt
    WINDOWS_LOCKING_AVAILABLE = True
except ImportError:
    WINDOWS_LOCKING_AVAILABLE = False

try:
    import fcntl
    UNIX_LOCKING_AVAILABLE = True
except ImportError:
    UNIX_LOCKING_AVAILABLE = False


class FileLockError(Exception):
    """Raised when a file lock cannot be acquired within the timeout."""


@contextmanager
def locked_file(file_handle, timeout: float = 5.0, retry_delay: float = 0.1):
    """Acquire an exclusive advisory lock on an already-open file handle.

    No-op on platforms without msvcrt or fcntl.

    Args:
        file_handle: Open file handle to lock.
        timeout: Maximum time to wait for the lock, in seconds.
        retry_delay: Delay between lock attempts, in seconds.

    Raises:
        FileLockError: If the lock isn't acquired within timeout.
    """
    start_time = time.time()
    locked = False

    try:
        if WINDOWS_LOCKING_AVAILABLE:
            while time.time() - start_time < timeout:
                try:
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(retry_delay)
            if not locked:
                raise FileLockError(f"Could not acquire lock within {timeout} seconds")

        elif UNIX_LOCKING_AVAILABLE:
            while time.time() - start_time < timeout:
                try:
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError:
                    time.sleep(retry_delay)
            if not locked:
                raise FileLockError(f"Could not acquire lock within {timeout} seconds")

        yield

    finally:
        if locked:
            try:
                if WINDOWS_LOCKING_AVAILABLE:
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                elif UNIX_LOCKING_AVAILABLE:
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass  # Ignore unlock errors


if __name__ == "__main__":
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with open(tmp_path, 'r+') as f:
            with locked_file(f):
                f.write("locked ok")
        with open(tmp_path) as f:
            assert f.read() == "locked ok"
        print("file_lock self-check OK")
    finally:
        os.unlink(tmp_path)
