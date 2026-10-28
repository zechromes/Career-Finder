"""Bounded cache of collected postings; never stores candidate profiles or credentials."""

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

from backend.paths import JOB_COLLECTION_CACHE_DIR

_LOCKS = [threading.Lock() for _ in range(64)]
LOGGER = logging.getLogger(__name__)


def _integer_setting(name, default, maximum):
    try:
        return min(maximum, max(0, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


class CollectionCache:
    def __init__(self, directory=None, ttl=None, max_entries=None, clock=time.time):
        self.directory = Path(
            directory
            or os.getenv("JOB_COLLECTION_CACHE_DIR")
            or JOB_COLLECTION_CACHE_DIR
        )
        self.ttl = (
            _integer_setting("JOB_COLLECTION_CACHE_TTL_SECONDS", 900, 86400)
            if ttl is None
            else ttl
        )
        self.max_entries = (
            _integer_setting("JOB_COLLECTION_CACHE_MAX_ENTRIES", 256, 4096)
            if max_entries is None
            else max_entries
        )
        self.clock = clock

    def _read(self, path):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            age = self.clock() - payload["fetched_at"]
            jobs = payload["jobs"]
            if (
                payload["version"] == 1
                and 0 <= age < self.ttl
                and isinstance(jobs, list)
                and jobs
                and all(isinstance(job, dict) for job in jobs)
            ):
                # Nested feed snapshots must not acquire a fresh TTL simply by
                # being included in a newer aggregate search-cache entry.
                fetched = [
                    job.get("collection_fetched_at", payload["fetched_at"])
                    for job in jobs
                ]
                if any(not isinstance(value, (int, float)) for value in fetched):
                    return None
                if self.clock() - min(fetched) >= self.ttl:
                    return None
                return jobs
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return None

    def _write(self, path, jobs):
        temporary = path.with_name(f".{uuid.uuid4().hex}.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(
                    {"version": 1, "fetched_at": self.clock(), "jobs": jobs},
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, path)
            # Only manage our hashed cache entries, never arbitrary user files.
            entries = []
            for entry in self.directory.glob("*.json"):
                if len(entry.stem) != 64 or any(
                    c not in "0123456789abcdef" for c in entry.stem
                ):
                    continue
                modified = entry.stat().st_mtime
                if self.clock() - modified >= self.ttl:
                    entry.unlink(missing_ok=True)
                else:
                    entries.append((modified, entry))
            for _, entry in sorted(entries)[: max(0, len(entries) - self.max_entries)]:
                entry.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            LOGGER.warning(
                "Collection cache write unavailable; using collected results."
            )
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def collect(self, parameters, fetch, should_cancel=None, force_refresh=False):
        """Return (jobs, cache_hit); fetch returns (jobs, safe_to_cache)."""
        cancelled = should_cancel or (lambda: False)
        if cancelled():
            return [], False
        if self.ttl <= 0 or self.max_entries <= 0:
            jobs, _ = fetch()
            return ([] if cancelled() else jobs), False
        digest = hashlib.sha256(
            json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        path = self.directory / f"{digest}.json"
        lock = _LOCKS[int(digest[:8], 16) % len(_LOCKS)]
        while not lock.acquire(timeout=0.1):
            if cancelled():
                return [], False
        try:
            if cancelled():
                return [], False
            if not force_refresh:
                jobs = self._read(path)
                if jobs is not None:
                    return jobs, True
            # Invalidating before refresh prevents reuse after an unsuccessful forced refresh.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            jobs, safe_to_cache = fetch()
            if cancelled():
                return [], False
            # Empty results may be silent throttling. Never cache them or a partial failure.
            if jobs and safe_to_cache:
                self._write(path, jobs)
            return jobs, False
        finally:
            lock.release()
