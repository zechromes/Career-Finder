"""Content-addressed cache of public job vectors; candidate queries are not cached."""

import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path


# Cache public posting vectors while delegating private candidate queries directly.
class CachedJobEmbeddings:
    def __init__(
        self, delegate, directory, model="text-embedding-3-small", ttl_days=30
    ):
        self.delegate = delegate
        self.directory = Path(directory)
        self.model = model
        self.ttl = ttl_days * 86400

    # Send candidate queries to the delegate without caching private profile text.
    def embed_query(self, text):
        return self.delegate.embed_query(text)

    # Reuse valid cached job vectors and request only missing or expired embeddings.
    def embed_documents(self, texts):
        keys = [
            hashlib.sha256((self.model + "\0focused-v1\0" + text).encode()).hexdigest()
            for text in texts
        ]
        found = {}
        for key in dict.fromkeys(keys):
            path = self.directory / f"{key}.json"
            try:
                if time.time() - path.stat().st_mtime <= self.ttl:
                    vector = json.loads(path.read_text())
                    if (
                        isinstance(vector, list)
                        and vector
                        and all(
                            isinstance(x, (int, float)) and math.isfinite(x)
                            for x in vector
                        )
                    ):
                        found[key] = vector
            except (OSError, ValueError, TypeError):
                pass
        # Batch identical uncached texts once, then restore the caller’s original order.
        missing = {key: text for key, text in zip(keys, texts) if key not in found}
        if missing:
            vectors = self.delegate.embed_documents(list(missing.values()))
            if len(vectors) != len(missing):
                raise ValueError("Embedding response count does not match job count")
            for key, vector in zip(missing, vectors):
                found[key] = vector
                # A unique temporary file prevents readers from observing partial vectors.
                temporary = self.directory / f".{uuid.uuid4().hex}.tmp"
                try:
                    self.directory.mkdir(parents=True, exist_ok=True)
                    temporary.write_text(json.dumps(vector))
                    os.replace(temporary, self.directory / f"{key}.json")
                except OSError:
                    pass  # Cache failures must not fail a search.
                finally:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
        return [found[key] for key in keys]
