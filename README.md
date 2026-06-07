# House Harness Engine

AI development has moved from *context management* — assembling the right text into a prompt — to *harness management*: the durable set of artifacts (instructions, tools, evals, guardrails) that defines how an agent operates. The same shift is coming to companies. A **company harness** is the organizational equivalent: a compact, living set of artifacts — taxonomy, charter, rules, playbooks, owners, resolved aliases, sourced facts — that holds the essence of the company, so an agent (or a person) can operate it without reading everything. This engine builds that harness from a company's messy documents.

A company-definition engine. Ingests a messy document corpus and emits a **House
Harness** — `<COMPANY>.md` plus a queryable ontology — that an agent operates a
company through: resolved aliases, as-of dates, contradictions surfaced,
guardrails + authorities, every claim sourced and entailment-checked.

**Status:** scaffold + plan. Typed contracts, conventions, packaging, and the
eval spine are complete; model-touching logic is stubbed (`NotImplementedError`).
It compiles and imports; it is not yet a running system. Build order in
[`PLAN.md`](./PLAN.md) (design rationale in [`BUILD_PLAN_HELIXPAY.md`](./BUILD_PLAN_HELIXPAY.md));
submission narrative in [`SOLUTION.md`](./SOLUTION.md).

**Stack:** built on **LangChain 1.0** (`create_agent` + `init_chat_model`, LangGraph for any
orchestration) with **LangSmith** for tracing and eval runs — model and tracing backends both
sit behind seams (`config/llm.py`, `obs/`) and are swappable config. See `AGENTS.md` for the rules.

**Built with an external-memory flow** so the work survives sessions and context
compaction — [`AGENTS.md`](./AGENTS.md) (norms), [`PLAN.md`](./PLAN.md) (checklist + DoD),
[`PROGRESS.md`](./PROGRESS.md) (running log), [`VERIFY.md`](./VERIFY.md) (commands that
prove it works). The loop is in `AGENTS.md` → "Development flow". (`CLAUDE.md` points there.)

**New here (dev team)? Start at [`HANDOFF.md`](./HANDOFF.md)** — 60-second orientation, run steps, build order, and the parallel-track ownership map.

## Quickstart

**Install with Claude Code (one prompt):**
> Clone this repo (`github.com/teionarr/cds-house-harness` — the HelixPay `data/` is vendored in, no runtime fetch), read CLAUDE.md and AGENTS.md, run `./install.sh`, fill any missing secrets from `.env.example` (only `ANTHROPIC_API_KEY` is required; LangSmith optional, tracing auto-off without a key), wait for `/health`, then print the agent endpoint and (if tracing is on) the LangSmith trace URL and run the demo queries in SOLUTION.md.

**Or from a fresh clone:**
```bash
cp .env.example .env    # add ANTHROPIC_API_KEY + HOUSE_HARNESS_API_TOKEN
./install.sh            # docker compose up (app + SQLite store; LangSmith tracing via env), ingest data/, health-check
make eval               # with/without-harness uplift gate
```

Observability is on from the first run: every query is traced in **LangSmith** (`smith.langchain.com`) — ingest → retrieve → extract → synthesize → verify → caps/cost. Live deploy + submission flow: see `SUBMISSION.md`.

## Layout
```
AGENTS.md PLAN.md PROGRESS.md VERIFY.md   # external-memory dev flow (CLAUDE.md -> AGENTS.md)
VALIDATION.md                             # post-build acceptance gate (make validate)
src/house_harness/
  schema.py            # all typed contracts (34: 24 models + 10 enums) — the boundary discipline
  config/              # llm.py (model seam, ZDR), structured.py (llm_json: validate+repair)
  ingest/              # loaders (+vision charts), gate (untrusted-content)
  pipeline/            # profiler (corpus->config rule table), harness (extraction),
                       #   health (missing/off + quick wins), feedback (closed loop)
  pipeline/ontology.py # query() = primary answer source (ontology-first)
  retrieval/           # FALLBACK seam for out-of-ontology Qs (raw WholeCorpus | Hybrid)
  synthesis/           # envelope (trust envelope), verify (claim entailment)
  agents/              # reader (untrusted, no tools) / executor (privileged, allowlist) / runner (caps)
  guards/redact.py     # egress PII/secret redaction
  obs/tracing.py       # LangSmith (LangChain family)
  serve/               # MCP (primary) + thin HTTP /ask /health
evals/                 # evals.json (seed) + workspace/ (with/without-harness uplift)
```

---

## 1. Implemented
- **Typed contracts** — `schema.py`, 24 Pydantic models + 10 enums, imports clean. The trust
  envelope, House Harness, harness-health, adaptive-ingestion, reader/executor
  boundary, feedback, and `Claim.verified` all live here.
- **Deterministic rule tables (real logic, not stubs)** — `pipeline.profiler.plan_pipeline`
  (corpus profile → `PipelineConfig` from a fixed menu), `pipeline.health.ACTIONS`
  (gap-kind → quick-win), `EXPECTED_SECTIONS`.
- **Conventions & gates** — `CLAUDE.md` (standing rules: determinism, grounded≠correct,
  close-the-loop, typed boundaries), `greptile.json` (PR review), `doppler.yaml` (secrets).
