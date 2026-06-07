# HANDOFF.md — start here

The single entry point for the dev team. Read this, then `AGENTS.md`, then take a track.

## v1 scope (locked)
Build the live ontology-first slice through P3 (deep questions answered from the ontology, beating a raw baseline) **plus chart-image reading** (P4, after the green slice, no eval depends on it). **Deferred, designed-not-built:** the self-correcting feedback loop, the reader/executor runtime split (v1 is read-only Q&A; the untrusted-content gate + egress redaction still ship), confidence calibration, and a larger eval set. Details in SOLUTION "What I didn't tackle."

## What this is (60 seconds)
The **House Harness Engine**: ingests a messy company document corpus and emits a **House Harness** — `<COMPANY>.md` plus a queryable, sourced ontology — that an agent operates the company through. Deep cross-cutting questions (staleness, contradiction, aliases, hierarchy, attribution) are answered from a **resolved ontology**, not a search index. Built on **LangChain 1.0** (`create_agent`, `init_chat_model`, LangGraph) with **LangSmith** tracing. Task brief + grading: `BUILD_PLAN_HELIXPAY.md` §0–§2; submission narrative: `SOLUTION.md`.

## Current state (be honest)
**Scaffold + plan, ~0% model logic.** What's real: the typed contract (`schema.py`, 31 types), deterministic rule tables (`ontology.RELIABILITY`, `profiler.plan_pipeline`, `health.ACTIONS`), the controlled vocab (`pipeline/attributes.py`), the verified alias ledger (`pipeline/aliases.py`), the frozen mock envelope (`synthesis/_mock.py`), and two test fixtures. Everything model-touching raises `NotImplementedError` by design. **Phase 0 (corpus verification) is PASSED** (`PHASE_0_CORPUS_VALIDATION.md`). The build is Phases 1–5.

## Run it (from a fresh clone)
```bash
cp .env.example .env          # add ANTHROPIC_API_KEY, HOUSE_HARNESS_API_TOKEN, LANGSMITH_API_KEY
./install.sh                  # docker compose up (app + SQLite; LangSmith via env), ingest data/, health-check
make eval                     # uplift gate: with_harness (ontology-first) vs without_harness (raw baseline)
```
Or hand the repo to Claude Code: *"Clone this, read CLAUDE.md and AGENTS.md, run ./install.sh, fill secrets from .env.example, wait for /health, then run the demo queries in SOLUTION.md."*

## How we work (non-negotiable)
The loop, every session (`AGENTS.md` → "Development flow"): **read `PROGRESS.md` → take the next item in `PLAN.md` → implement → run the matching block in `VERIFY.md` → append to `PROGRESS.md` → check it off.** Never check an item without a green VERIFY run. Hard boundaries (provider isolation, untrusted-content, typed-at-every-boundary, privilege split, grounded≠correct) are in `AGENTS.md` and are not optional. `VALIDATION.md` is the go/no-go gate before submission.

## Build order (depth-first, stop-lined — full detail in `PLAN.md`)
Each stop-line is a place you could ship from. **Don't go breadth-first.**
- **P1 Skeleton live (~45m)** — `install.sh`→compose→Fly, answering from `synthesis/_mock.answer()`. *Stop-line: a live URL with green `/health`.* De-risks "live in production" at hour 1.
- **P2 Ontology spine, no LLM (~1h)** — `ontology.upsert/resolve/assertion_id/query`, pure, unit-tested vs `tests/fixtures/assertions_resolve.json`. *Stop-line: resolve() separates "both true" from real conflict + supersession; idempotent re-ingest.*
- **P3 First vertical slice (~1.5h)** — two traps (`confluence-launch`, `nps-segmented`) end-to-end: extract → upsert/resolve → **`ontology.query`** → envelope → `/ask`, behind the mock on the live URL. *Stop-line: those 2 evals green live, beating the raw baseline (`delta.pass_rate > 0`). **Defensible submission here.***
- **P4 Widen (~1h)** — remaining loaders/traps, abstention+escalation, harness extraction → `<COMPANY>.md`, health, reader/executor split, vision (provisional). Each addition individually droppable.
- **P5 Harden + write-up (~45m)** — redaction, caps, LangSmith on, calibration, `make validate`, finish `SOLUTION.md`. The write-up is graded; protect it.

## Who builds what — parallel tracks (all start from the frozen `schema.py`)
The frozen contract + the mock envelope are what let these run concurrently and converge at P3.

