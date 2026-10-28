"""Bounded private assessment cache; failed or cancelled calls are never cached."""

import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

_LOCKS = [threading.Lock() for _ in range(64)]


def cached_assessment(directory, identity, model, operation, cancelled=lambda: False):
    if directory is None:
        return operation()
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, default=str).encode()
    ).hexdigest()
    path = Path(directory) / (key + ".json")
    lock = _LOCKS[int(key[:8], 16) % len(_LOCKS)]
    while not lock.acquire(timeout=0.1):
        if cancelled():
            raise RuntimeError("Run cancelled")
    try:
        if cancelled():
            raise RuntimeError("Run cancelled")
        try:
            record = json.loads(path.read_text())
            if time.time() - record["created_at"] < 7 * 86400:
                return model.model_validate(record["assessment"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        result = operation()
        if cancelled():
            raise RuntimeError("Run cancelled")
        # Deletion uses these same locks; never recreate a removed owner.
        from backend.profiles.storage import LOCK
        from backend.runs import RUNS_LOCK

        with LOCK, RUNS_LOCK:
            if not path.parent.parent.is_dir():
                return result  # Owner was deleted while the request was in flight.
            temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with os.fdopen(
                    os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
                ) as stream:
                    json.dump(
                        {"created_at": time.time(), "assessment": result.model_dump()},
                        stream,
                    )
                os.replace(temporary, path)
                files = sorted(
                    path.parent.glob("*.json"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
                for index, item in enumerate(files):
                    if index >= 1000 or time.time() - item.stat().st_mtime > 7 * 86400:
                        item.unlink(missing_ok=True)
            except OSError:
                pass  # Cache failure cannot discard a valid assessment.
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return result
    finally:
        lock.release()
