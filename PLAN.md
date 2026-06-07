# PLAN.md

Checklist plan + definition of done. Work top-down; don't check an item without a green `VERIFY.md` run. Design rationale lives in `BUILD_PLAN_HELIXPAY.md` (§ refs below).

## Build order — depth-first, stop-lined

Prove the skeleton **live** first, then build one trap all the way through, then widen. Each phase ends somewhere coherent; **a stop-line is a place you could ship from.** Don't walk the dependency graph breadth-first — that yields eleven half-built modules and zero green evals. Times are budget guides for a ~4–6h build.

### Phase 0 — Grounding (DONE) ✓
- [x] Corpus validation PASSED (`PHASE_0_CORPUS_VALIDATION.md`): full read of all 24 interviews + chat/email/dashboards/PDFs; traps verified; MRR/T3 corrected; vocab (`attributes.py`), alias+anti-alias ledger (`aliases.py`), source-tier (`ontology.RELIABILITY`) committed; budget decided (whole_corpus, ~55K tok); evals seeded + held-out locked.
- [x] Frozen contract + rule tables + parallel-build aids: `schema.py` (34 typed contracts: 24 models + 10 enums); `profiler.plan_pipeline`/`health.ACTIONS`/`ontology.RELIABILITY`; `synthesis/_mock.py` (frozen TrustEnvelope, all 4 statuses); fixtures `assertions_resolve.json` (resolve mechanics) + `extraction_golden.json` (prompt regression).
- **Stop-line (met):** the eval set matches reality; no fictional traps.

### Phase 1 — Skeleton live (~45m)  ← BLOCKING: no Phase 2+ until a live URL returns green /health
- [ ] `./install.sh` → compose up → `/health` green → **`fly deploy` to a real URL**, all answering from `synthesis/_mock.answer()` (fixed `TrustEnvelope`). Bearer-token auth on everything but `/health`.
- **Stop-line:** a live production URL returns a well-formed envelope from the mock. "Live in production" (a pass/fail brief requirement) is now de-risked at hour ~1; everything after is swapping real logic behind the frozen return type. (§4.6, §5)

### Phase 2 — Ontology spine, no LLM (~1h)  ← highest-leverage hour
- [x] `ontology.upsert` (idempotent, stable `assertion_id`) + `ontology.resolve` (scope-aware conflict → current view + `Dissent`) + `ontology.query` (ontology-first read); `Assertion`/`Alias`/`SourceTier`/`RelationKind` wired. Pure functions, unit-tested against `tests/fixtures/assertions_resolve.json` (`tests/test_ontology.py`, 10 cases green).
- **Stop-line:** `resolve()` separates "both true" (NPS 62 sea_enterprise vs 47 aggregate) from a real same-scope conflict + supersession, and re-ingest is idempotent — all on synthetic data, zero external deps. (§4.13)

### Phase 3 — First vertical slice (~1.5h)  ← DEFENSIBLE SUBMISSION
- [ ] Thinnest path for the two most-confident traps (`confluence-launch` staleness + `nps-segmented` scope): loaders for only those formats → extraction prompt (regression-tested vs `tests/fixtures/extraction_golden.json`) → upsert/resolve → **`ontology.query` (ontology-first answer source)** → `synthesis/envelope` → `/ask`, swapped in behind the mock on the **live** endpoint. The `without_harness` baseline answers the same cases over the raw corpus; the slice path must beat it.
- **Stop-line:** those 2 real evals green end-to-end on the live URL; `delta.pass_rate > 0`, with **`answer_path=ontology` and every claim carrying an `assertion_id`** (proves the ontology answered, not raw retrieval). **If you stop here, you have a defensible submission.** Flip `HOUSE_HARNESS_SERVE_MODE=live`; graded answers must be `mode=live` (mock fails `make validate`). (§4.1, §4.4)

### Phase 4 — Widen (~1h)  ← each addition individually droppable
- [ ] Remaining loaders + traps; profiler rule table; abstention + authority-routed escalation; harness extraction (alias/anti-alias resolution via `aliases.py`, contradiction+staleness → taxonomy + typed graph) → emit `HELIXPAY.md` + `graph.json`; `assess_harness` health; **vision chart extraction (`load_image`)** — IN scope, but after the green slice and with no eval depending on it (on this corpus the charts duplicate text; vision is the generality capability). The ingestion untrusted-content gate + egress redaction ship here too. (§4.0, §4.2, §4.5, §4.9)

### Phase 5 — Harden + write-up (~45m)  ← the write-up is graded; protect it
- [ ] Step/timeout/cost caps; LangSmith tracing on (graceful off without key); alias-resolution eval (A1); `make validate`; **`SOLUTION.md`** (run-in-one-command, tradeoffs, architecture justification, honest deferred-roadmap, `<DEPLOY_URL>` + cold-start).
- **Deferred for v1 (designed, not built — named in SOLUTION):** (1) self-correcting feedback loop §4.11; (2) reader/executor privilege split §4.10 — v1's live surface is read-only Q&A with no privileged actions to gate, so the split's runtime enforcement waits until an action surface exists (the read-only protections — untrusted-content gate + egress redaction — still ship); (3) confidence calibration/fine-tuning (ships honest-but-uncalibrated); (4) a larger eval set beyond the 13 seeded + held-out. Plus the standing scale-path items: Hybrid/pgvector, full multilingual.

## Definition of done
- [ ] `./install.sh` brings the system up from a fresh clone in one command; `/health` is green.
- [ ] Every answer returns the full trust envelope — claims **sourced** (cite-or-abstain; entailment scored offline), freshness, dissent, coverage gaps, `escalate_to`, confidence, status.
- [ ] `make eval` passes the gate: `delta.pass_rate > 0` (with-harness beats without-harness) across question classes.
- [ ] Contradiction, staleness, alias, hierarchy, and source-attribution question classes each covered by ≥1 passing case.
- [ ] No claim without a source; abstains instead of confabulating; unsupported claims dropped/downgraded.
- [ ] Ingestion is per-file isolated; agents run under step/timeout/cost caps; egress redaction on.
- [ ] `VERIFY.md` runs green end to end; `PROGRESS.md` and this file are current.
- [ ] **Validation passed** — every blocking check in `VALIDATION.md` is green and `evals/validation/report.json` is committed. This is the go/no-go gate for submission.
