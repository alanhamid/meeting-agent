"""Offline BM25 with light stemming plus phrase and title boosts.

Quality is measured by scripts/eval_retrieval.py. The clearance gate does not depend on any of this.
"""
from __future__ import annotations

import itertools
import math
import re
from collections import Counter
from dataclasses import dataclass

from meeting_agent.classification import Level
from meeting_agent.kb.loader import Chunk

_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_STOP = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "of", "on", "or", "our", "so", "than", "that", "the", "their", "then", "there", "these", "they", "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your", "about", "any", "also", "actually", "really"]
)
_SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s")


def stem(w: str) -> str:
    if len(w) <= 4 or not w.isalpha():
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[: -len(suf)]
            return base + "y" if suf in ("ies", "ied") else base
    return w


def tokens(text: str, do_stem: bool = True) -> list[str]:
    out = []
    for t in _WORD.findall(text.lower()):
        t = t.strip(".-_")
        if t and t not in _STOP:
            out.append(stem(t) if do_stem else t)
    return out


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    matched: int


class Index:
    def __init__(
        self,
        chunks: list[Chunk],
        k1: float = 1.4,
        b: float = 0.75,
        title_boost: float = 6.0,
        phrase_boost: float = 1.0,
    ) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.title_boost, self.phrase_boost = title_boost, phrase_boost
        self._body = [tokens(c.text) for c in chunks]
        self._title = [set(tokens(c.title)) for c in chunks]
        self._tf = [Counter(b_) for b_ in self._body]
        self._len = [len(b_) or 1 for b_ in self._body]
        self._avg = (sum(self._len) / len(chunks)) if chunks else 1.0
        self._text = [" ".join(b_) for b_ in self._body]
        df: Counter[str] = Counter()
        for i, tf in enumerate(self._tf):
            df.update(set(tf) | self._title[i])
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 5, levels: set[Level] | None = None) -> list[Hit]:
        base = list(dict.fromkeys(tokens(query)))
        if not base:
            return []
        need = 1 if len(base) <= 2 else 2
        bigrams = [f"{a} {b_}" for a, b_ in itertools.pairwise(base)]
        hits: list[Hit] = []
        for i, tf in enumerate(self._tf):
            if levels is not None and self.chunks[i].level not in levels:
                continue
            title = self._title[i]
            matched = [t for t in base if t in tf or t in title]
            if len(matched) < need:
                continue
            score = 0.0
            for t in base:
                f = tf.get(t, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self._len[i] / self._avg)
                    score += self._idf[t] * f * (self.k1 + 1) / denom
                if t in title:
                    score += self._idf.get(t, 0.0) * self.title_boost / 3
            for bg in bigrams:
                if bg in self._text[i]:
                    score += self.phrase_boost * sum(self._idf.get(t, 0.0) for t in bg.split()) / 2
            hits.append(Hit(self.chunks[i], score, len(matched)))
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:k]
