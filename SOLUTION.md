# SOLUTION.md

## What this is

A **company harness** built over a company's raw document corpus. It resolves the
snapshot into a queryable **ontology** and emits a generated `<COMPANY>.md` (charter,
targets, guardrails + authorities, taxonomy, and a "needs clarification" gap mirror) —
the compact, sourced artifact an agent loads to *operate as the company* without
reading everything.

The consumer is an agent. The primary interface is **MCP** (six tools); HTTP `/ask`
is the same engine over a socket. Every answer is a **trust envelope** — not a string,
but sourced claims + dissent + freshness + coverage gaps + authority-routed escalation
+ confidence — so an agent can act on it, not just read it.

## How to run (one command, fresh clone)

```bash
git clone github.com/teionarr/cds-house-harness && cd cds-house-harness   # corpus vendored in data/
./install.sh                                                              # docker compose up, ingest data/ on boot, health-check
```

Needs Docker + `ANTHROPIC_API_KEY` (seeded into `.env` on first run; LangSmith tracing
and Doppler optional). Serves on `:8080` — `/mcp` (MCP), `/ask` (HTTP), `/health`.

The MCP server is also **hosted**, so a reviewer can use it as a normal Claude MCP with
one command — no clone, no build:

```bash
claude mcp add --transport http house-harness https://house-harness.fly.dev/mcp
# ...then ask the agent. Tools: ask_company, get_harness, get_harness_health, get_entity,
#   plus list_commands + run_command — a menu of ready-made commands you can run by name.

# Or hit the same engine over HTTP:
curl -s https://house-harness.fly.dev/ask -H "Authorization: Bearer $HOUSE_HARNESS_API_TOKEN" \
  -d '{"q":"Who can approve a customer discount, and when does Confluence go GA?"}'
```

Live instance: **https://house-harness.fly.dev** (Fly.io). `/health` is open and echoes
the serve mode; `/ask` is bearer-gated; the `/mcp` endpoint is **open (no token)** for
one-command demo use — gate it with a header token for production. Machines scale to
zero, so the first call after idle wakes in a few seconds.

**Try the cross-cutting questions** (each spans documents that disagree):
- *"When does Confluence launch?"* → **Sep 30**, with the public June date flagged as the superseded line.
- *"What's our NPS?"* → **47 aggregate and 62 SEA-enterprise** — both true, both sourced (scope, not conflict).
- *"Can I trust the Brazil HubSpot pipeline?"* → No — Brazil runs on Pipedrive; the 78% is SEA-weighted.
- *"Who owns the merchant_id schema?"* → Sara Wijaya / Vikram Patel / Camila Souza / Luiz Ferreira.
- *"Is POS Self-Service the same as POS?"* → No. *"Which Maria?"* → Santos (CS) vs Silva (Sales), kept distinct.

## Architecture — the choices that mattered

- **Facts are assertions, not settled values.** Every fact is a sourced, dated, scoped
  `Assertion`; entities, targets, and the org graph are views over them. One model
  carries staleness (supersession), contradiction (≥2 live assertions, same scope),
  segmentation (NPS 62 SEA-ent vs 47 aggregate are *both true*), and attribution. This
  is the "ontology, not search engine" answer the brief asks for.
- **Ingestion-heavy, query-first split.** Entity/alias resolution and per-fact
  resolution (staleness, conflict-vs-scope, source tier, hierarchy) happen *once* at
  ingest. The query path resolves a question to its `(subject, attribute, scope)`, reads
  the resolved slice, reasons over that, and cites. The deep questions are answered from
  precomputed structure, not by re-reading raw contradictory text — so they stay
  correct, and per-query cost is O(slice), flat as a live corpus grows. **This is the
  fork I'd defend hardest:** a model staring at the whole corpus reproduces exactly the
  staleness/contradiction failures the ontology resolves deterministically.
- **Bitemporal — validity vs recording are separate axes.** `as_of` is when a fact was
  *true* (the GA slipped *to* Sep 30) and drives supersession; `recorded_at` is when it
  was *written down* and drives staleness. Conflating them is the usual reason staleness
  gets hand-waved; kept apart, a freshly-recorded restatement of an old fact reads
  differently from one nobody has touched.
- **Source reliability tiers.** `filing > board > official > interview > chat` breaks
  conflict ties and weights confidence — a board email outweighs a Slack joke, so chat
  chatter never becomes a fact.
- **Retrieval is the fallback, not the path.** Graded questions answer from the ontology.
  Out-of-namespace questions load the corpus raw (it fits the budget); dense + sparse +
  graph + rerank is the documented scale path, not built before it's needed. The uplift
  metric keeps this honest: `without_harness` reasons over the raw corpus, `with_harness`
  over the ontology — the delta is the structured layer's value, same model both arms.
- **Corpus-agnostic by construction.** The attribute namespace that makes grouping fire
  (so "MRR"/"recurring revenue"/"rev" collide and a contradiction surfaces) is a
  universal KERNEL plus a DOMAIN vocab *induced from the corpus* at ingest and pinned —
  not hand-authored per company. Point it at a new corpus and it derives its own
  namespace; the name registry is likewise built from the org chart. Turnkey, not a
  re-authoring exercise.
- **Moving target handled.** A file-hash manifest rebuilds only on change (new, edited,
  *or removed*); stable assertion ids upsert and supersede with no double-counting; a
  retracted source is reconciled out. Re-ingestion is config, not a rewrite.
