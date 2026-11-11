"""Code-aware tokenizer for BM25.

Concept: BM25 is a bag-of-words model, so its quality is decided by what counts
as a "word". Issues say "the filter method of query sets" while code says
`QuerySet.filter` or `query_set_filter`. Splitting identifiers into their
camelCase / snake_case parts lets those meet in the middle, and also keeping
the full identifier rewards exact mentions (an issue naming `HTTPResponseError`
matches that symbol more strongly than one merely containing "error").
Stopwords (English + Python keywords) and 1-character tokens carry no signal.
"""

from __future__ import annotations

import keyword
import re

_IDENT = re.compile(r"[A-Za-z0-9_]+")
# Split "HTTPResponseError" -> HTTP, Response, Error ; "parseJSON2Dict" -> parse, JSON2, Dict
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

ENGLISH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has", "have",
    "he", "i", "if", "in", "into", "is", "it", "its", "of", "on", "or", "our", "she", "so",
    "such", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "will", "with",
    "would", "you", "your", "can", "could", "should", "do", "does", "did", "not", "no",
    "me", "my", "am", "been", "being", "also", "than", "too", "very", "just", "any", "all",
    "some", "here", "how", "why", "about", "after", "before", "because", "only",
    "other", "more", "most", "same", "each", "both", "up", "down", "out", "over", "under",
}
PY_KEYWORDS = {k.lower() for k in keyword.kwlist} | {"self", "cls"}
STOPWORDS = ENGLISH_STOPWORDS | PY_KEYWORDS


def split_identifier(ident: str) -> list[str]:
    """'snake_case_name' -> [snake, case, name]; 'QuerySet' -> [Query, Set]."""
    parts = []
    for piece in ident.split("_"):
        if piece:
            parts.extend(_CAMEL.findall(piece))
    return parts


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for ident in _IDENT.findall(text):
        full = ident.strip("_").lower()
        parts = [p.lower() for p in split_identifier(ident)]
        candidates = parts if len(parts) == 1 and parts[0] == full else [full, *parts]
        for tok in candidates:
            if len(tok) > 1 and tok not in STOPWORDS:
                tokens.append(tok)
    return tokens
