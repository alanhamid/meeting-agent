"""Copy the manifest-listed AAPA files into ./kb (gitignored) and print the level counts.

Usage: python scripts/sync_kb.py [--source ../aapa-v0.1] [--dest kb]
Only files matched by kb.manifest.yaml are copied. Nothing confidential is committed.
"""
from __future__ import annotations

import argparse
import fnmatch
import shutil
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="/home/user/aapa-v0.1")
    ap.add_argument("--dest", default=str(ROOT / "kb"))
    a = ap.parse_args()
    src, dest = Path(a.source), Path(a.dest)
    manifest = ROOT / "kb.manifest.yaml"
    patterns = [e["path"] for e in yaml.safe_load(manifest.read_text())["entries"]]

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    copied = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or ".git" in f.parts or "node_modules" in f.parts:
            continue
        rel = f.relative_to(src).as_posix()
        if any(fnmatch.fnmatch(rel, p) for p in patterns):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / rel)
            copied += 1
    shutil.copy2(manifest, dest / "manifest.yaml")

    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from meeting_agent.kb.loader import load_kb

    chunks = load_kb(dest)
    levels = Counter(c.level.value for c in chunks)
    print(f"copied {copied} files -> {dest}; chunks by level: {dict(levels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
