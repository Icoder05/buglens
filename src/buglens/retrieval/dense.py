"""Dense (embedding) retrieval with a bi-encoder + FAISS — systems S2 and S4.

Concept: a bi-encoder maps the issue and every code chunk into the same vector
space, trained so that an issue lands near the code that fixes it. With
L2-normalised vectors, the inner product is the cosine similarity, and FAISS
`IndexFlatIP` does exact inner-product search. Unlike BM25 it can match
"crashes when the list is empty" to `if not items:` without shared words.
CodeRankEmbed is asymmetric: queries get an instruction prefix, code does not.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import faiss
import numpy as np

from buglens.chunking.corpus import Corpus
from buglens.config import Config
from buglens.retrieval.embed_cache import EmbeddingCache, cache_key
from buglens.utils import console


def _patch_transformers() -> None:
    """Compatibility shim: CodeRankEmbed's remote code calls
    `get_extended_attention_mask`, removed from transformers 5. Re-add the
    transformers-4 implementation (additive mask: 0 keep, -inf ignore)."""
    import torch
    import transformers

    if hasattr(transformers.PreTrainedModel, "get_extended_attention_mask"):
        return

    def get_extended_attention_mask(self, attention_mask, input_shape=None, device=None,
                                    dtype=None):
        dtype = dtype or self.dtype
        if attention_mask.dim() == 3:
            ext = attention_mask[:, None, :, :]
        else:
            ext = attention_mask[:, None, None, :]
        ext = ext.to(dtype=dtype)
        return (1.0 - ext) * torch.finfo(dtype).min

    transformers.PreTrainedModel.get_extended_attention_mask = get_extended_attention_mask


def model_key(model_id: str) -> str:
    """Cache identity of a model: hub id, or local dir + hash of its weights header."""
    p = Path(model_id)
    if p.exists():
        weights = sorted(p.glob("*.safetensors")) or sorted(p.glob("*.bin"))
        h = hashlib.sha1()
        for w in weights:
            with open(w, "rb") as f:
                h.update(f.read(1 << 20))
            h.update(str(w.stat().st_size).encode())
        return f"local:{p.name}:{h.hexdigest()[:12]}"
    return model_id


def needs_query_prefix(model_id: str) -> bool:
    return "coderankembed" in model_id.lower()


class DenseEncoder:
    def __init__(self, cfg: Config, model_id: str, device: str | None = None):
        import torch
        from sentence_transformers import SentenceTransformer

        _patch_transformers()
        self.cfg = cfg
        self.model_id = model_id
        self.key = model_key(model_id)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = SentenceTransformer(model_id, trust_remote_code=True, device=self.device)
        self.model.max_seq_length = cfg.retrieval.max_seq_length
        if self.device == "cuda" and cfg.retrieval.get("fp16", False):
            self.model.half()
        self.prefix = cfg.retrieval.query_prefix if needs_query_prefix(model_id) else ""
        self.cache = EmbeddingCache(cfg.path("cache") / "embeddings.sqlite")

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        texts = [self.prefix + q for q in queries]
        return self._encode(texts)

    def _encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, batch_size=self.cfg.retrieval.batch_size,
                                 normalize_embeddings=True, convert_to_numpy=True,
                                 show_progress_bar=len(texts) > 2000)
        return np.asarray(vecs, dtype=np.float32)

    def encode_docs(self, texts: list[str]) -> np.ndarray:
        """Encode with the SQLite cache; only misses go through the model."""
        keys = [cache_key(self.key, t) for t in texts]
        unique = list(dict.fromkeys(keys))
        found = self.cache.get_many(unique)
        miss_keys = [k for k in unique if k not in found]
        self.cache.hits += len(unique) - len(miss_keys)
        self.cache.misses += len(miss_keys)
        if miss_keys:
            first_text = {}
            for k, t in zip(keys, texts, strict=True):
                first_text.setdefault(k, t)
            new = self._encode([first_text[k] for k in miss_keys])
            self.cache.put_many(dict(zip(miss_keys, new, strict=True)))
            found.update({k: v.astype(np.float16) for k, v in zip(miss_keys, new, strict=True)})
        return np.stack([found[k] for k in keys]).astype(np.float32)

    def corpus_matrix(self, corpus: Corpus) -> np.ndarray:
        return self.encode_docs([c.text for c in corpus.chunks])


def faiss_scores(doc_matrix: np.ndarray, query_vec: np.ndarray) -> np.ndarray:
    """FR-R5: exact inner-product search over all chunks; returns scores aligned to rows."""
    index = faiss.IndexFlatIP(doc_matrix.shape[1])
    index.add(np.ascontiguousarray(doc_matrix, dtype=np.float32))
    n = doc_matrix.shape[0]
    dist, ids = index.search(np.ascontiguousarray(query_vec.reshape(1, -1), dtype=np.float32), n)
    scores = np.zeros(n, dtype=np.float32)
    scores[ids[0]] = dist[0]
    return scores


def report_cache(encoder: DenseEncoder) -> None:
    console.print(f"embedding cache hit rate: {encoder.cache.hit_rate:.1%} "
                  f"(hits={encoder.cache.hits}, misses={encoder.cache.misses})")
