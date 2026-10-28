"""Shared, versioned public-job vectors with immutable per-search eligibility scopes."""

from backend.observability import stage
from collections import OrderedDict
import copy
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from backend.paths import JOB_INDEX_DIR
from backend.search.ranking import BM25Index

_LOCK = threading.RLock()
_CORPORA = OrderedDict()
_MAX_CACHED_DOCUMENTS = 20000


def index_directory():
    return Path(os.getenv("JOB_INDEX_DIR") or JOB_INDEX_DIR)


def _batches(values, size=500):
    for start in range(0, len(values), size):
        yield values[start : start + size]


@stage("index.publish")
def publish(documents, scope_dir, embeddings, should_cancel=None):
    """Add only new posting versions, then atomically publish a complete scope."""
    from langchain_chroma import Chroma
    from chromadb.config import Settings
    from backend.search.collection import _job_key

    cancelled = should_cancel or (lambda: False)
    if cancelled():
        return None
    directory = index_directory()
    now = time.time()
    versions = {}
    for original in documents:
        doc = copy.deepcopy(original)
        # Search-specific hints must never become globally shared job evidence.
        for field in ("requested_location", "pre_screen_note"):
            doc.metadata.pop(field, None)
        posting_id = hashlib.sha256(str(_job_key(doc.metadata)).encode()).hexdigest()
        payload = json.dumps(
            [doc.page_content, doc.metadata], sort_keys=True, ensure_ascii=False
        )
        version_id = hashlib.sha256(
            ("focused-v1:text-embedding-3-small:" + posting_id + payload).encode()
        ).hexdigest()
        doc.metadata.update(
            posting_id=posting_id, version_id=version_id, last_seen_at=now
        )
        versions[version_id] = doc
    with _LOCK:
        store = Chroma(
            persist_directory=str(directory),
            embedding_function=embeddings,
            client_settings=Settings(anonymized_telemetry=False),
            collection_configuration={"hnsw": {"ef_search": 500}},
        )
        if store._collection.configuration["hnsw"]["ef_search"] != 500:
            store._collection.modify(configuration={"hnsw": {"ef_search": 500}})
        # Inactive versions age out; live/paused result snapshots remain in run state.
        expired = store.get(
            where={"last_seen_at": {"$lt": now - 7 * 86400}}, include=[]
        )["ids"]
        for batch in _batches(expired):
            store.delete(ids=batch)
        if expired:
            removed = set(expired)
            for cache_key in list(_CORPORA):
                if cache_key[0] == str(directory.resolve()) and removed.intersection(
                    cache_key[1]
                ):
                    del _CORPORA[cache_key]
        for ids in _batches(list(versions)):
            if cancelled():
                return store
            existing = set(store.get(ids=ids, include=[])["ids"])
            missing = [key for key in ids if key not in existing]
            if missing:
                store.add_documents([versions[key] for key in missing], ids=missing)
            if existing:
                known = [key for key in ids if key in existing]
                store._collection.update(
                    ids=known, metadatas=[{"last_seen_at": now} for _ in known]
                )
        if cancelled():
            return store
        scope = Path(scope_dir)
        scope.mkdir(parents=True, exist_ok=True)
        temporary = scope / f".{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "index_dir": str(directory.resolve()),
                        "ids": list(versions),
                    }
                ),
                encoding="utf-8",
            )
            os.replace(temporary, scope / "job_scope.json")
        finally:
            temporary.unlink(missing_ok=True)
    return store


def read_scope(persist_dir):
    path = Path(persist_dir) / "job_scope.json"
    if not path.exists():
        return None
    scope = json.loads(path.read_text(encoding="utf-8"))
    if (
        scope.get("version") != 1
        or not isinstance(scope.get("index_dir"), str)
        or not isinstance(scope.get("ids"), list)
        or not all(isinstance(key, str) for key in scope["ids"])
    ):
        raise ValueError("Invalid job search index scope. Start a new search.")
    return scope


def corpus(store, scope=None):
    """Return immutable cached documents/lexical statistics for this eligible scope."""
    from langchain_core.documents import Document

    key = (scope["index_dir"], tuple(scope["ids"])) if scope else None
    with _LOCK:
        if key is not None and key in _CORPORA:
            _CORPORA.move_to_end(key)
            return _CORPORA[key]
        if scope:
            records = {}
            for batch in _batches(scope["ids"]):
                data = store.get(ids=batch, include=["documents", "metadatas"])
                records.update(
                    {
                        key: (text, meta)
                        for key, text, meta in zip(
                            data["ids"], data["documents"], data["metadatas"]
                        )
                    }
                )
            if len(records) != len(set(scope["ids"])):
                raise ValueError(
                    "Some indexed postings have expired. Start a new search to refresh them."
                )
            ids = scope["ids"]
            rows = [records[key] for key in ids]
        else:
            data = store.get(include=["documents", "metadatas"])
            ids = data["ids"]
            rows = list(zip(data["documents"], data["metadatas"]))
        docs = [
            Document(page_content=text or "", metadata=meta or {})
            for text, meta in rows
        ]
        lexical = BM25Index([doc.page_content for doc in docs])
        result = ids, docs, lexical
        if key is not None and len(docs) <= _MAX_CACHED_DOCUMENTS:
            _CORPORA[key] = result
            while (
                len(_CORPORA) > 32
                or sum(len(value[0]) for value in _CORPORA.values())
                > _MAX_CACHED_DOCUMENTS
            ):
                _CORPORA.popitem(last=False)
        return result
