# Test log (append-only, one section per date)

## 2026-11-11
**What:** step 1 - loader, gate, ask pipeline, API, dashboard UI.
**How:** `pytest` (48 offline tests); real knowledge pack synced from the AAPA repo and queried through the API
with an unsigned and a signed participant; Chromium (Playwright) run of the dashboard.
**Result:** 48 tests pass, ruff clean. Real pack: 257 chunks (internal 73, public 66, nda 118); both "Do not say"
sections tagged internal. Unsigned meeting: NDA questions got the script, no NDA text reached the model; signed
meeting: same questions answered. Browser: form refuses start without an NDA answer; banner shows PUBLIC ONLY;
withheld answer shows a Release-once button; no console errors.
**Findings:** extractive answers are poor on some questions (e.g. an audit-log question returned the moat Q&A
because that passage ranked first). Retrieval/answer quality needs a model and embeddings. The `customers` warning
fires on any mention of the word, including harmless ones (warn-only, accepted).
**Not tested:** any live model, voice recognition accuracy, Zoom/Teams use, Railway/LangSmith, load, mobile layout.

## 2026-11-11 (round 2)
**What:** Azure OpenAI gateway, degraded mode, transcript parsing (Teams/Zoom VTT, Zoom txt, SRT, plain), notes, UI.
**How:** `pytest` (70 offline tests, httpx mock transport for the model), Chromium run of dashboard -> transcript -> notes -> end meeting.
**Result:** 70 pass, ruff clean. Verified: model receives only cleared passages; model failure degrades to a quote and is
flagged; invalid model JSON falls back to heuristic notes; transcript is fenced with an injection guard; transcripts over
60k characters never go to the model; transcripts are immutable; speakers not on the participant list are flagged.
Browser: notes render, ended meetings hide the ask box (found and fixed a CSS bug where `[hidden]` was overridden).
**Findings:** the heuristic notes are weak (keyword rules; the presenter shows as "not on the list"). Meeting presenter
name is not stored, so the unlisted-speakers check includes you.
**Not tested:** any live Azure OpenAI call, note quality with a real model, real Zoom/Teams exports (formats are from
my knowledge of them, not from your files), long transcripts, voice.
