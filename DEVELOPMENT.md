# DEVELOPMENT.md

How the engine is built and how to take it further from here. For *what it does* and
*why the calls were made*, read [`SOLUTION.md`](./SOLUTION.md); this is the engineering
companion.

## Architecture in one pass

The engine is **ingestion-heavy, query-light**. All the hard resolution happens once
at ingest; the query path reads a small, already-resolved slice.

```
data/ ──ingest──▶ extraction ──▶ ontology spine ──▶ SQLite store ──┐
        (loaders,    (one LLM pass    (assertions:                  │
         gate)        per doc →        resolve / supersede /        │
                      assertions)      dissent / scope)             │
                                                                    ▼
agent ──MCP / HTTP──▶ answer() ──▶ ontology-first query ──▶ trust envelope
                                   (raw-corpus fallback if
                                    out-of-namespace)
```

**The spine (`pipeline/ontology.py`).** Every fact is an `Assertion` — sourced, dated
(`as_of` = valid time, `recorded_at` = transaction time), scoped, tiered. `upsert`
applies same-tier recency supersession; `resolve`/`query` group by
`(subject, attribute, scope)` and emit `Dissent` when single-valued facts disagree.
This is pure over an in-memory `dict[str, Assertion]`, so it unit-tests against
fixtures with no database. `pipeline/store.py` is the only SQLite-aware module — swap
it for pgvector/Postgres and nothing above it changes.

**Why determinism here matters.** Which assertion is *current* and which *conflict* is
decided by rules (tier, recency, scope), not an LLM opinion — reproducible and
auditable. The model's only job is to *emit* assertions during extraction.

## Point it at a new corpus

The engine is corpus-agnostic by construction; re-pointing is config, not a rewrite:

1. Replace `data/` (or pass a path: `house-harness run <corpus>`).
2. On ingest, three things derive themselves from the new corpus:
   - **Attribute vocabulary** (`pipeline/vocab.py`) — a universal org/person KERNEL
     stays fixed; the DOMAIN keys are *induced* from the corpus and pinned to the
     store, so `resolve()`'s grouping fires without hand-authoring keys. The
     `new_attribute:<slug>` escape hatch flags whatever induction misses.
   - **Name registry** (`pipeline/names.py`) — built from the org chart; canonicalizes
     casing/first-name variants, never over-merging ambiguous names.
   - **Source-tier map** (`pipeline/ontology.py:RELIABILITY`) — doc-type → reliability;
     adjust if a new corpus has source types not covered.
3. `pipeline/aliases.py` holds the product/org alias ledger and the **anti-aliases**
   (the must-not-merge pairs). The safe default is under-merge; add corpus-specific
   anti-aliases here when two distinct entities share a surface form.

## Commands

```bash
make setup      # uv sync (Python 3.12)
make lint       # ruff
make type       # pyright
make test       # pytest  (model-touching tests skip without ANTHROPIC_API_KEY)
make run        # full pipeline over data/ → SQLite + out/<COMPANY>.md + graph.json
make start      # serve the agent interface locally
make eval       # with- vs without-harness uplift gate (subset)
make validate   # the acceptance gate (see below)
make docker     # build the image
make package    # zip the committed files for delivery
```

## Serving surfaces

One process, one port (`APP_PORT`, default 8080), three routes:

- **`/mcp`** — the MCP server (FastMCP, streamable-http), exposing six tools:
  `ask_company`, `get_harness`, `get_harness_health`, `get_entity`, and `list_commands`
  / `run_command` (a discoverable menu of named commands). `house-harness mcp` runs it
  over **stdio** for a local agent to spawn; `house-harness mcp --transport
  streamable-http` hosts it at a URL a client adds with `claude mcp add --transport
  http <name> https://<host>/mcp`. This is what the Fly deploy runs (open, no token).
- **`/health`** — open deploy probe (`{status, mode}`).
- **`/ask`** — token-gated REST fallback for non-MCP clients (`{"q": "..."}` → envelope).

`/mcp` and `/ask` both route through `serve.app.answer`, so the surfaces never diverge.
`house-harness serve` still runs the stdlib HTTP-only server (`/health` + `/ask`) for
environments without the MCP deps.

## The acceptance gate (`make validate`)

The post-build go/no-go, run against the live system on the real corpus. It writes
`evals/validation/report.json` and exits non-zero on any blocking failure.

- **Held-out discipline.** `evals/validation/validation.json` (paraphrased trap classes
  + abstain/reliability negatives) is locked *before* tuning and never touched in the
  dev loop — scoring on the build set `evals/evals.json` is not validation.
- **Blocking checks.** Alias precision (≥0.95 — over-merge is silent corruption),
  staleness + as-of, contradiction recall with zero fabrication, hierarchy accuracy,
  source attribution, claim entailment, abstention on out-of-corpus questions, prompt
  injection (zero successful), egress redaction (zero leaks), and **uplift > 0** on the
  held-out set. Every graded answer must be `mode == "live"` and `answer_path ==
  "ontology"` with an `assertion_id` on every claim — a graded trap answered from the
  raw fallback is a fail.
