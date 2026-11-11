"""SQLite cache of embeddings, keyed by sha1(model_id + text) — FR-R4.

Concept: encoding is the expensive step of dense retrieval (a transformer
forward pass per chunk). The same function text appears in many commits of the
same repository, so caching by *content* means each unique chunk text is
encoded once per model. Vectors are stored as float16 (half the disk, no
measurable effect on cosine ranking) and only cache misses are sent to the GPU.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from buglens.utils import sha1


def cache_key(model_id: str, text: str) -> str:
    return sha1(model_id + "\n" + text)


class EmbeddingCache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=60)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec BLOB)")
        self.hits = 0
        self.misses = 0

    def get_many(self, keys: list[str]) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        for i in range(0, len(keys), 900):
            batch = keys[i:i + 900]
            q = f"SELECT key, vec FROM emb WHERE key IN ({','.join('?' * len(batch))})"
            for k, v in self.conn.execute(q, batch):
                out[k] = np.frombuffer(v, dtype=np.float16)
        return out

    def put_many(self, items: dict[str, np.ndarray]) -> None:
        rows = [(k, np.asarray(v, dtype=np.float16).tobytes()) for k, v in items.items()]
        with self.conn:
            self.conn.executemany("INSERT OR REPLACE INTO emb (key, vec) VALUES (?, ?)", rows)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