| Track | Owns | Depends on | Starts against | First task |
|---|---|---|---|---|
| **A — Ontology spine** | `pipeline/ontology.py` (`upsert`/`resolve`/`assertion_id`/`query`) | nothing (pure) | `tests/fixtures/assertions_resolve.json` | make `resolve()` green on the fixture (P2) |
| **B — Ingest** | `ingest/loaders.py`, `ingest/gate.py` → `Artifact`s | `schema.Artifact` | real `data/` | md/pdf/html/chat/email loaders, per-file isolation |
| **C — Infra/serve/deploy** | `install.sh`, `Dockerfile`, `fly.toml`, `serve/app.py`, `guards/redact.py`, `obs/`, CI | `schema`, `synthesis/_mock` | `_mock.answer()` | **P1**: live `/health` on Fly against the mock |
| **D — Extraction** | `pipeline/harness.py` + the extraction prompt | B's `Artifact`, `attributes.py`, `aliases.py` | `tests/fixtures/extraction_golden.json` | get the prompt green on the golden fixture |
| **E — Synthesis** | `synthesis/envelope.py`, `synthesis/verify.py` | A's `query()` output shape | synthetic resolved assertions + `_mock` | build envelope from an assertion slice (ontology-first) |
| **F — Evals** | `evals/*.json` + the runner wiring | (gated on Phase 0 ✓) | C's mock | wire `with_harness` (ontology-first) vs `without_harness` (raw) |

**Integration point = P3:** A's `query()` ⨝ D's assertions ⨝ E's envelope, served through C's endpoint, gated by F's uplift. **A (ontology) is the critical path** — it's what P3 integrates around, so visible progress on B/C/D can mask a lagging A and leave nothing to integrate; keep A staffed first. **Solo order:** C(skeleton) → A → D → E → F-wire. **With ≥2 people:** A and C run in true parallel from minute 0; D's prompt work starts against the golden fixture on day one.

## Gotchas (will bite you)
- **Deploy-first is a GATE, not a suggestion.** Build the boring thing — the live `/health` skeleton (`house-harness serve`) — and `fly deploy` it BEFORE any ontology work. Phase 1 is a hard stop-line: no Phase 2+ until a live URL returns green `/health` and CI `deploy-smoke` is green. The agent's pull is to build the fun part first; that's exactly how the deploy tax lands at hour 5.
- **Never ship the mock.** The Phase-1 skeleton answers from `_mock` via `serve.answer()` (`HOUSE_HARNESS_SERVE_MODE=mock`). It self-identifies (`mode=mock` on every envelope, `/health` echoes it) and **fails `make validate`**. `live` is the default and raises if the pipeline isn't wired — it will never silently serve canned data. Phase 3 flips to live.
- **Ontology-first is the query default**, not whole-corpus. The call graph is encoded in `synthesis/respond.py` (`answer → resolve_question → ontology.query → claims_from_assertions → build_envelope`); raw `WholeCorpus` is reached only inside `_fallback`. Tripwires: graded answers must be `answer_path=ontology` with every claim carrying an `assertion_id` — `make validate` fails otherwise. Don't wire the RAG-reflex (retrieve→stuff→generate) path; it reintroduces the trap failures (`BUILD_PLAN` §4.5).
- **The uplift number can flatter or thrash.** `without_harness` must be a *fair* baseline (same model + raw corpus; evals `baseline_spec`) — a strawman makes the harness "win" trivially. If `delta.pass_rate ≤ 0`, check `uplift-canary` before touching the harness: it must split (baseline fail, harness pass); if it doesn't, the rig is mis-wired (shared context source or harness off-path), not the harness.
- **Confidence = ontology coverage, not retrieval similarity.** Grounded ≠ correct; a citation proves a claim wasn't invented, not that it's true.
- **Extraction is the highest-variance step, and it fails *silently*.** Hard gate: `attributes.nonconformant(emitted) == []` — an off-namespace synonym never groups in `resolve()`, so no dissent fires and the traps "pass" by returning one value. Use `new_attribute:<slug>` for genuine out-of-vocab facts, never a guessed synonym. Treat the prompt as the highest-iteration artifact; regression-test against `extraction_golden.json` every change.
- **Anti-aliases are load-bearing.** Over-merge is silent corruption (`aliases.py`: 9 anti-alias pairs + 3 non-person identities). Precision ≥0.95 is graded.
- **Entailment is OFFLINE.** Runtime is cite-or-abstain; `verify.py` runs in the eval harness, `Claim.verified` is `None` at runtime.
- **Keep deterministic things deterministic.** Profiler/planner/health/resolve are rule tables, never LLM oracles.

## Doc index
`README.md` what+status+layout · `AGENTS.md` norms+loop (canonical) · `CLAUDE.md` pointer · `PLAN.md` phased build+DoD · `PROGRESS.md` running log · `VERIFY.md` per-stage commands · `VALIDATION.md` acceptance gate · `PHASE_0_CORPUS_VALIDATION.md` corpus verdicts (passed) · `BUILD_PLAN_HELIXPAY.md` full design rationale · `SOLUTION.md` submission narrative · `SUBMISSION.md` packaging playbook.
