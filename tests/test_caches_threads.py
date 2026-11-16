"""The demo serves requests from worker threads; the SQLite caches must allow that."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from buglens.kvstore import KVStore
from buglens.retrieval.embed_cache import EmbeddingCache


def test_kvstore_usable_from_other_threads(tmp_path):
    store = KVStore(tmp_path / "kv.sqlite")
    store.put_many({"a": [1, 2]})
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda i: store.get_many(["a"]), range(8)))
    assert all(r == {"a": [1, 2]} for r in results)


def test_embedding_cache_usable_from_other_threads(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.sqlite")

    def work(i):
        cache.put_many({f"k{i}": np.ones(4) * i})
        return cache.get_many([f"k{i}"])[f"k{i}"][0]

    with ThreadPoolExecutor(4) as ex:
        assert sorted(ex.map(work, range(8))) == list(range(8))