- **Swappable model seam.** The model sits behind one config line (`config/llm.py`,
  default `anthropic:claude-sonnet-4-6`); the owned, compounding layer is the ontology,
  the harness, and the evals.

## Tradeoffs

- **Wholesale rebuild on change, not per-file incremental.** The manifest skips
  unchanged files, but when anything changes the harness rebuilds from the full corpus
  (charter/graph need the whole set). Simpler and provably correct at this size;
  per-file incremental is the next step.
- **Deterministic conflict resolution over an LLM judge.** Current-vs-conflict is decided
  by `(tier, recency)` rules — reproducible, cheap, auditable — at the cost of not
  resolving conflicts that need semantic nuance (those surface as `Dissent` for a human).
- **Text-first ingestion; charts via a vision-LLM pass.** On this corpus the charts
  restate facts already in prose, so vision doesn't move the number here — it's carried
  for generality, not this snapshot.
- **SQLite + raw-corpus fallback, no vector index.** Graded questions answer from the
  ontology; the corpus fits the context budget. pgvector/hybrid is the scale path.
- **Name canonicalization under-merges on purpose.** A first name resolves only when
  unambiguous in the roster (`Sofia`→`Sofia Almeida`, but `Maria`/`Wei` stay unmerged).
  Silent over-merge is worse than an unmerged mention.

## What I didn't tackle (and why)

The dataset has more quirks than belong in this scope. Three groups, named rather than
hidden:

**Designed, deferred out of the time box** (seams in place):
- **Self-correcting feedback loop** — a correction → new source + gold case + re-extract.
  Less important now because the read path is already correct; today a fix means editing
  the source and re-ingesting (deltas only).
- **Reader/executor privilege split** — the typed boundary for an *action* surface. The
  live product is read-only Q&A, so there's nothing privileged to gate yet; the
  protections a read-only system actually needs (untrusted-content gate, egress
  redaction) do ship.
- **Hybrid retrieval + trained reranker + pgvector** — the scale-path fallback. Pure
  capacity, not correctness; building it before a corpus outgrows the budget is
  speculative.
- **Confidence calibration** and a **larger adversarial eval set** — both move the system
  from "honest" toward "tuned"; valuable, but not what makes or breaks the core.
- **As-of-recording time-travel queries** — the store *is* bitemporal and retains
  superseded history, so "what did we believe on date X" is answerable from the data; it
  just isn't exposed as a query API. Matters less than getting *current* staleness right,
  which the two axes already do.

**Honest limits of what ships** (no runtime fix — said plainly):
- **Entailment verification checks support, not truth.** It catches "the cited span
  doesn't support this claim," not "the source itself is wrong." For arbitrary questions
  there's no ground-truth oracle; only the feedback loop can overwrite a wrong source.
- **Confidence is honest, not calibrated.** It tracks coverage + source tier + dissent, so
  it moves in the right direction, but it isn't tuned against a labeled set and isn't a
  per-answer guarantee.
- **Answer completeness on some multi-fact questions.** For *"can I trust the Brazil
  HubSpot pipeline?"* the ontology resolves the migration-status facts (Brazil not yet
  migrated, 0%) and correctly says don't trust it — but doesn't always name the system of
  record (Pipedrive) that a whole-corpus read surfaces. The fact is in the ontology
  (`crm.system_of_record`); broadening the resolved slice to pull *related* facts for
  "can I trust X" questions is deferred query-path tuning. (In the uplift eval this shows
  as the one case where the raw baseline edges the harness — named, not hidden.)

**Fundamental scope calls** (the most interesting ones to name):
- **The edge is scale-conditional — and the numbers say so plainly.** On the held-out set
  the harness **ties** a fair full-corpus baseline (0.75 vs 0.75, **Δ = 0**); on the tuned
  build set it edges ahead (Δ ≈ +0.03). The win that *does* show at this size is **cost —
  2.2× fewer tokens/$** (26.5K vs 60.8K per query), with latency roughly flat. The
  ontology's accuracy advantages — correctness under contradiction, recording-time
  staleness — bite hardest on a corpus large enough that reading it raw *fails*; at ~54K
  tokens the whole thing fits in context, so a "read everything" baseline is already
  strong. The architecture targets the larger regime; this corpus can't enter it. We
  report the tie rather than hide it.
- **The edge is self-graded, and routing is tuned to expected phrasings.** Uplift is
  measured on our own eval set, and the deterministic hierarchy/contradiction routing is
  pattern-matched to anticipated wording. A blind, paraphrase-heavy held-out set plus
  semantic intent detection would prove robustness against questions we didn't foresee.

None of these change the correctness of what ships — only how far its advantages can be
demonstrated inside the time box.

## How LLMs are used

- **At ingest:** one structured pass per document emits assertions + relations +
  guardrails; the deterministic layer (alias ledger, namespace, source tiers, the
  ontology) decides what's current and what conflicts. Vocabulary and charter are
  induced; conflict resolution is rules, never an opinion.
- **At query:** the model reasons over the resolved slice with enforced citation and
  conflict surfacing — it composes the answer, it does not adjudicate the facts.
- **Provider isolation:** only `config/llm.py` touches a model SDK; every call goes
  through a validate-and-repair wrapper with prompt caching and usage tracking, so the
  model is swappable config.
