# House Harness — Company Definition Engine: Build Plan

*HelixPay is the working dataset in this plan; the engine is general — point it at any company's document set.*

> 4–6 focused hours of build. The core idea: a company is now defined by its harness the way an agent is — a set of artifacts (taxonomy, charter, evals, guardrails) that say what it is and how it operates. We don't extract pieces of context; we run an engine that distills a company's scattered documents into that **House Harness** — the boiled-down core most companies can't articulate but recognize the moment they see it — and ship every answer with a **trust envelope** so an agent can act on it rather than guess. Built from business requirements through evals before any feature code.

---

## 0. Thesis — the House Harness is the company's edge

An AI harness is the set of tools that defines a single agent — its context, its instructions, its evals, its guardrails. The **House Harness** is the same idea raised to the level of a company: the set of artifacts that defines the organization itself. In the AI era this is the thing that matters most — the layer agents (and people) operate inside. Context tooling today stops at retrieval and hands back passages; that is a *data provider*. We build the engine above it: it reads a company's scattered, contradictory, half-stale documents and distills them into a small library of defining artifacts — the company's soul, boiled down to a core it will recognize on sight.

The arc is the tell. Agent development already moved from **context management** — getting the right text into the model — to **harness management**: governing the whole apparatus (tools, evals, guardrails, orchestration) the model runs inside. Company tooling is one step behind, still treating a company as context to retrieve. The House Harness is that same shift at the company level. Today it presents as context *for* AI; it is built to become the company's managed harness. We build it that way from the start — ahead of where the market is looking.

The headline output is a generated **`HELIXPAY.md`** (the engine emits `<COMPANY>.md` for any input) plus a queryable ontology. A harness file at the repo root is the AI-native convention — the same shape an AI-native company is already operated through. And because the input could be any company's document set, the engine **profiles the corpus first and assembles the right architecture for it** (§4.0) — and tells you, in plain terms, why it chose what it chose.

The defining artifacts, with scope set deliberately (see §8):

**In scope — the core the engine distills now:**
- **Context / retrieval** — the corpus + ontology.
- **Taxonomy** — entities, relations, glossary, resolved aliases, as-of dates.
- **Charter** — mission and operating principles.
- **Evals** — the company's own KPIs, targets, and definitions of "good".
- **Guardrails** — policies, decisions, constraints, and **approval authorities** (who owns pricing, what was committed to the board), enforced at runtime as data-transfer gates (§4.8).
- **Trust / provenance** — the trust envelope with abstention + authority-routed escalation (§4.4).
- **Harness health** — the mirror: what's missing or off in the harness, with quick-win actions and owners (§4.2).

**Deferred (named in §8):** capabilities/action-surface (sketch only), orchestration/decision workflows (who-owns-what only), tracing/audit, the *automatic* learning loop (the capture loop itself is in scope, §4.11), and general decision-engine behavior.

---

## 1. Business requirements (start here)

The consumer is an agent acting for a HelixPay exec. The questions that matter cut across the dataset and have no single-passage answer. Question classes (each is a business need, and each becomes an eval class):

1. **Hierarchy / ownership** — who reports to whom, who owns metric/product X (cross-references org-chart + interviews + chat; the org-chart is stale by design).
2. **Financial / metric, with staleness** — the real number for a KPI, where Q1 PDF, board deck, and weekly review disagree → answer the *current* value and name the conflict.
3. **Decisions / policy** — what was decided and by whom (all-hands, board update, exec email).
4. **Status / risk** — what's at risk, what's blocked (weekly review + chat).
5. **Identity / alias** — resolve the same person/team across inconsistent naming; the CEO has no structured interview and must be assembled from scattered mentions.
6. **Contradiction** — where do sources disagree, and which is authoritative.

## 2. Evals — the spine, defined before building