- **Mechanical guards (code-checked, not LLM-judged):** `attributes.nonconformant(...)
  == []` on every extraction (no silent attribute synonyms), and `resolve()` fires
  correctly on `tests/fixtures/assertions_resolve.json`.

## Deferred build paths (interfaces in place)

These have types/seams in the codebase and are intended next steps — see `SOLUTION.md`
"What I didn't tackle" for the rationale:

- **Reader/executor privilege split** (`agents/reader.py`, `agents/executor.py`) — the
  typed boundary for an action surface. Raise `NotImplementedError` by design; the live
  product is read-only Q&A, so there are no privileged actions to gate yet.
- **Hybrid retrieval** (`retrieval/hybrid.py`) — dense + sparse + graph + rerank, the
  scale-path fallback behind the `WholeCorpus` default. Stubbed until a live corpus
  outgrows the context budget.
- **Self-correcting feedback loop** (`schema.Feedback`) — correction → new source + gold
  case + re-extract. Designed, not wired.
- **Eval speed + cost** (`evals/harness.py`) — the case loop runs sequentially and the
  *fair* baseline pushes the whole corpus (~55K tokens) through the model on every case,
  so a full 30-case run is ~10–20 min **and spends substantial API credits each time**.
  Levers: parallelize the case loop (bounded workers); cut the baseline spend via a
  prompt-cached corpus prefix and/or a smaller default subset. Deferred — coverage over
  speed/cost for now; the suite is broad on purpose.

## Iteration speed — the 10× levers (future work)

The dev loop is slower than it should be. Four things are slow; the meta-principle is
the same for all of them: **stop paying the full cost on every iteration — cache,
decouple, tier, and parallelize so each loop pays only for what changed.**

1. **Deploy is slow because extraction runs on boot → ship a pre-built data artifact.**
   *(biggest win)* Today: deploy → restart → re-extract ~6 min on the box (which OOM-loops
   on a small machine — see why `fly.toml` declares 2GB). Fix: build the ontology **in CI
   as an artifact** (or a one-off job), bake/upload the finished SQLite DB, and have the
   server just *load* it. Boot drops from ~6 min + crash-risk to **seconds**, and
   extraction stops competing with the web server for RAM. **~50× on the deploy loop.**

2. **Evals + extraction re-run from scratch every time → record-replay the LLM calls.**
   *(biggest $ + dev-loop win)* Today an eval is ~25 min / ~$6 and an extraction ~6 min /
   ~$4, even when one line changed. Fix: **cache model responses keyed by (prompt-hash,
   model)**. Unchanged cases replay instantly and free; only the diff hits the API. A
   re-run after a small change goes from 25 min to ~30s and ~$0 — the single
   highest-leverage change, since ~90% of iterations change one thing. **~20× + ~$0.**

3. **Evals are sequential with a 55K-token baseline per case → parallelize + cache + tier.**
   Parallelize the case loop (8–16 workers): 25 min → ~2–3 min. Prompt-cache the baseline
   corpus prefix (same 55K every case → cache hits ~10× cheaper). **Tier it:** a ~5-case
   smoke suite (~30s) on every push; the full 30-case + held-out only pre-merge/nightly.
   Don't pay 25 min to check a typo. **~10× on the eval loop.**

4. **Every change is a full PR through a multi-minute review gate → tier the gate + auto-merge.**
   The AI review (3–8 min) is the long pole and it blocks merge. Run it **async/advisory**
   (review after merge, or on-demand), not as a required check on every trivial change.
   Use `gh pr merge --auto` so green PRs merge themselves. For solo/small-team: reserve the
   PR ceremony for substantive code; allow direct-to-main (`[skip ci]`) for docs/config.
   **~5× on the change loop.**

**Paper-cuts to kill:** fix the editable install so `house-harness` runs without a
`PYTHONPATH=src` workaround; and pin local Doppler to the real project so the key resolves
first try.

## Conventions

- **Typed boundaries.** `schema.py` is the only coupling between ingest / pipeline /
  synthesis / serve — no raw dicts across module lines. Change it deliberately.
- **Provider isolation.** Only `config/llm.py` imports a model SDK; everything else
  goes through `config/structured.llm_json` (validate-and-repair, prompt caching, usage
  tracking).
- **Grounded ≠ correct.** A citation proves a claim wasn't invented, not that it's true.
  Correctness lives in entailment verification and the evals, not in retrieval scores.
- **Gates.** `make lint && make type && make test` before a commit; CI runs them plus
  the eval gate (`.github/workflows/`). Secrets via Doppler or `.env` (never committed).
- **Branch flow.** `main` is protected: no force-push or deletion, and merges go through
  a pull request with the required checks green — `quality`, `deploy-smoke`, and
  `Greptile Review`. Work on a branch, open a PR, let CI + Greptile (`greptile.json`
  rules) review it, merge when green. The deploy job ships to Fly on green `main`.
