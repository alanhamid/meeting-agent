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
