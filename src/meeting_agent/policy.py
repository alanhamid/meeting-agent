"""Policy as data: scripts and do-not-say rules live in config/policy.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from meeting_agent.models import Stakeholder, Warning_


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    message: str
    stakeholders: frozenset[str]  # empty = applies to everyone


@dataclass(frozen=True)
class Policy:
    scripts: dict[str, str]
    rules: list[Rule]

    def check(self, text: str, stakeholder: Stakeholder) -> list[Warning_]:
        out = []
        for r in self.rules:
            if r.stakeholders and stakeholder.value not in r.stakeholders:
                continue
            if r.pattern.search(text):
                out.append(Warning_(rule_id=r.id, message=r.message))
        return out


def load_policy(path: Path) -> Policy:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    scripts = raw["scripts"]
    for key in ("nda", "no_answer", "avoid_topic"):
        if not scripts.get(key, "").strip():
            raise ValueError(f"policy script '{key}' is required")
    rules = [
        Rule(
            id=r["id"],
            pattern=re.compile(r["pattern"], re.IGNORECASE),
            message=r["message"],
            stakeholders=frozenset(r.get("stakeholders", [])),
        )
        for r in raw.get("rules", [])
    ]
    return Policy(scripts=scripts, rules=rules)
