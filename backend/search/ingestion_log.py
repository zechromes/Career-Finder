"""Bounded record of postings dropped during ingestion; reasons, never fit judgments."""

from contextlib import contextmanager
import contextvars
import hashlib
import json
import os
import time
import uuid

# Per-stage caps keep run files small; counts stay exact beyond the caps.
CAPS = {"filter": 120, "description": 60, "budget": 60, "deduplicate": 50}
DESCRIPTION_LIMIT = 6000
# Stages that can remove a posting that would otherwise reach ranking.
LOSS_STAGES = {"filter", "description", "budget"}
_current = contextvars.ContextVar("ingestion_log", default=None)


def _identity(job):
    from backend.search.collection import _job_key

    return _job_key(job)


class IngestionLog:
    def __init__(self):
        self.collected = {}
        self.counts = {}
        self.dropped = []
        self.omitted = 0
        self.cached = False
        self._seen = set()

    def add_collected(self, board, count):
        self.collected[board] = self.collected.get(board, 0) + count

    def drop(self, job, stage, reason, duplicate_of=None):
        board = job.get("source_platform") or job.get("source") or "unknown"
        key = f"{stage}|{reason}|{board}"
        self.counts[key] = self.counts.get(key, 0) + 1
        identity = _identity(job)
        # Jobs already in the workspace are not losses; count them only.
        if reason == "already in this workspace" or identity in self._seen:
            return
        self._seen.add(identity)
        if sum(row["stage"] == stage for row in self.dropped) >= CAPS.get(stage, 0):
            self.omitted += 1
            return
        self.dropped.append(
            dict(
                id="dropped-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                title=str(job.get("title", "")),
                company=str(job.get("company", "")),
                location=str(job.get("location", "")),
                url=str(job.get("url", "")),
                board=board,
                stage=stage,
                reason=reason,
                description=str(job.get("description", ""))[:DESCRIPTION_LIMIT],
                duplicate_of=duplicate_of,
            )
        )

    def to_dict(self, kept):
        return dict(
            recorded_at=time.time(),
            cached=self.cached,
            collected=self.collected,
            kept=kept,
            counts=[
                dict(stage=stage, reason=reason, board=board, count=count)
                for key, count in sorted(self.counts.items())
                for stage, reason, board in [key.split("|", 2)]
            ],
            omitted=self.omitted,
            dropped=self.dropped,
        )


@contextmanager
def recording(log):
    token = _current.set(log)
    try:
        yield log
    finally:
        _current.reset(token)


def active():
    return _current.get() is not None


def drop(job, stage, reason, duplicate_of=None):
    log = _current.get()
    if log is not None:
        log.drop(job, stage, reason, duplicate_of)


def collected(board, count):
    log = _current.get()
    if log is not None:
        log.add_collected(board, count)


def mark_cached():
    log = _current.get()
    if log is not None:
        log.cached = True


def record_duplicates(jobs, kept, known=(), workspace=()):
    """Record jobs removed by deduplication, naming the posting each one matched."""
    log = _current.get()
    if log is None:
        return
    from backend.search.collection import _job_key, deduplicate_jobs

    kept_ids = {id(job) for job in kept}
    workspace_ids = {id(job) for job in workspace}
    others = list(kept) + list(known)
    normalize = lambda job: tuple(
        " ".join(str(job.get(field, "")).casefold().split())
        for field in ("company", "title", "location")
    )
    for job in jobs:
        if id(job) in kept_ids:
            continue
        key, identity = _job_key(job), normalize(job)
        match, method = None, ""
        for other in others:
            if other is job:
                continue
            if _job_key(other) == key:
                match, method = other, "same link"
                break
            # Cross-board merges require the same employer, title and location.
            if (
                normalize(other) == identity
                and len(deduplicate_jobs([other, job])) == 1
            ):
                match, method = other, "same title, company and location; near-identical description"
                break
        if match is not None and id(match) in workspace_ids:
            log.drop(job, "deduplicate", "already in this workspace")
            continue
        log.drop(
            job,
            "deduplicate",
            "duplicate posting",
            duplicate_of=(
                dict(
                    title=str(match.get("title", "")),
                    company=str(match.get("company", "")),
                    url=str(match.get("url", "")),
                    board=match.get("source_platform") or "unknown",
                    description=str(match.get("description", ""))[:DESCRIPTION_LIMIT],
                    method=method,
                )
                if match is not None
                else None
            ),
        )


def save(run_dir, log, kept, search):
    """Append this search's ingestion record to the run's ingestion file."""
    path = run_dir / "ingestion.json"
    try:
        data = json.loads(path.read_text()) if path.is_file() else {"searches": []}
    except (OSError, ValueError):
        data = {"searches": []}
    data["searches"].append({**log.to_dict(kept), "search": search})
    temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            json.dump(data, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load(run_dir):
    path = run_dir / "ingestion.json"
    try:
        return json.loads(path.read_text()) if path.is_file() else None
    except (OSError, ValueError):
        return None
