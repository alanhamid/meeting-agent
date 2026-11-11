"""Model gateway. The model receives only passages the gate has already cleared."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from meeting_agent.models import Meeting

TONE = {
    "investor": "Lead with the problem, the honest stage of the work and the risks. No hype.",
    "microsoft": "Be precise about architecture and Azure services; state limits plainly.",
    "strategic_enterprise": "Focus on the controlled pilot: scope, controls, what is simulated.",
    "credit_union_or_bank": "Focus on controls, auditability and the approval flow.",
    "technical_ally": "Be technical and exact; cite the source.",
    "other": "Be brief and factual.",
}


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    title: str
    text: str


class Gateway(Protocol):
    def answer(self, system: str, question: str, passages: list[Passage]) -> str: ...


def build_system(meeting: Meeting) -> str:
    return (
        "You are a private talk-track assistant for a founder in a live meeting. "
        "Answer in at most three short sentences, using ONLY the passages provided. "
        "If the passages do not answer the question, say you do not have a confirmed answer. "
        "Never invent numbers, customers, dates or claims. "
        f"Audience: {meeting.stakeholder.value}. {TONE[meeting.stakeholder.value]}"
    )


_MD = re.compile(r"[#*`|>]+|^\s*[-+]\s+", re.MULTILINE)


class ExtractiveGateway:
    """Offline default: quotes the best passage. No model, no network, so tests run anywhere."""

    def answer(self, system: str, question: str, passages: list[Passage]) -> str:
        if not passages:
            return ""
        body = _MD.sub(" ", passages[0].text)
        body = re.sub(r"\s+", " ", body).strip()
        sentences = re.split(r"(?<=[.!?])\s+", body)
        return " ".join(sentences[:3]).strip()
