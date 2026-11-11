"""Load the knowledge pack into tagged chunks.

Fail closed: any file not covered by the manifest is INTERNAL, and a section override can
only be matched by an exact heading.
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from meeting_agent.classification import Confidence, Level, Topic

TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt"}
MAX_CHUNK_CHARS = 1400
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _is_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and not _SEP.match(s)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc: str
    title: str
    text: str
    level: Level
    topic: Topic
    confidence: Confidence


@dataclass(frozen=True)
class _Entry:
    pattern: str
    level: Level
    topic: Topic
    confidence: Confidence
    sections: dict[str, Level]


def load_manifest(path: Path) -> list[_Entry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[_Entry] = []
    for e in raw.get("entries", []):
        out.append(
            _Entry(
                pattern=e["path"],
                level=Level(e["level"]),
                topic=Topic(e.get("topic", "general")),
                confidence=Confidence(e.get("confidence", "unreviewed")),
                sections={
                    s["heading"].strip().lower(): Level(s["level"])
                    for s in e.get("sections", [])
                },
            )
        )
    return out


def _match(entries: list[_Entry], rel: str) -> _Entry | None:
    for e in entries:
        if fnmatch.fnmatch(rel, e.pattern):
            return e
    return None


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n|\n(?=[-|*] )", text):
        if cur and len(cur) + len(para) > MAX_CHUNK_CHARS:
            parts.append(cur)
            cur = ""
        while len(para) > MAX_CHUNK_CHARS:  # one huge paragraph: hard split
            parts.append(para[:MAX_CHUNK_CHARS])
            para = para[MAX_CHUNK_CHARS:]
        cur = f"{cur}\n{para}".strip() if cur else para
    if cur:
        parts.append(cur)
    return parts


def _chunk_markdown(rel: str, text: str, entry: _Entry | None, default: Level) -> list[Chunk]:
    base = entry.level if entry else default
    topic = entry.topic if entry else Topic.GENERAL
    conf = entry.confidence if entry else Confidence.UNREVIEWED
    overrides = entry.sections if entry else {}

    sections: list[tuple[str, Level, list[str]]] = []
    stack: list[tuple[int, str]] = []
    override_depth: int | None = None
    override_level: Level | None = None
    cur_lines: list[str] = []
    cur_title, cur_level = rel, base

    def flush() -> None:
        if any(line.strip() for line in cur_lines):
            sections.append((cur_title, cur_level, list(cur_lines)))

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            depth, heading = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, heading))
            if override_depth is not None and depth <= override_depth:
                override_depth, override_level = None, None
            key = heading.lower()
            if key in overrides:
                override_depth, override_level = depth, overrides[key]
            cur_title = f"{rel} > " + " > ".join(h for _, h in stack)
            cur_level = override_level or base
            cur_lines = [line]
        else:
            cur_lines.append(line)
    flush()

    chunks: list[Chunk] = []
    for n, (title, level, lines) in enumerate(sections):
        rows = [ln for ln in lines if _is_row(ln)]
        if len(rows) >= 3:  # table: one chunk per row so each Q&A answers on its own
            head = "\n".join(ln for ln in lines if not _is_row(ln) and ln.strip() and not _SEP.match(ln))
            for k, row in enumerate(rows):
                label = row.strip("| ").split("|")[0].strip(" *")[:60]
                chunks.append(Chunk(f"{rel}#{n}.{k}", rel, f"{title} > {label}", row.strip(), level, topic, conf))
            if head.strip():
                chunks.append(Chunk(f"{rel}#{n}.h", rel, title, head, level, topic, conf))
            continue
        for k, piece in enumerate(_split_long("\n".join(lines).strip())):
            chunks.append(Chunk(f"{rel}#{n}.{k}", rel, title, piece, level, topic, conf))
    return chunks


def _chunk_plain(rel: str, text: str, entry: _Entry | None, default: Level) -> list[Chunk]:
    level = entry.level if entry else default
    topic = entry.topic if entry else Topic.GENERAL
    conf = entry.confidence if entry else Confidence.UNREVIEWED
    return [
        Chunk(f"{rel}#0.{k}", rel, rel, piece, level, topic, conf)
        for k, piece in enumerate(_split_long(text.strip()))
        if piece.strip()
    ]


def load_kb(root: Path, manifest: Path | None = None) -> list[Chunk]:
    manifest = manifest or root / "manifest.yaml"
    entries = load_manifest(manifest) if manifest.exists() else []
    chunks: list[Chunk] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES or f == manifest:
            continue
        rel = f.relative_to(root).as_posix()
        text = f.read_text(encoding="utf-8", errors="replace")
        entry = _match(entries, rel)
        fn = _chunk_markdown if f.suffix.lower() == ".md" else _chunk_plain
        chunks.extend(fn(rel, text, entry, Level.INTERNAL))
    return chunks
