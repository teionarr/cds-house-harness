# SOLUTION.md

## What this is
A **company harness** over HelixPay's raw data: it turns the snapshot into a queryable ontology plus an agent-facing interface, and emits a generated `HELIXPAY.md` (taxonomy + company rules + playbooks + alias glossary) that an agent can load to operate as HelixPay. The consumer is an agent, via MCP (primary) or HTTP `/ask`.

## Run it (one command, fresh clone)
```bash
git clone github.com/teionarr/cds-house-harness && cd cds-house-harness   # HelixPay data/ is vendored in
./install.sh           # builds & starts the app (SQLite store), ingests data/ on boot, prints the endpoint
# then:
curl -s localhost:8080/ask -H "Authorization: Bearer $HOUSE_HARNESS_API_TOKEN" \
  -d '{"q":"Who can approve a customer discount, and what is the Confluence GA date?"}'
```
Live instance: **<DEPLOY_URL>** (Fly.io; `fly.toml`). Auth: bearer token `HOUSE_HARNESS_API_TOKEN` on all endpoints except `/health`. Cold-start: machines scale to zero, so the first call after idle takes a few seconds to wake.

## Architecture — the calls that mattered
- **Facts are assertions, not settled values.** Every fact is a sourced, dated, scoped `Assertion`; entities/targets/graph are views over them. One model carries staleness (supersedes), contradiction (≥2 live assertions, same scope), segmentation (NPS 62 SEA-ent vs 47 aggregate are *both true*, not a conflict), and attribution. This is the "ontology, not search engine" answer.
- **Source reliability.** A `SourceTier` (filing > board > official > interview > chat) breaks conflict ties and weights confidence — a board email outweighs a Slack joke, so F1 chatter never becomes a fact.
- **Idempotent re-ingest, deltas only.** A file-hash manifest means a re-run (or a cold boot) re-processes ONLY new/changed files, not the whole corpus. Stable assertion ids (hash of subject+attribute+scope+source) then upsert and supersede — the moving-target case, no double-counting, persisted on the Fly volume.
- **Harness, not search.** We derive taxonomy + rules + playbooks at ingestion and expose them, rather than returning passages. Justification: the brief asks for an *ontology an agent reasons over*; a harness is the reusable form of that.
- **Ingestion-time vs query-time split (ingestion-heavy, ontology-first query).** Entity/alias resolution and per-fact resolution (staleness, conflict-vs-scope, source-tier, hierarchy) happen once at ingest. Query-time is ontology-first: resolve the question to its `(subject, attribute, scope)`, read the resolved assertion slice (values + dissent + as-of + sources), reason over that, cite. The deep questions are answered from precomputed structure, not by re-reading raw text — so they stay correct, and per-query cost is O(slice), flat as a live corpus grows.
- **Retrieval is the fallback, not the path.** The graded questions are answered from the ontology, not from retrieval. Whole-corpus-over-raw is deliberately *not* the default: fitting the ~55K-token budget is a capacity fact, not a correctness one (a model over raw contradictory text reproduces the failures the ontology prevents). For out-of-namespace questions v1 loads the corpus raw (SQLite, no index); dense (pgvector) + sparse (FTS/BM25) + graph + RRF + rerank is the documented scale fallback when a live corpus outgrows the budget. Uplift makes this honest: `without_harness` answers over the raw corpus, `with_harness` over the ontology — the delta is the structured layer's value.
- **Contradiction-aware.** Conflicting facts are surfaced with sources + recency; the system states which it treats as current and why.
- **Swappable stack.** Model behind one config seam; owned layer is the ontology, the harness, and the eval set.
- **Caps in one chokepoint.** Agent step/timeout/cost caps live in `agents/runner.py` as a single enforcement point (not scattered across call sites); a breach surfaces as a `degraded`/`failed` envelope. Wired in when `serve/` lands — deliberate, not an oversight.

