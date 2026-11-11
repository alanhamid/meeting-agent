"""Parse pasted/uploaded transcripts (Zoom .txt/.vtt, Teams .vtt, SRT, 'Name: text') into utterances."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 300_000

_TS = re.compile(r"^\s*(?:\d+\s*$)?")
_CUE = re.compile(
    r"^(?:(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*(?:(\d{1,2}:)?\d{2}:\d{2}[.,]\d{3})"
)
_VOICE = re.compile(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$")
_ZOOM_HDR = re.compile(r"^\[(.+?)\]\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$")
_TIME_NAME = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s+([^:]{1,60}):\s*(.*)$")
_NAME_LINE = re.compile(r"^([A-Z][^:\n]{0,50}):\s+(\S.*)$")
_TAG = re.compile(r"</?[a-z][^>]*>")


@dataclass
class Utterance:
    speaker: str
    text: str
    start: str | None = None


def _merge(items: list[Utterance]) -> list[Utterance]:
    out: list[Utterance] = []
    for u in items:
        u.text = " ".join(u.text.split())
        if not u.text:
            continue
        if out and out[-1].speaker == u.speaker:
            out[-1].text += " " + u.text
        else:
            out.append(u)
    return out


def _cue_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
    blocks, cur_time, cur = [], None, []
    for ln in lines:
        m = _CUE.match(ln.strip())
        if m:
            if cur_time is not None:
                blocks.append((cur_time, cur))
            cur_time, cur = ln.strip().split("-->")[0].strip(), []
        elif cur_time is not None:
            if ln.strip() == "":
                blocks.append((cur_time, cur))
                cur_time, cur = None, []
            else:
                cur.append(ln.strip())
    if cur_time is not None:
        blocks.append((cur_time, cur))
    return blocks


def parse_transcript(text: str) -> list[Utterance]:
    text = text.replace("\r\n", "\n").replace("﻿", "")
    lines = text.split("\n")

    if any(_CUE.match(ln.strip()) for ln in lines):  # WebVTT (Teams, Zoom) or SRT
        out = []
        for start, body in _cue_blocks(lines):
            speaker, parts = "Unknown", []
            for b in body:
                v = _VOICE.match(b)
                if v:
                    speaker, b = v.group(1).strip(), v.group(2)
                else:
                    n = _NAME_LINE.match(_TAG.sub("", b))
                    if n and not parts and speaker == "Unknown":
                        speaker, b = n.group(1).strip(), n.group(2)
                parts.append(_TAG.sub("", b))
            out.append(Utterance(speaker, " ".join(parts), start))
        return _merge(out)

    if any(_ZOOM_HDR.match(ln.strip()) for ln in lines):  # Zoom "[Name] 10:01:02" then text
        out, cur = [], None
        for ln in lines:
            h = _ZOOM_HDR.match(ln.strip())
            if h:
                cur = Utterance(h.group(1).strip(), "", h.group(2))
                out.append(cur)
            elif cur is not None and ln.strip():
                cur.text += " " + ln.strip()
        return _merge(out)

    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        t = _TIME_NAME.match(s)
        if t:
            out.append(Utterance(t.group(2).strip(), t.group(3), t.group(1)))
            continue
        n = _NAME_LINE.match(s)
        if n:
            out.append(Utterance(n.group(1).strip(), n.group(2)))
        elif out:
            out[-1].text += " " + s  # continuation line
        else:
            out.append(Utterance("Unknown", s))
    return _merge(out)
