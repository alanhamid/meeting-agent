"""Small offline BM25 index. Retrieval quality can be upgraded later; the gate does not depend on it."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from meeting_agent.kb.loader import Chunk

_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_STOP = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "is", "it", "its", "of", "on", "or", "our", "so", "than", "that", "the", "their", "then", "there", "these", "they", "this", "to", "was", "we", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your"]
)


def tokens(text: str) -> list[str]:
    return [t.strip(".-_") for t in _WORD.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    matched: int  # distinct query terms found in the chunk


class Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self._tf = [Counter(tokens(f"{c.title} {c.title} {c.text}")) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(chunks)) if chunks else 1.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q = list(dict.fromkeys(tokens(query)))
        if not q:
            return []
        need = 1 if len(q) <= 2 else 2
        hits: list[Hit] = []
        for i, tf in enumerate(self._tf):
            matched = [t for t in q if t in tf]
            if len(matched) < need:
                continue
            score = 0.0
            for t in matched:
                f = tf[t]
                denom = f + self.k1 * (1 - self.b + self.b * self._len[i] / self._avg)
                score += self._idf[t] * f * (self.k1 + 1) / denom
            hits.append(Hit(self.chunks[i], score, len(matched)))
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:k]