## Demo queries (the planted traps + the three agents)
- *Exec brief:* "When does Confluence launch?" → Sep 30, with June flagged as the stale public line. "What's our NPS?" → 62 (SEA-ent) **and** 47 (aggregate), both sourced.
- *Sales prep:* "Can I trust the Brazil HubSpot pipeline?" → no, Brazil's on Pipedrive; 78% is SEA-weighted. "Why did Cosmos Hotels leave?" → multi-property gap.
- *Support / ops:* "Who owns the merchant_id schema?" → Sara Wijaya / Vikram Patel / Camila Souza. "Is POS Self-Service the same as POS?" → no.
- *Entity resolution:* "Which Maria?" → Santos vs Silva, kept distinct.

## Tradeoffs
- <e.g. chose LLM reranker over a trained cross-encoder to fit the time budget>
- <e.g. text-first ingestion; chart images parsed from their textual equivalents>
- <...>

## What I didn't tackle (and why) — deliberate v1 scope
Built to a working live slice that answers the deep cross-cutting questions from the ontology and beats a raw-corpus baseline, **plus chart-image reading**. Four things are designed (types + architecture in place) but deferred out of the time box:
- **Self-correcting feedback loop (§4.11).** Corrections/escalations → new source + gold case + re-extract. Deferred whole; the architecture leaves a clean seam for it.
- **Reader/executor privilege split (§4.10).** The typed boundary and intent are in the design, but v1's live surface is **read-only Q&A** — there are no privileged actions to gate yet, so the split's runtime enforcement (pods + executor allowlist) waits until an action surface exists. The protections a read-only system actually needs — the ingestion **untrusted-content gate** and **egress redaction** — do ship.
- **Confidence calibration / fine-tuning.** Confidence ships honest but uncalibrated (it tracks coverage + source tier + dissent); tuning it against a larger labeled set is future work.
- **A larger eval set.** 13 seeded cases across every trap class + a locked held-out set; growing it (more paraphrases, more adversarial) is deferred.
- *Kept in scope:* **vision chart extraction** (`load_image`). Note: on this corpus the 4 charts render facts already in the text, so vision doesn't move the uplift number here — it's the generality capability (a live corpus has charts not duplicated in prose), built after the green slice with no eval depending on it. (WebPlotDigitizer was evaluated and rejected for the automated path — per-chart calibration, AGPL, paid auto-mode; a vision-LLM pass is used instead.)
- *Also standing scale-path / not v1:* trained reranker, Hybrid/pgvector, full multilingual normalization — diminishing returns inside 4–6h.

## Known limits (stated plainly)
Two pieces close real gaps but don't fully solve them, and it's more honest to say so than to imply otherwise:
- **No self-correcting loop in v1.** When a source is wrong, there's no in-product path yet to capture a correction and re-extract — that's the deferred feedback loop (§4.11). Today a fix means editing the source and re-ingesting (deltas only).
- **Entailment verification checks support, not truth.** It catches "the cited span doesn't support this claim" — it does **not** catch "the source itself is wrong." A confidently-cited claim from a wrong source still passes. There is no runtime fix for that: for arbitrary questions there's no ground-truth oracle. The only correction path is the feedback loop slowly overwriting bad sources as people flag them.
- **Confidence is honest, not calibrated.** The confidence field is computed from ontology coverage + source tier + dissent so it moves in the right direction; it is **not** tuned against a labeled set in v1 (calibration is deferred), and it is not a per-answer guarantee. The system optimizes for *grounded, consistent, and verified-against-source*, and surfaces uncertainty — not for an unobtainable runtime truth.

## How LLMs are used in the system
- At ingestion: entity/alias resolution, rule + playbook extraction, taxonomy synthesis.
- At query: reasoning over retrieved + graph-expanded context, with enforced citation and conflict surfacing.
- In development: most code is LLM-written; conventions are enforced by `AGENTS.md` (`CLAUDE.md` points to it), the AGENTS/PLAN/PROGRESS/VERIFY external-memory flow, a `cto` planning subagent, and **Greptile** PR review (`greptile.json`).
