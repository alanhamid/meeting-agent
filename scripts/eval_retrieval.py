"""Retrieval eval: hit@1, hit@3, MRR over evals/retrieval.yaml against ./kb. Run after sync_kb.py."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from meeting_agent.classification import Level
from meeting_agent.kb.loader import load_kb
from meeting_agent.kb.search import Index


def evaluate(index: Index, cases: list[dict], k: int = 5, verbose: bool = False) -> dict:
    h1 = h3 = 0
    mrr = 0.0
    misses = []
    for c in cases:
        hits = index.search(c["q"], k=k, levels={Level.PUBLIC, Level.NDA})
        rank = None
        for i, h in enumerate(hits, 1):
            if h.chunk.doc == c["doc"] and (not c.get("sec") or c["sec"].lower() in h.chunk.title.lower()):
                rank = i
                break
        if rank == 1:
            h1 += 1
        if rank is not None and rank <= 3:
            h3 += 1
        mrr += 1 / rank if rank else 0
        if rank is None or rank > 1:
            misses.append((c["q"], rank, [f"{h.chunk.doc}|{h.chunk.title.split(' > ')[-1][:30]}" for h in hits[:3]]))
    n = len(cases)
    out = {"n": n, "hit@1": h1 / n, "hit@3": h3 / n, "mrr": mrr / n}
    if verbose:
        for q, r, top in misses:
            print(f"  rank={r} {q}\n      got {top}")
    return out


def main() -> int:
    chunks = load_kb(ROOT / "kb")
    cases = yaml.safe_load((ROOT / "evals" / "retrieval.yaml").read_text())["cases"]
    r = evaluate(Index(chunks), cases, verbose="-v" in sys.argv)
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}, f"chunks={len(chunks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
