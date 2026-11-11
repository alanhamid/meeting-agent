# CLAUDE.md

Private meeting copilot for the AAPA founder: grounded answers during Zoom/Teams/in-person meetings,
gated by per-meeting NDA clearance, plus follow-up capture and (later) meeting notes.

## Rules
- The gate is code, not a prompt. Retrieval is tagged public / nda / internal and filtered BEFORE any model call.
  A model must never receive text the meeting is not cleared for.
- Fail closed: untagged files are internal; a participant with no explicit NDA answer is not cleared;
  a late joiner is "not signed" until the presenter says otherwise; expired NDAs do not cover.
- INTERNAL is never spoken to anyone, with or without an NDA, and a release cannot lift it.
- The weakest participant sets the level. NDA scope (all/technical/commercial) is checked per topic.
- Releases are explicit, logged with a reason, single-use, NDA-level only.
- Policy (spoken scripts, do-not-say rules) is data in `config/policy.yaml`; rules only warn the presenter.
- Do not invent facts. The model answers only from cleared passages; otherwise it abstains.
- Confidential content (`kb/`) is gitignored and synced by `scripts/sync_kb.py`. Keep this repo private.
- Events are append-only. Tests run offline (no network, GPU or API keys).
- Record every round of testing in `docs/test-log.md` (append-only, one section per date).
- Ask the user before writing code or changing the repo. Never push to main without explicit approval.

## Commands
```bash
uv venv .venv && uv pip install -e '.[dev]'
.venv/bin/pytest -q && .venv/bin/ruff check .
.venv/bin/python scripts/sync_kb.py --source ../aapa-v0.1     # fills ./kb (gitignored)
.venv/bin/uvicorn meeting_agent.api:app_factory --factory --port 8080
```
Production needs `MEETING_AGENT_ENV=production` and `MEETING_AGENT_TOKEN` (the app refuses to start without it).
