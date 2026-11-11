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

## Status (step 1)
Built: knowledge loader with section-level tags, BM25 retrieval, clearance gate, pre-meeting dashboard,
ask by typing or browser push-to-talk, policy warnings, release-once, follow-up log, append-only audit events.
Not built: a live model (offline extractive answerer is the default), embeddings, cloud speech-to-text,
transcript import and notes, live meeting capture, LangSmith tracing, Railway deployment.

## Known limits
- Answer quality with the offline answerer is quotation of the best passage, and keyword retrieval can pick the
  wrong passage. The gate does not depend on this, but usefulness does; a model and better retrieval come next.
- The gate trusts the NDA status you enter. It cannot verify an NDA exists.
- Anything shown on your screen (including withheld titles and private notes) is for you only.
