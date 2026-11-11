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

## 2026-11-11 (round 3: retrieval quality)
**What:** retrieval ranking on the real knowledge pack.
**How:** `scripts/eval_retrieval.py` over `evals/retrieval.yaml` (43 questions I wrote, each with the document that should rank;
ranking measured over public+nda chunks only, as in the live flow). Ablations of title boost, phrase boost, aliases, row chunking.
**Result:** baseline (BM25, 257 chunks, all levels) hit@1 0.72 / hit@3 0.88 / MRR 0.79 (not comparable: internal chunks
counted). Final (table rows as separate chunks, light stemming, title boost 6, bigram phrase boost, internal searched
separately, 503 chunks): hit@1 0.744 / hit@3 0.907 / MRR 0.822. Ablation on the same set: plain 0.465 / 0.791 / 0.636;
+title 0.651 / 0.930 / 0.775; +phrase 0.698 / 0.884 / 0.787. Alias expansion lowered hit@3 (0.884 -> 0.837) so it was removed.
Real-pack spot checks: "Who is the customer?" and the audit-log question now return the right passages.
75 tests pass.
**Findings:** the gain is modest and the eval is small, self-written and tuned on the same 43 questions (overfitting risk);
several "misses" are label ambiguity (e.g. controls-to-regulators exists in two documents). Keyword retrieval stays a
ceiling; embeddings or a reranker would be the next step. Conservative rule unchanged: when the best match is NDA-level
and the room is not cleared, the script is used even if a weaker public passage exists (e.g. the audit-log question).
**Not tested:** embeddings, rerankers, questions phrased by other people, spoken (mis-transcribed) questions.

## 2026-11-11 (round 4: notes stay local)
**What:** transcripts go to a model only with `MEETING_AGENT_NOTES_MODEL=on` (default off), because the available Azure
OpenAI resource is in a US region.
**How:** `pytest` (76 tests); new test proves that with an answer model configured and the flag unset, no request is made
for notes.
**Result:** 76 pass, ruff clean.
**Not tested:** a live Azure OpenAI call (endpoint and key not yet provided).
