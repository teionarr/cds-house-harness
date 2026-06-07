# SUBMISSION.md — internal playbook (not for examiners)

Clarity on exactly what we hand Codos and how the pieces fit. `SOLUTION.md` is the
doc examiners read; this file is for us.

## What the examiners actually receive
Three graded things + one optional:
1. **The zip** — emailed to gleb@codos.ai **and** dima@codos.ai. Built with `make package` (committed files only, no venv/cache/secrets).
2. **The live URL** — in `SOLUTION.md`. The README says it outright: *"Should be live in production — not local."* A localhost demo fails this. This is the only hard requirement we can't satisfy from the repo alone — it needs a deploy.
3. **`SOLUTION.md`** — their reading guide, with the four required sections: how to run (one command from fresh clone), tradeoffs, architecture justification, what you didn't tackle + why.
4. *(optional)* **2–5 min video** — the best vehicle to *show full functionality + observability* live. Welcome, not required.

## Install: one prompt for Claude
The repo is structured so a single Claude Code prompt clones and runs it — the AI-native install, on-thesis for Codos. Paste into Claude Code:

> Clone https://github.com/<you>/house-harness, read CLAUDE.md and AGENTS.md, run `./install.sh` to bring the stack up with docker compose, fill any missing secrets from `.env.example`, wait for `/health` to pass, then print the agent endpoint and the LangSmith trace URL. Run the demo queries in SOLUTION.md and show me the traces.

Why it works: `CLAUDE.md → AGENTS.md` carry the norms and the run steps; `install.sh` + `docker-compose.yml` bring up app (SQLite store) with LangSmith tracing via env; the demo queries are in `SOLUTION.md`. Nothing bespoke — the conventions do the orchestration.

**Fresh-clone fallback (for a non-Claude examiner):**
```bash
git clone https://github.com/<you>/house-harness && cd house-harness
cp .env.example .env   # add ANTHROPIC_API_KEY + HOUSE_HARNESS_API_TOKEN
./install.sh           # compose up, ingest data/, health-check, print endpoints
```

## Showing full functionality + observability
- **Functionality** — run the planted-trap queries (SOLUTION "Demo queries"): each returns a **trust envelope** — answer + sourced, entailment-verified claims + freshness + dissent + scope + confidence. That envelope *is* the "deep questions, good answers, with attribution" requirement made visible.
- **Observability** — `docker-compose` enables **LangSmith** tracing from env; tracing is on from the first run (`AGENTS.md` rule). The LangSmith UI (`smith.langchain.com`) shows the per-query trace tree: ingest → retrieve → extract → synthesize → **verify** → caps/cost. Open it during the demo/video — it proves the "conventions around the model" claim better than prose can.

## Requirements → where we satisfy them
| README requirement | Where | Status |
| --- | --- | --- |
| Agent-friendly interface (CLI/HTTP/MCP/library) | HTTP `/ask` + `/health` live (stdlib skeleton, token-authed); MCP is the primary *design*, not yet a running server | HTTP wired; MCP designed |
| Deep questions: staleness / aliases / hierarchy / contradictions / attribution | assertion ontology §4.13 + trust envelope §4.4; 13 seeded eval cases (all trap classes incl. abstention + entity hygiene) + held-out validation | design ✓ |
| Reasonable time | ontology-first answer path, O(slice); raw whole-corpus / Hybrid fallback §4.5; caps §4.9 | design ✓ |
| ingestion-time vs query-time split (your call) | stated & defended §4.1 | ✓ |
| Built for a moving target (live ingestion = small change) | idempotent versioned re-ingest §4.13 + pluggable loaders | design ✓ |
| Live in production, not local | `fly.toml` + token auth; URL in SOLUTION | **needs deploy** |
| Production-grade conventions around the LLM | typed contracts, structured output, cite-or-abstain + entailment, evals, AGENTS/PLAN/PROGRESS/VERIFY, Greptile | ✓ strength |
| How LLMs are used (when/where/with what) | extraction = LLM; profiler/planner/health/ontology = rule tables (deliberately not LLM); reader/executor split is designed (v1 is read-only Q&A, runtime enforcement deferred) | design ✓ |
| No starter code / setup is signal | clean scaffold, one-command + one-prompt install | ✓ |
| SOLUTION.md (run/tradeoffs/architecture/cuts) | present | fill URL |
| Observability *(not required)* | LangSmith, traced from first run | ✓ bonus |

## Before we can hit send (scaffold → shippable)
Everything above is blueprint + scaffold + conventions. To actually submit:
1. **Build the stubs** — follow `PLAN.md` in the `VERIFY.md`-gated loop until `make eval` passes (`delta.pass_rate > 0`).
2. **Run validation** — `make validate`; every blocking check in `VALIDATION.md` green; commit `evals/validation/report.json`.
3. **Deploy** — `fly deploy`; set secrets; paste the URL into `SOLUTION.md`; note cold-start.
4. **Fill SOLUTION.md placeholders** — `<DEPLOY_URL>`, tradeoffs, cuts.
5. *(optional)* **Record the 3-min video** — one-prompt install → trap queries → LangSmith traces.
6. **Package & send** — `make verify` (extract clean + run), then `make package`, email the zip to gleb@ and dima@.