Per the Operating Map: decide what "good" is first. Borrow the eval-driven *methodology* (agentskills.io's skill-evaluation guide; the `skill-creator` skill as a reference), but the **runner is a small headless Python harness** (`evals/run.py`, invoked by `make eval` and `evals.yml`) — not an external/interactive tool — because the gate must run deterministically in CI. It reads `evals/evals.json`, and for each case calls the system twice (`with_harness` = ontology-first via `synthesis.respond.answer`; `without_harness` = the fair raw-corpus baseline in `baseline_spec`). Mechanical assertions (valid envelope, `status`/`confidence` enum, sources resolve, `answer_path`, `assertion_id` present) are checked in code; judgment assertions go to a batched **LLM judge** at temperature 0 that must cite evidence for a PASS. It writes `benchmark.json` and exits non-zero if `delta.pass_rate <= 0`.

**The headline metric is uplift.** Run every case twice — **with_harness** (answering from the resolved ontology slice, ontology-first) and **without_harness** (a baseline agent over the raw corpus, the 'search box') — and measure the delta. The delta isolates the value of the structured layer, not of one extra document; a harness that doesn't beat the raw baseline isn't earning its place. The baseline must be **fair** (same model + same corpus access — evals `baseline_spec`); a too-weak baseline flatters us as badly as a too-strong one. A planted `uplift-canary` case must split (baseline fails, harness passes), so a non-positive delta diagnoses the rig (strawman baseline / shared context source / harness off-path), not the harness.

Three correctness checks sit alongside uplift, because *grounded is not correct* (§4.12): **entailment** — every cited claim's span must actually support it (`verified`); **calibration** — high-confidence answers must actually be right more often than low-confidence ones, so the confidence number means something; and **extraction evals** — grade the engine's resolved entities and especially **alias resolution** (precision/recall) directly, since a bad merge silently corrupts everything downstream. These are gold-set measures, not runtime machinery.

**You author one file, `evals/evals.json`** — 15–25 cases across the §1 question classes. Each case is a realistic agent prompt, an `expected_output`, and `assertions` (added after the first run reveals what "good" looks like):

```json
{
  "suite": "helixpay",
  "evals": [
    {"id": "discount-authority",
     "prompt": "Who can approve a customer discount?",
     "expected_output": "Sofia Almeida (CRO) — she approved the Lazada discount. The org chart names no separate pricing owner.",
     "assertions": ["names Sofia Almeida (CRO) as the approver",
                    "cites the source (Tom Holloway interview / org chart)",
                    "does not invent a 'pricing owner' role the org chart lacks"]},
    {"id": "q1-revenue",
     "prompt": "What was Q1 revenue, and how did it track to plan?",
     "expected_output": "SGD 14.2M vs a 16.0M plan (−11%); SEA −6%, Brasil −20/21%. Sourced to the Q1 results filing.",
     "assertions": ["gives 14.2M actual vs 16.0M plan",
                    "cites the q1-2026-results PDF (filing tier)",
                    "does not invent an MRR figure"]},
    {"id": "eu-churn-gap",
     "prompt": "What's churn for the EU segment?",
     "expected_output": "Abstains — no source covers it (corpus is SEA + Brasil) — and routes to the metric owner.",
     "assertions": ["confidence == abstain", "coverage_gaps is non-empty",
                    "escalate_to names the metric owner"]}
  ]
}
```

**Assertion families** (graded PASS/FAIL with quoted evidence): *correctness*, *attribution* (cited sources match), *conflict handling* (dissent surfaced + fresh chosen with a stated reason), *abstention* (a real gap returns a coverage gap, not a confabulation), and *escalation* (gap routed to the right owner). Mechanical ones — valid envelope, sources resolve, confidence enum — are code-checked; judgment ones use an LLM judge that must cite evidence for a PASS.

**Workspace** (produced by the runner, not authored):

```
evals/
├── evals.json                       # you author this
└── workspace/iteration-N/
    ├── <case-id>/
    │   ├── with_harness/     {outputs/, timing.json, grading.json}
    │   └── without_harness/  {outputs/, timing.json, grading.json}
    └── benchmark.json               # per-config pass_rate/time/tokens + delta
```

Each case runs in a **fresh process / clean state** (no leftover context between cases), so an answer reflects only the harness; `timing.json` (`total_tokens`, `duration_ms`) is measured by the runner around each call (token usage from the API response). `benchmark.json` reports `with_harness` vs `without_harness` and the **`delta.pass_rate`** — the number that proves the harness earns its cost. `evals.yml` runs `make eval` headless and gates on the with-harness pass rate *and* `delta.pass_rate > 0`; a `mode != live` or `answer_path != ontology` graded answer fails the run (see VALIDATION preconditions).

> **The audit is the engine, not a manual pre-step.** The input could be any company's document set, so surfacing contradictions, resolving aliases, and detecting stale-vs-fresh facts is what the extraction engine *does* — a product capability, generalizable, not a one-time human read of HelixPay. We author the gold set by spot-checking the engine's first-pass output (its flagged conflicts and resolved entities), then grade the engine against it. The human job is defining "good"; finding the quirks is the engine's job.

## 3. Functional requirements (derived from the evals)

The eval classes dictate the build: an **assertion-centric ontology** (every fact a sourced, dated, scoped `Assertion`; entities/targets/graph are views, §4.13), **adaptive ingestion** (profile → `PipelineConfig`, §4.0), **alias/entity resolution with anti-aliases** (`distinct_from`), a **temporal model** (as-of dates + supersedes), **contradiction detection** distinguished from **scope** (NPS-by-segment), **source-reliability weighting** (filing > board > … > chat), **idempotent versioned re-ingestion** (stable ids → upsert, not duplicate), **typed hierarchy** (dotted-line edges), **provenance** on every claim, a **context-strategy seam** (ontology-first default; raw whole-corpus / Hybrid as fallback, §4.5), **vision chart extraction** (provisional confidence), an **agent-facing interface** (token-authed live endpoint), the **House Harness extraction** (charter + targets + guardrails/authorities, alongside taxonomy) with a **harness-health check** (what's missing/off + quick-win actions + owners), and a **trust envelope** with **abstention + authority-routed escalation**. Two runtime guardrails ship with it: an **untrusted-content gate** at ingestion and **egress redaction**, plus **provider-leakage controls** (ZDR/no-train, data minimization, self-host model route, and no raw corpus in traces — LangSmith Cloud default, self-hosted `LANGSMITH_ENDPOINT` for sensitive corpora) (§4.8). Query-time runs under **reader/executor privilege separation** (reader sees untrusted input with no tools; executor runs only allowlisted closed-vocabulary requests — the typed boundary is the trust boundary, §4.10). Two compounding pieces close the gap between a snapshot and a system: a **feedback loop** (correction/escalation → source + gold case + re-extract, §4.11) and **offline entailment verification** (runtime is cite-or-abstain; the cited-span-supports-claim check runs in the eval harness, §4.12). Throughout, **typed-at-every-boundary contracts with structured LLM output** and **failure-isolated, degradation-aware** handling (§4.9). Nothing else is in scope.

---

## 3.5 v1 build scope (post-optimization)
The lean set we actually build in the 4–6h, after the cuts. Optionality is the cost, so seams are kept as types but their machinery is deferred.

**In v1 — the buildable core + the differentiators:**
- Ingest the real `data/` (md/html, PDF text, charts via vision, chat tagged low-reliability) → **per-doc structured extraction** into the `Assertion` model mapped onto the controlled **attribute namespace**.
- **Ontology** (`ontology.py`): idempotent `upsert` (stable ids), scope-aware `resolve` (conflict vs segment), `SourceTier` tie-breaks, alias/anti-alias seeded from in-doc disambiguation. **SQLite** store, no vector index (corpus ≈55K tokens).
- **Ontology-first** query path (answers from the resolved slice); raw whole-corpus is the in-budget fallback. Profiler is a constant for v1.
- **Reader/executor privilege split** (kept, not merged) + the caps chokepoint.
- **Trust envelope**: cite-or-abstain, dissent, freshness, scope, coverage-gap abstention, authority-routed escalation.
- **Interface**: MCP + HTTP `/ask` with token auth; live **Fly** deploy; **LangSmith** tracing.
- **Evals**: the verified gold + held-out sets and the uplift gate. Entailment, calibration, and alias precision/recall are scored **offline**, not at runtime.

**Deferred — kept as types/seams, named in §8 + SOLUTION:**
- Hybrid retrieval + pgvector (scale path behind the `ContextProvider` seam); the profiler as a *runtime* branch (constant in v1).
- Harness-health beyond the deterministic stub; feedback-loop auto-re-extract; vision precision tooling; calibration/entailment as a *runtime* pass; full multilingual; exhaustive ontology.
- Physical pod isolation (reader/executor are logically split in v1; separate containers/network at deploy).

---

## 4. Architecture

### 4.0 Adaptive ingestion — profile, then plan
Step zero reads the corpus and picks the architecture for it, because the input could be any company's documents. A **profiler** measures volume (token estimate), format mix, entity/cross-reference density, temporal spread, and language → a typed `CorpusProfile`. A **planner** maps that to a typed `PipelineConfig` — context strategy (§4.5), vision extraction on/off, graph on/off, reranker on/off — via an **explicit rule table, not an LLM**: the decisions are few and measurable, so deterministic thresholds are the right tool, they're testable, and the `rationale` string explains the choice for a human to audit. It chooses from a *fixed menu of known-good shapes*; it never invents one. Keep it small — a profiler and a lookup.

**Measured for HelixPay (2026-06-07): the text corpus is ≈54.5K tokens** (md+html) + 2 PDFs + 4 charts — well under the 120K budget. So the planner's output is a **constant for v1: `ontology_first + vision + graph`** (raw whole-corpus is the in-budget fallback), and we build that path directly (no vector index, SQLite store). `CorpusProfile`/`PipelineConfig` stay as types + the documented rule so the moving-target case (corpus outgrows budget → Hybrid) is a config flip, not a rewrite — but the profiler is not a runtime branch in v1.

### 4.1 Ingestion-time vs query-time (state the call) — ingestion-heavy, ontology-first query
Do the heavy lifting at **ingestion**: parse and normalize every format, resolve entities/aliases, build the taxonomy + ontology graph, distill the harness (charter, targets, guardrails/authorities), and — crucially — **resolve every fact once** (staleness, conflict-vs-scope, source-tier, hierarchy) into the assertion store. **Query-time is then ontology-first and cheap:** resolve the question to its `(subject, attribute, scope)` → read the matching live assertions (values + dissent + as-of + sources) from the store → reason over that small structured slice → cite. The deep, graded questions are answered from precomputed structure, *not* by re-reading raw text — which is why they stay correct (a model over the raw corpus silently picks one value, misses a supersession, merges two Marias). Per-query cost is O(slice), so it stays flat as a live corpus grows. Raw whole-corpus reasoning is the **fallback** for questions outside the controlled namespace (§4.5). The moving-target case reduces to re-running ingestion on changed files (idempotent `upsert`; incremental later is a small change, not a rewrite).

### 4.2 The House Harness (the product)
Ingestion emits the owned artifacts: the **ontology graph** (`graph.json`), the **`HELIXPAY.md`** House Harness file, and the **dense+sparse indexes**. The harness is a curated library of artifacts that define the company — distilled, not dumped:

| Defining artifact | What it captures | Status |
|---|---|---|
| Context / retrieval | corpus + ontology | **build** |
| Taxonomy | entities, relations, glossary, aliases, as-of dates | **build** |
| Charter | mission + operating principles | **build** |
| Evals | company KPIs, targets, definitions of "good" | **build** |
| Guardrails | policies, decisions, constraints, approval authorities | **build** |
| Trust / provenance | the trust envelope (§4.4) | **build** |
| Capabilities | org systems + action surface | defer → §8 Arc A·#3 |
| Decision workflows | escalation + approval flows | defer → §8 Arc A·#4 |
| Audit | the company's decision log | defer → §8 Arc B·#6 |
| Learning loop | how the company updates itself | defer → §8 Arc B·#7 |

These owned artifacts are the edge; the model and framework underneath are rented and swappable.

**Harness health — what's missing / off, and the quick win.** Right after extraction, a deterministic check compares the populated harness against its expected shape and the conflict/staleness signals already computed, and emits a `HarnessHealth`: a completeness score plus a prioritized list of `HarnessGap`s, each with a severity, a templated quick-win action, and an owner pulled from the harness authorities. It catches missing or thin sections, unowned targets/guardrails, unresolved conflicts (no source of record), stale facts, coverage gaps, and orphans (referenced-but-undefined entities). This is the mirror the company reads: *here's what the system sees about you, and the five quick things to fix to level up.* Detection is rule-based (testable, no LLM opinion); the action copy is a template per gap-kind. It upgrades the blind-spots map (§8 #1) into something actionable, and reuses signals the pipeline already produces — so it's nearly free.

### 4.3 Decision-engine behavior (scoped)
Because the House Harness carries guardrails and targets, the agent can answer *within* them — e.g. "can we offer customer Z a 40% discount?" → applies the pricing guardrail, names the approval authority, flags the relevant target. **Demonstrate on 1–2 queries only**; do *not* generalize to arbitrary rule-application (that's the time/correctness sink, sharper still for a payments company). The trust envelope (§4.4) is the guardrail *on* this behavior — a rule-applier that can't say "no source" is dangerous.

### 4.4 The trust envelope (every answer)
This is a return-shape decision, not new machinery — it surfaces what the pipeline already computes (sources, as-of dates, detected dissent), plus one new signal: **coverage gaps** via abstention. Every answer returns:

```json
{
  "answer": "…",
  "claims": [{"text": "…", "sources": ["interview-07#L40"], "as_of": "2026-04-21", "verified": null}],
  "freshness": "newest supporting source: 2026-04-21",
  "dissent": [{"point": "…", "sources_disagree": ["board-deck", "weekly-review"]}],
  "coverage_gaps": ["no source addresses churn for the EU segment"],
  "escalate_to": [{"gap": "EU churn", "owner": "Dana Levin", "evidence": ["org-chart", "interview-12"]}],
  "confidence": "high|medium|low|abstain"
}
```

Two mechanics, both reusing pieces we already build:
- **Abstention** — if the resolved ontology has no in-scope coverage for the question (or, on the raw fallback, retrieval falls below a confidence threshold) *or* the offline judge can't ground a claim, emit a coverage gap and lower confidence rather than confabulate. Coverage — not retrieval similarity — is the primary signal; a cite-or-abstain rule backs it.
- **Authority-routed escalation** — when there's a gap or low confidence, join it to the owning authority already in the harness and return `escalate_to`. This is a few lines wiring two existing signals (gaps + authorities), and it's the line between "search box that admits ignorance" and "decision-engine that knows who holds the answer." An agent that hits a wall routes instead of stalling.
- **Entailment (offline, §4.12)** — at runtime the guarantee is cite-or-abstain (no claim without a non-empty cited span); whether the span actually *supports* the claim is measured offline over the gold set, not on every query. `verified` is set by the eval harness, not at runtime — grounded is not correct, but verifying it per-query is the wrong place to pay for it.

### 4.5 Context strategy — ontology-first default; raw whole-corpus + Hybrid as fallback
The default query path does **not** assemble raw context at all: it answers from the resolved ontology slice (`ontology.query`, `ContextStrategy.ontology_first`). The `ContextProvider` seam is the **fallback** for out-of-ontology questions, and it's what scales — a config flip, not a rewrite.

- **Call graph (encoded in `synthesis/respond.py`, not just prose):** `answer(query)` → `resolve_question` → `ontology.query(subject, attribute, scope)` → `claims_from_assertions` (stamps every claim with its `assertion_id`) → `build_envelope(answer_path=ontology)`; raw retrieval is reached only inside `_fallback`, never as the default. The envelope's `answer_path` + per-claim `assertion_id` are the tripwires the eval grades on.
- **Ontology-first (default, the whole point).** `ontology.query(subject, attribute, scope)` returns the live resolved assertions for the question — already deconflicted, dated, scoped, and sourced — and synthesis builds `Claim`s directly off them. Staleness/conflict/alias/hierarchy were decided once at ingest, deterministically; query-time just reads them. Coverage is the abstain signal: an in-scope question with no covering assertion is an honest gap (abstain + escalate), never a reason to fall back and guess. Cost is O(slice), flat as the corpus grows. Assertions live in a local **SQLite** store; **no Postgres, no vector index** for v1.
- **WholeCorpus (fallback, in-budget).** For questions whose `(subject, attribute)` fall outside the controlled namespace, load the raw documents into context (the snapshot is ≈55K tokens). Deliberately *not* the default: fitting the budget is a capacity fact, not a correctness one — a model over 55K tokens of contradictory text reproduces the exact failures the ontology prevents, so this path caps envelope confidence lower and tags chart/low-tier facts provisional.
- **Hybrid (fallback, at scale).** When the corpus exceeds the context budget, the fallback switches to dense (pgvector) + sparse (FTS/BM25) + graph, fused with RRF, reranked, recency-weighted; for contradiction questions it retrieves all variants of a fact. Built behind the interface, enabled by the planner — the scale-out arc, not the snapshot build.

v1's owned store is **SQLite** (artifacts, assertions, harness, graph) — no Postgres, no vector index. Postgres/pgvector appears only on the scale-out path (the `scale` extra), swapping the store layer behind the same interface; nothing above it changes.

### 4.6 Interface
- **MCP server** — the primary, agent-native surface (Codos's keystone; "the consumer is an AI agent"). Exposes `ask_company`, `get_entity`, `get_harness`, and `get_harness_health` (the missing/off gaps + quick wins) tools. `ask_company` returns the full trust envelope (§4.4), not a bare string — that return shape is what makes it agent-native.
- **Thin HTTP** — `/ask` (so it's curl-demoable) and `/health` (so `install.sh` can gate on it).

### 4.7 Swappable stack (Operating Map)
Model behind a single `config/llm.py` seam (provider = config). Tracing via **LangSmith** (LangChain family), behind `obs/` (backend stays swappable; self-hostable for sensitive corpora). Secrets/env injected via **Doppler** (§5). Everything containerized. The harness, ontology, and eval set are owned; the rest is rented.

### 4.8 Security: runtime gates & provider-leakage controls
Gates, framed as the guardrails artifact *enforced live*:
- **Untrusted-content gate at ingestion** — every ingested document is data, never instructions; a sanitization step neutralizes embedded directives. Real prompt-injection surface, not theater.
- **Egress redaction** — a PII/secret pass before content goes to the model and before it leaves the MCP. A backstop, not a control.

Provider-leakage controls (this is a payments corpus — financials, customer PII, board material all transit the model API):
- **ZDR / no-train** — the provider account must be zero-data-retention / no-training. The primary, near-free control; `config/llm.py` carries a `REQUIRE_ZDR` reminder flag.
- **Data minimization** — send sourced spans, not whole documents; strip metadata not needed to answer.
- **Self-host / VPC route** — for sensitive deployments, point the model seam at an in-boundary model; the swappable stack makes this a config change.
- **Trace containment** — LangSmith holds the same sensitive prompts/answers. LangSmith Cloud is the default; for sensitive corpora point `LANGSMITH_ENDPOINT` at a self-hosted/VPC instance and send minimal sourced spans — the same swappable route as the model seam, so tracing isn't a second leak.

Full DLP, per-query access control, and encryption policy are deferred (§8).

### 4.9 Failure handling & data contracts
The structured contract *is* the failure boundary: every value crossing a stage is a validated Pydantic model, and the act of validating it is where failures get caught. Cheapest-first, all reusing pieces the build already has:

1. **Degradation-aware envelope** — `status` (answered / abstained / degraded / failed) + `errors` separate "no source covers this" (agent escalates or fetches) from "the system couldn't complete" (agent retries or alerts). One field set on the envelope we already ship; the agent routes the two completely differently.
2. **Per-file ingestion isolation** — a malformed PDF / bad encoding / unknown format becomes an `IngestFailure` (and an honest coverage gap), never a crashed batch. A try/except in `load_corpus`. The corpus is adversarial by design, so this is guaranteed to fire.
3. **Typed boundaries** — `RetrievedChunk` and the rest; no raw dicts or prose between stages, JSON only at the process/MCP/HTTP edge. Enforced by pyright + Greptile.
4. **Structured LLM output, validated + repaired** — `config/structured.py::llm_json` binds each stage-feeding call to a schema, repairs once on a validation error, retries bounded, then marks the unit degraded. Closes the most common LLM failure mode.
5. **Caps** — step cap, per-call timeout, cost-per-run cap in config, enforced in the agent wrapper.

### 4.10 Privilege separation — reader & executor pods
Injection defense by structure, not by hoping the gate caught everything. The query-time agents split into two components with different privileges, and the **typed boundary is the trust boundary**. (We deliberately keep the split for v1 rather than collapsing to one agent — it's a genuine differentiator and the boundary is cheap when it's just two typed functions.)

- **Reader pod** (`agents/reader.py`) — the *only* component that sees untrusted input (query + retrieved content). **No tools, no execution.** Bound to structured output, it emits a `ReaderOutput`: an answer draft plus typed, allowlisted `PlanRequest`s. The most an injection can produce is a bad draft or a request the executor rejects.
- **Executor pod** (`agents/executor.py`) — privileged, but **never sees raw untrusted text**. It consumes the reader's typed requests, validates each against the closed `RequestKind` vocabulary (`retrieve`, `escalate`) and an ontology allowlist (`executor.validate`), rejecting anything URL/host/shell-shaped, then executes only the validated requests and assembles the envelope.

`executor.validate` is a pure, unit-testable function, so the security property is a test, not a hope. In deployment the two run as separate processes/containers (reader gets no outbound network beyond the model API; executor gets scoped allowlisted access) — but the typed boundary is the trust boundary regardless of co-location, so v1 keeps the split logically and physical isolation is a deploy-time setting, not a rewrite.

### 4.11 Feedback loop — closing the open loop
The system senses what it doesn't know (coverage gaps, escalations, dissent, harness-health gaps) — this is the loop that lets it *learn* from that, so it compounds instead of staying a snapshot. When an escalation is resolved or a user corrects an answer, that `Feedback` becomes three things (`pipeline/feedback.py`): (1) a new **sourced `Artifact`** — the correction enters the corpus, attributed to whoever resolved it, superseding the sources it overrides; (2) a new **gold eval case** — the system is now held to the corrected answer; (3) a **re-extract trigger** — the next ingestion run reconciles it into the harness. The cheap closed version is built (capture + queue, consumed on the next ingest run); full auto re-extract on capture rides incremental ingestion (§8 #2). This is the one loop worth closing first: it turns escalations from a dead end into the mechanism that fills the harness's own blind spots.

### 4.12 Correctness verification — grounded is not correct (offline)
Cite-or-abstain proves a claim isn't invented; it doesn't prove the cited span *supports* it. But a second LLM call per claim per query is the biggest hidden cost multiplier in the system and a poor runtime trade, so v1 splits it by where it runs:

- **Runtime (hot path): cite-or-abstain only.** Every claim carries a non-empty cited span or the answer abstains (§4.4). `Claim.verified` stays `None` at runtime — we don't pretend a per-claim entailment check ran.
- **Offline (eval harness): the entailment judge** (`synthesis/verify.py`) runs over the gold set, checking each cited span actually supports its claim, and reports an entailment score. That's where "grounded ≠ correct" is *measured* and regressions are caught — in batch, not on every user query.

Companion measures also live in the eval suite, not in runtime machinery: **confidence calibration** against the gold set, and **direct extraction evals** — especially **alias-resolution precision/recall**, the silent-corruption risk. Promote entailment to a runtime pass later only for high-stakes answers, behind a flag. The honest framing holds: the system optimizes for *grounded, consistent, and verified-against-source-offline*, and surfaces uncertainty — not for an unobtainable runtime ground truth.

### 4.13 The ontology: sourced, dated, scoped assertions (the spine)
"An ontology, not a search engine" is the core ask, and the elegant representation that wins four of the five planted traps at once is to model every fact as a **timestamped, sourced, scoped `Assertion`** rather than a settled value (`pipeline/ontology.py`). Entities, the graph, and targets are *views* over assertions; conflicts are first-class, never collapsed.

- **Staleness** — each assertion carries `as_of`; a fresher/higher-reliability assertion supersedes the prior (`supersedes`, `live=False`). "When does Confluence launch?" → Sep 30, with the June all-hands line shown as the superseded public position.
- **Contradiction vs scope** — assertions group by `(subject, attribute, scope)`. Same scope, differing values → a real conflict: keep the highest `(reliability, recency)` as current **and** emit `Dissent`. *Different* scope → both true, no conflict: NPS@SEA-enterprise=62 and NPS@aggregate=47 are returned with their segments, not flagged as a disagreement.
- **Source reliability** — every assertion has a `SourceTier` (filing > board > official > interview > chat). A board email outweighs a Slack joke; the F1 chatter never becomes a fact. Tier feeds both conflict tie-breaks and confidence. It's a deterministic lookup (`ontology.RELIABILITY`), not an LLM judgment.
- **Attribution** — `source` (a `SourceSpan`) on every assertion; this is what makes cite-or-abstain (§4.4) and entailment verification (§4.12) possible.
- **Aliases & anti-aliases** — `Alias(canonical, aliases, distinct_from)`. `distinct_from` is load-bearing: it actively keeps Maria Santos ≠ Maria Silva and POS Self-Service ≠ POS, so resolution can't silently over-merge.
- **Typed hierarchy** — `GraphEdge.relation` is a `RelationKind` enum incl. `dotted_reports_to`, so matrix/dotted-line org questions ("who dotted-lines into Sofia?") are answerable, and the stale org chart is superseded by the Apr-18 reorg like any other fact.
- **Idempotent re-ingestion (the moving target)** — assertion `id` is a stable hash of `(subject, attribute, scope, source)`, so re-importing a changed file **upserts**: same fact re-derived → same id (no duplicate); a new weekly-review's Confluence date supersedes the old assertion and keeps it as history. This is the evaluator's "show me you update without double-counting" test, handled by construction.

### 4.14 Extraction & resolution — the make-or-break step
The whole system rests on the LLM reliably emitting well-formed `Assertion`s from messy multi-format docs. This is the highest-variance step, so it gets a real design, not a one-liner:

- **Controlled attribute namespace** (`pipeline/attributes.py`, derived from the real corpus). The extractor must map every fact onto a canonical `attribute` key (`revenue.quarter_actual`, `nps`, `confluence.ga_date`, `crm.system_of_record`, …) or emit `new_attribute:<slug>` for review. This is what makes `resolve()`'s grouping by `(subject, attribute, scope)` fire — without it "MRR"/"recurring revenue"/"rev" become three non-conflicting assertions and contradiction detection silently fails.
- **Structured extraction, per document.** Each doc → `llm_json` (validate + repair) emitting assertions with `subject, attribute, value, scope, as_of, source span, reliability`. Documents fit individually, so chunk only the few that don't; one pass per doc keeps spans accurate.
- **`as_of` provenance rule.** Distinguish the *stated date* (when the doc was written) from the *referenced date* (when the fact is true-as-of). The weekly-review states "April MTD" on Apr 21 but references Q1 figures; the assertion's `as_of` is the referenced date, which supersession compares; stated-date breaks ties.
- **Alias algorithm — precision-first.** Candidate-generate by normalized-name + embedding similarity; adjudicate with the LLM on context. Crucially, **seed `distinct_from` from the corpus's own disambiguation**: the org chart literally says "Maria Santos and Maria Silva are different people" and "Tan Wei Ming … not related to Daniel Tan." Mining those explicit statements gets most of the ≥0.95 precision (over-merge = silent corruption) without a clustering model.
- **Source reliability at extraction.** Tag each assertion's `SourceTier` from the document type (`ontology.RELIABILITY`), so the all-hands stage claim ("78% in HubSpot", "Q3 not on the table") is outranked by the board email and weekly review at resolution time.

---

## 5. Packaging & platform fit (constraint 1)

- **One command from a fresh clone:** `./install.sh` → `docker compose up` brings up app (SQLite store; LangSmith tracing via env), ingests `data/` on boot, health-checks, prints the agent endpoint.
- **Secrets via Doppler:** env is injected at runtime with `doppler run --` (no secrets on disk) for dev and the live deploy; `install.sh` uses Doppler when a token is present and falls back to `.env.example` so a fresh-clone local run still works without a Doppler account. The live deploy reads its config from a Doppler project, not a committed file.
- **AI-native convention:** `AGENTS.md` (with `CLAUDE.md` pointing to it) and the generated `HELIXPAY.md` sit at the repo root; the **MCP server** is the primary agent surface. Development follows the AGENTS/PLAN/PROGRESS/VERIFY external-memory flow.
- **Live in production, not local:** an explicit pass/fail — a localhost demo fails it. Deploy to a real host (`fly.toml` provided: Fly.io app, SQLite store (pgvector only on the Hybrid scale path)) and put the URL in `SOLUTION.md`. The endpoint requires a **bearer token** (`HOUSE_HARNESS_API_TOKEN`, `serve/app.py:require_token`); `/health` stays open for probes. Note **cold-start** behavior (scale-to-zero) in `SOLUTION.md`. The zip is the code; the URL is the proof.
- **Zip:** `make package` (git archive — committed files only, no venv/cache/secrets); `make verify` extracts clean and runs `install.sh`, so a broken zip can't ship.

## 6. Review & CI (constraint 3: Greptile)

- **Greptile** = the automated PR reviewer. Connect the GitHub app to the repo; it indexes the whole repo into a code graph and posts context-aware reviews on every PR (v4, built on the Claude Agent SDK). Pleasing symmetry: its repo-graph mirrors our company-ontology graph.
- **`greptile.json`** at root encodes our conventions as custom rules (provider isolation, untrusted-content-is-data, provenance-required, evals-for-new-behavior, no secrets). See the file in this repo.
- **`cto` Claude Code subagent** stays for architecture/scope and milestone acceptance against the DoD. Division of labor: CTO plans and accepts; Greptile reviews the diffs.
- **CI:** `ci.yml` (ruff + pyright + pytest) and `evals.yml` (structural/provenance must pass; correctness/conflict gated). Greptile runs as the PR-native reviewer alongside.

## 7. The 4–6 hour schedule

| Time | Work |
|---|---|
| 0:00–0:30 | Define the House Harness schema + the question/eval classes. Skim a few docs only to calibrate — the engine, not a manual pass, is what surfaces conflicts/aliases/staleness. |
| 0:30–1:00 | Seed the gold cases (13 committed in `evals/evals.json`, spanning every trap class incl. abstention + entity hygiene; held-out set locked separately); refine wording against the engine's first-pass output. |
| 1:00–1:30 | Scaffold (reuse: `AGENTS.md`/`CLAUDE.md`, the PLAN/PROGRESS/VERIFY flow, compose, `install.sh`, schema, `greptile.json`, Doppler config). |
| 1:30–2:30 | Ingestion: **profiler → `PipelineConfig`**, then loaders (md/pdf/html/chat/email + **vision for charts**) → **untrusted-content gate** → normalized `Artifact` with source + as-of date. (Whole-corpus mode for HelixPay — index only if over budget.) |
| 2:30–3:30 | **The extraction engine (automated audit):** entity/alias resolution, contradiction + staleness detection → taxonomy + ontology graph; distill charter + targets + guardrails/authorities; emit `HELIXPAY.md` + `graph.json`; run the **harness-health check** (missing/off + quick wins). |
| 3:30–5:00 | ontology-first answering (reader/executor over the resolved slice; raw docs only as fallback); graph for hierarchy; contradiction surfacing; **trust envelope** (cite-or-abstain, freshness + dissent + coverage-gap abstention + authority-routed escalation; entailment scored offline); **egress redaction**; 1–2 decision-engine answers; MCP + `/ask`. |
| 5:00–6:00 | Run evals; wire Greptile; `make verify`; deploy live; write `SOLUTION.md`; (optional) 2–5 min video. |

## 8. Deferred roadmap — ranked by asymmetric value, grouped into arcs

Ordered most-asymmetric first. Items that form a single build-unit are grouped into an **arc** and taken together when built, even though their individual asymmetric values differ — an arc sits at the rank of its entry point. Name each in `SOLUTION.md` with its *why*.

**Standalone next bets** — highest asymmetric, each shippable alone, each reuses signals the build already produces:

1. **Blind-spots map → now delivered as Harness Health (§4.2, in scope).** The static "what's missing / off + quick wins" mirror is built. What remains deferred: tracking it *over time* — does completeness improve as they fill gaps? — which rides the moving-target loop (#2).
2. **Live incremental ingestion + harness diff** — *idempotent versioned re-ingest is now in scope* (stable assertion ids → upsert/supersede, §4.13), so re-running on changed files updates without double-counting. What remains deferred: a **file watcher** (auto-trigger) and a **harness diff** ("what changed since last import"). *Value:* high. *Cost:* low (ingestion is isolated and idempotent). *Defer because:* a single snapshot can't demo the watcher.

**Arc A — The action/decision layer** (build 3→4→5 as a unit; this is where the House Harness stops describing the company and starts governing what agents may do):

3. **Tools / capabilities registry (action-surface)** — model the company's systems and who may act in them. *Value:* high — the bridge from description to governance. *Cost:* medium (partial data). **The arc's entry point and the named next element.**
4. **Decision workflows / approval orchestration** — escalation paths and approval flows beyond who-owns-what. *Value:* medium–high. *Cost:* medium. *Depends on #3.*
5. **General decision-engine behavior** — apply guardrails + targets to arbitrary situations, not just the 1–2 demo queries. *Value:* high (the ultimate product). *Cost:* high + correctness/safety risk, acute for payments. *Depends on #3–#4, with the trust envelope as its guardrail.*

**Arc B — The compounding loop** (build 6→7 as a unit; turns the live system into a moat that improves with use):

6. **Tracing → company audit log** — surface LangSmith answer/decision traces as an auditable decision trail. *Value:* medium (trust/ops; the loop's foundation). *Cost:* low (LangSmith already wired). *Defer because:* inert on a static snapshot.
7. **Feedback / learning loop → capture loop now in scope (§4.11).** The closed loop is built at its cheapest: a correction/escalation becomes a sourced artifact + a gold case + a re-extract trigger, consumed on the next ingest run. What remains deferred: *automatic* re-extract on capture (rides incremental ingestion, #2) and longitudinal learning analytics. *This is the moat that compounds.*

**Polish & edge** — opportunistic, lower asymmetric value:

8. **Trained cross-encoder reranker** — precision/latency at scale; the LLM reranker captures most of the gain now.
9. **Higher-precision chart digitization (WebPlotDigitizer)** — vision-LLM chart extraction is now *in scope* (§4.0/§4.5). WPD was considered for higher numeric precision but rejected for the automated path: it needs per-chart axis calibration, its auto mode assumes clean scientific plots, the fully-automatic version is closed/paid, and the free frontend is AGPL. Kept only as a manual precision-verification fallback for a single critical chart.
10. **Full multilingual normalization** — detection covers the graded cases; translate-normalize later.
11. **Exhaustive ontology** — cover only the entity/relation types the questions need.

## 9. Repo delta from the scaffold

Add: `src/house_harness/ingest/` (multi-format loaders + failure-isolated `load_corpus` + `load_image` vision extraction + **untrusted-content gate**), `pipeline/profiler.py` (corpus profile → `PipelineConfig` via a deterministic rule table), `pipeline/harness.py` (the extraction engine → assertions → taxonomy + charter + targets + guardrails/authorities → `HELIXPAY.md`), `pipeline/ontology.py` (the spine: stable assertion ids, `RELIABILITY` table, idempotent `upsert`, scope-aware `resolve` → current view + `Dissent`), `pipeline/attributes.py` (the controlled attribute namespace derived from the corpus — the extractor maps into it), `pipeline/health.py` (deterministic harness-health check → `HarnessHealth`: missing/off gaps + quick-win actions + owners), `pipeline/ontology.py::query` (the **primary** query-time read — ontology-first), `retrieval/strategy.py` (the `ContextProvider` **fallback** seam: raw `WholeCorpus` in-budget + `Hybrid` at scale) and `retrieval/hybrid.py` (the scale impl), `synthesis/envelope.py` (trust envelope: abstention + authority-routed escalation + degradation status), `synthesis/verify.py` (OFFLINE entailment judge over the gold set — not a runtime pass), `pipeline/feedback.py` (the closed loop: `Feedback` → sourced artifact + gold case + re-extract trigger), `config/structured.py` (`llm_json`: structured output + validate + repair), `agents/runner.py` (the caps chokepoint), `agents/reader.py` + `agents/executor.py` (the reader/executor privilege split: structured-output read with no tools → allowlist `validate` → execute; pods physically separated at deploy), `guards/redact.py` (egress PII/secret redaction), `serve/` (MCP + HTTP, `ask_company` returns the envelope), `obs/` (LangSmith tracing), `evals/evals.json` + `evals/workspace/`, `greptile.json`, `doppler.yaml`, `SOLUTION.md`. Extend `schema.py` with the House Harness, trust-envelope (`status`/`errors`), `RetrievedChunk`, `IngestFailure`, the agent boundary types (`ReaderOutput`, `PlanRequest`, `RequestKind`), and the adaptive-ingestion types (`CorpusProfile`, `PipelineConfig`, `ContextStrategy`), and the harness-health types (`HarnessHealth`, `HarnessGap`, `GapKind`), `Feedback` and the `verified` flag on `Claim`, plus the ontology spine (`Assertion`, `SourceTier`, `Alias`, `RelationKind`, and `scope` on `Claim`). Add `fly.toml` (live deploy) and token auth in `serve/app.py`. Reuse everything else as-is.
