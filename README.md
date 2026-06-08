# House Harness Engine

A **company-definition engine.** It ingests a company's messy document corpus and
builds a *House Harness* — a queryable ontology plus a generated `<COMPANY>.md` —
that an AI agent loads to operate the company without reading everything: resolved
aliases, as-of dates, contradictions surfaced, owners and guardrails, every answer
sourced.

The consumer is an agent. The primary interface is **MCP**; HTTP `/ask` is the same
engine over a socket.

- **Use it →** the MCP tools and the one-command run, below.
- **Read the writeup →** [`SOLUTION.md`](./SOLUTION.md) — how it runs, the tradeoffs, the architecture, and what's deferred.
- **Extend it →** [`DEVELOPMENT.md`](./DEVELOPMENT.md) — internals, how to point it at a new corpus, and how to test/eval/validate.

## Run it (one command, fresh clone)

```bash
git clone github.com/teionarr/cds-house-harness && cd cds-house-harness   # the corpus is vendored in data/
./install.sh                                                              # docker compose up, ingest data/ on boot, health-check
```

`install.sh` needs Docker + an `ANTHROPIC_API_KEY` (copied into `.env` on first run;
LangSmith tracing and Doppler are both optional). It serves on `:8080`.

```bash
curl -s localhost:8080/ask \
  -H "Authorization: Bearer $HOUSE_HARNESS_API_TOKEN" \
  -d '{"q":"Who can approve a customer discount, and when does Confluence go GA?"}'
```

Live instance: **https://house-harness.fly.dev** (Fly.io; `fly.toml`) — MCP at `/mcp`,
plus `/health` (open) and `/ask`. Machines scale to zero, so the first call after idle
wakes in a few seconds.

## Use it (the agent interface)

MCP is the keystone surface, and **it's hosted** — add the live server to any MCP
client (Claude Code, Claude Desktop, Cursor) with one command, no clone, no build:

```bash
claude mcp add --transport http house-harness https://house-harness.fly.dev/mcp
```

Then just ask the agent about the company — it calls four tools, each returning
structured data it can *act on*, not just read:

| Tool | Returns |
|---|---|
| `ask_company(query)` | the full **trust envelope** — answer + sourced claims + dissent + freshness + coverage gaps + authority-routed escalation + confidence + status |
| `get_harness()` | the distilled House Harness — charter, targets, guardrails/authorities, taxonomy |
| `get_harness_health()` | the mirror — what's missing or off, with quick-win actions and owners |
| `get_entity(name)` | the resolved assertions about one entity, each with its source and as-of date |

`ask_company` routes through the same single entrypoint as HTTP `/ask`, so the two
surfaces can never diverge. The same host also serves `GET /health` (open) and
`POST /ask` (bearer-gated) for non-MCP clients. (Locally, `house-harness mcp` runs
the same server over stdio for an agent to spawn as a subprocess.)

## What's inside

```
src/house_harness/
  schema.py       # the typed contracts — Assertion, TrustEnvelope, HouseHarness, …
  config/         # llm.py (model seam), structured.py (validate-and-repair LLM calls)
  ingest/         # corpus loaders + the untrusted-content gate
  pipeline/       # extraction, the ontology spine (assertions → resolve/supersede/dissent),
                  #   vocab induction, name canon, harness distillation, health mirror
  retrieval/      # the raw-corpus fallback for out-of-namespace questions
  synthesis/      # query-time answering + claim entailment verification
  serve/          # mcp.py (primary) + the thin HTTP /ask /health server
  guards/         # egress PII/secret redaction
data/             # the vendored company corpus (no runtime fetch)
evals/            # the uplift gate (with- vs without-harness) + the held-out set
```

Built with **LangChain** `init_chat_model` behind a one-line model seam (default
`anthropic:claude-sonnet-4-6`); the store is **SQLite**, persisted on the deploy
volume. The owned layer is the ontology, the harness, and the evals — the model is
swappable config.
