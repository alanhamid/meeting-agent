# meeting-agent

A private copilot for live meetings. Ask a question (typed or push-to-talk) and get a short talk track
with sources, warnings from your "do not say" list, and a follow-up log, while a deterministic gate keeps
anything the room is not cleared for away from the model.

## How the gate works
| Tag | Meaning |
|---|---|
| `public` | Safe for anyone |
| `nda` | Only if EVERY participant has a signed, unexpired NDA covering the topic |
| `internal` | Never shared with anyone; shown only to you as a private note |

Before a meeting starts, the dashboard requires each participant's name, organisation, role and an explicit
NDA answer (signed needs a date and a document reference). If the question needs material the room is not
cleared for, the reply is the fixed script: *"To answer that we need a signed NDA in place. Once it is signed,
I will follow up..."* and a follow-up is logged against the participants who block it.

## Model and notes (step 2)
- Set `MEETING_AGENT_MODEL=azure` with `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_KEY`
  (optional `AZURE_OPENAI_API_VERSION`). Default is the offline quoting answerer. Only cleared passages are sent;
  if the model call fails the answer degrades to a plain quote and is flagged.
- After a meeting, paste or upload a Zoom/Teams transcript (.txt, .vtt, .srt) and generate notes: summary, decisions,
  action items, questions, objections, open follow-ups, a snapshot of each participant's NDA status, and a list of
  speakers who were not on your participant list. Notes are keyword-based and stay local by default. Only with
  `MEETING_AGENT_NOTES_MODEL=on` is the TRANSCRIPT SENT to the model (other people's words, possibly confidential);
  leave it off until the model is in a region you are allowed to use.
- The Azure call has been tested only against a mock server, never a live endpoint.

## Retrieval
BM25 over tagged chunks (table rows are separate chunks), light stemming, title and phrase boosts. Measured with
`scripts/eval_retrieval.py` (hit@1 0.74, hit@3 0.91 on 43 self-written questions; see docs/test-log.md).

## Status (step 1)
Built: knowledge loader with section-level tags, BM25 retrieval, clearance gate, pre-meeting dashboard,
ask by typing or browser push-to-talk, policy warnings, release-once, follow-up log, append-only audit events.
Not built: embeddings, cloud speech-to-text, live meeting capture (silent Zoom/Teams listener), LangSmith tracing,
Railway deployment.

## Known limits
- Answer quality with the offline answerer is quotation of the best passage, and keyword retrieval can pick the
  wrong passage. The gate does not depend on this, but usefulness does; a model and better retrieval come next.
- The gate trusts the NDA status you enter. It cannot verify an NDA exists.
- Anything shown on your screen (including withheld titles and private notes) is for you only.
