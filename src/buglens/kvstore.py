"""A tiny SQLite key-value store for JSON values (compressed).

Concept: content-addressed caching. If the cache key is a hash of everything
the value depends on (here: git blob id + path + settings), the cache can never
serve a stale value, and work is shared across commits automatically. SQLite
gives atomic writes and fast batched lookups in a single file, with no server.
"""

from __future__ import annotations

import json
import sqlite3
import zlib
from pathlib import Path


class KVStore:
    def __init__(self, path: str | Path, table: str = "kv"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.table = table
        self.conn = sqlite3.connect(self.path, timeout=60)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, val BLOB)")

    def get_many(self, keys: list[str]) -> dict[str, object]:
        out: dict[str, object] = {}
        for i in range(0, len(keys), 500):
            batch = keys[i:i + 500]
            q = f"SELECT key, val FROM {self.table} WHERE key IN ({','.join('?' * len(batch))})"
            for k, v in self.conn.execute(q, batch):
                out[k] = json.loads(zlib.decompress(v))
        return out

    def put_many(self, items: dict[str, object]) -> None:
        rows = [(k, zlib.compress(json.dumps(v).encode())) for k, v in items.items()]
        with self.conn:
            self.conn.executemany(
                f"INSERT OR REPLACE INTO {self.table} (key, val) VALUES (?, ?)", rows)

    def close(self) -> None:
        self.conn.close()