- **Packaging** — `install.sh`, `docker-compose.yml` (app + SQLite; LangSmith tracing), `Makefile`
  (`package`/`verify`/`eval`), `pyproject.toml`.
- **Eval spine** — `evals/evals.json` seeded across question classes; uplift
  (`with_harness` vs `without_harness`) as headline metric + the gate.
- **Corpus-grounded artifacts (Phase 0 done)** — `PHASE_0_CORPUS_VALIDATION.md` (passed),
  `pipeline/attributes.py` (controlled vocab), `pipeline/aliases.py` (9 anti-alias pairs +
  3 non-person identities), `synthesis/_mock.py` (frozen envelope for parallel build), and
  `tests/fixtures/` (`assertions_resolve.json` resolve mechanics + `extraction_golden.json`
  prompt regression).
- **Module scaffold** — every component present with full signatures + docstrings
  stating the contract and the TODO. 15 files raise `NotImplementedError` by design.

## 2. Deferred / undone
- **All model-touching logic** — extraction, retrieval, synthesis, verification,
  vision: stubs. The plan fixes the *interfaces* and *order*; the bodies are the build.
- **Automatic re-extract on feedback capture** — capture is built; auto re-extract
  rides incremental ingestion (roadmap §8 #2).
- **Hybrid retrieval body** — seam + default (`WholeCorpus`) defined; the dense+sparse
  +graph+rerank impl is the scale path, behind the interface.
- **Roadmap arcs (§8)** — action-surface, decision workflows, tracing/audit,
  longitudinal harness-health trend, trained reranker, full multilingual.
- **Confidence calibration** — gold set is seeded + verified against the real corpus (Phase 0); final calibration of the confidence scores rides the build (Phase 5).

## 3. Commands run + exit codes
```
python -m compileall -q src                              # 0
python -m json.tool evals/evals.json                     # 0
python -m json.tool greptile.json                        # 0
python -c "import yaml; yaml.safe_load(open('doppler.yaml'))"        # 0
python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"  # 0
PYTHONPATH=src python -c "import house_harness.schema"      # 0  (34 typed contracts; requires pydantic)
shellcheck install.sh                                    # 127 (linter absent in this env; not verified)
tar -czf house-harness.tar.gz house-harness                  # 0
```

## 4. Issues discovered & how handled
1. **Source corpus** — unreadable during initial (blind) authoring; since cloned and
   **exhaustively read** (all 24 interviews + chat/email/dashboards/PDFs). Phase 0 gate
   PASSED (`PHASE_0_CORPUS_VALIDATION.md`): traps verified, the fabricated `mrr` figure
   corrected to Q1 revenue, vocab/alias/source-tier artifacts committed. The engine stays
   corpus-agnostic regardless; the gold set is now grounded in verified facts.
2. **`import house_harness.schema` failed** (`ModuleNotFoundError: pydantic`) — expected
   in a bare env; `compileall` verifies syntax, import re-verified green after
   `pip install pydantic`. Deps are pinned in `pyproject.toml`.
3. **Chart precision (WebPlotDigitizer)** — evaluated, rejected: needs per-chart
   calibration, AGPL frontend, auto-mode is closed/paid. Vision-LLM extraction
   instead, with chart facts tagged low-confidence (text wins ties).
4. **PII proxy (Braince.io)** — evaluated, not adopted (paid beta); recommend a
   self-hosted Microsoft Presidio reversible anonymizer, with an on-prem model route
   as the true "never leaves their server."
5. **Self-review found two thesis-level gaps** — runtime was open-loop (sensing, no
   learning) and conflated *grounded* with *correct*. Handled by adding the feedback
   loop (§4.11), claim entailment verification (§4.12), and calibration + extraction
   eval classes (§2).
6. **Plan-edit renumber churn** — new sections appended (§4.0, §4.11, §4.12) instead
   of inserted, to keep cross-references stable.

## 5. Key insights
1. **The owned layer compounds; the plumbing depreciates.** Model swaps are a config
   line; the corpus, harness, evals, and taxonomy get *more* valuable with each model
   generation, while hybrid/rerank/chunk plumbing erodes as context grows. Right-size
   to the data, keep the model-replaceable parts thin and removable.
2. **Grounded is not correct.** A citation proves a claim wasn't invented, not that
   it's true; "confidence" derived from retrieval similarity is confidence in
   relevance, not in truth. Correctness lives in entailment verification, calibration,
   and direct extraction evals — especially alias resolution, the silent-corruption risk.
3. **Sensing without loops is half a system.** Coverage gaps, escalations, dissent,
   and harness-health are sensors; they only create value when resolutions feed back
   into sources + evals + re-extraction. A company harness that can't level *itself*
   up contradicts its own pitch.

---

## For the implementing agent
Start at [`HANDOFF.md`](./HANDOFF.md), then follow the external-memory loop (`AGENTS.md` → "Development flow"): read `PROGRESS.md`,
take the next unchecked item in `PLAN.md`, implement, run the matching block in
`VERIFY.md`, log to `PROGRESS.md`, check it off. The dependency-gated build order and
the definition of done live in `PLAN.md`. Keep deterministic components (profiler,
planner, health) as rule tables, never LLM oracles. Gate every item on evals
(`delta.pass_rate > 0`).
