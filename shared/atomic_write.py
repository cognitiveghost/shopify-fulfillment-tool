"""Atomic JSON writes (temp file + rename) for files on shared network storage."""
import json
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def atomic_write_json(path, data, *, indent=2, ensure_ascii=False, retries=3, retry_delay=0.15):
    """Write `data` as JSON to `path` atomically (temp file in same dir + rename).

    Retries with backoff to tolerate transient SMB errors. Raises the last
    exception if all attempts fail.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    last_exc = None
    for attempt in range(retries):
        tmp_path = None
        try:
            fd, tmp_str = tempfile.mkstemp(
                dir=path.parent, prefix=f".{path.stem}_tmp_", suffix=path.suffix
            )
            tmp_path = Path(tmp_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            except Exception:
                os.close(fd)
                raise
            tmp_path.replace(path)
            return
        except Exception as e:
            last_exc = e
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception as e:
                    logger.debug(f"Could not remove temp file {tmp_path}: {e}")
            if attempt < retries - 1:
                time.sleep(retry_delay)

    raise last_exc


if __name__ == "__main__":
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "sub" / "data.json"
        atomic_write_json(target, {"a": 1})
        assert json.loads(target.read_text()) == {"a": 1}
        assert not list(target.parent.glob(".*_tmp_*"))
        print("atomic_write self-check OK")
