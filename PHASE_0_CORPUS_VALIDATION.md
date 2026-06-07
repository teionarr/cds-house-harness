# PHASE_0_CORPUS_VALIDATION.md

**The hard gate — RUN 2026-06-07 (PASSED, exhaustive read complete).** Adapted from the consulting CTO's gate. The plan was first authored blind; this gate was then run by reading **all of `data/`** — 24 interviews, 3 chat logs, 2 emails, 3 dashboards, both PDFs, 5 core docs. Verdicts below are findings, not assumptions. The earlier `mrr` contradiction the gate inherited was a fabrication and is **corrected** (T3).

## 0. Inventory — matches manifest
Present and as listed. **Interview count: 24** (confirmed). Notable: interviews are foldered by department (`product__pos_self_service/` confirms the POS-SS distinction); chat is 3 channels; 4 JPEG charts + 2 PDFs.

## 1. Trap verification
| # | Trap | Verdict | Finding |
|---|---|---|---|
| T1 | Confluence June → Sep 30 | **CONFIRMED** | all-hands 04-15 "Q3 is not on the table, end of June"; weekly 04-21 + board 04-22 re-baseline to Q3; Daniel: "I'd commit to Sep 30." |
| T2 | NPS 62 (SEA-ent) vs 47 (aggregate), both true | **CONFIRMED+RICHER** | full table: aggregate 47 (n=786), SEA-ent 62, SEA-SMB 41, BR-ent 53, BR-SMB 31 (−8 QoQ). |
| T3 | ~~MRR disagrees board-deck vs weekly~~ | **CORRECTED (DEAD)** | No MRR anywhere. Real metric: **Q1 revenue SGD 14.2M vs 16M target (−11%)**. The contradiction is all-hands optimism vs internal reality, resolved by source-tier + recency — not an MRR figure clash. Eval rewritten as `q1-revenue`. |
| T4 | Maria Santos ≠ Maria Silva | **CONFIRMED** | org-chart explicit, "told twice not to confuse them." Santos=Head CS Brasil; Silva=Head Sales Brasil. |
| T5 | POS Self-Service ≠ POS | **CONFIRMED** | overview: "Not the same as POS." |
| T6 | Org chart stale vs Apr-18 reorg | **CONFIRMED** | export 04-15; note: "does not reflect the SDR reorg announced April 18"; omits 12 contractors. |
| T7 | Who reports to Sofia | **CONFIRMED** | Sofia Almeida (CRO): SEA via Aisha Yusof, Brasil via Maria Silva (dotted-line Silva↔Sofia). |
| T8 | Brazil on Pipedrive; 78% is SEA-weighted | **CONFIRMED** | weekly: "Pipedrive remains system of record … 78% in HubSpot is SEA-weighted." |
| T9 | merchant_id schema owners | **CONFIRMED+** | Sara Wijaya, Vikram Patel, Camila Souza **+ Luiz Ferreira** (all-hands: "Sara, Vikram, Camila and Luiz are leading this"). |
| T10 | Cosmos churn = multi-property gap | **CONFIRMED** | debrief: 47 properties, need group-level reporting; moved to competitor; ARR −120K (renewal would've been 165K). |
| T11 | EU-segment churn → abstain | **CONFIRMED (no EU)** | corpus is SEA + Brazil only; EU has no source → valid abstain. (`eu-churn-gap` is in the build-loop set `evals/evals.json`; `v-abstain` on 2027 headcount is the held-out negative.) |
| T12 | Slack noise must not become fact | **CONFIRMED** | chat is heavy chatter; reliability tier `chat=1` floors it. |
| T13 | CEO has no interview; assembled | **CONFIRMED** | CEO is **Wei Chen** (not the placeholder used while blind); no Wei Chen interview — context from all-hands/board/email. |
| T14 | Q1 financials PDF-grounded | **CONFIRMED** | numbers cite `q1-2026-results.pdf` (filing tier). |
| T15 | **NPS framing is a *live contested decision*** (new) | **NEW — decision/contradiction** | exec-huddle: Wei wants 62 as headline ("don't lead with aggregate"); Marco + Tom want aggregate 47 as the external lead; Wei tables it. Not just "both true" — an unresolved ownership-of-narrative call. Add eval `nps-framing-decision`. |
| T16 | **Non-person commit identities** (new) | **NEW — identity/abstain** | code/contributors: `noise`, `Nikita@local`, and a misattributed `Aiman Idris` (a CSM) must NOT be minted as engineers. Add eval `non-person-identity`. |
| T17 | **Açaí Express / HX-LOY-487 multi-hop** (new) | **NEW — assembly** | email thread: customer → ~280 affected merchants → root cause in legacy Brasil schema → blocked behind Confluence → explicit tradeoff (free Camila 2wk = +3wk on GA) → exec escalation. Strong multi-source assembly case. |
| T18 | **Q4 dashboard (15.4M) vs Q1 (14.2M)** (new) | **NEW — staleness** | a stale "auto-refreshed daily" Q4 dashboard still reads 15.4M; current Q1 is 14.2M (revenue fell QoQ). "What's our revenue" must return Q1, not the stale dashboard. |

## 2. Attribute vocabulary (OUTPUT)
Committed in code as `src/house_harness/pipeline/attributes.py` (30 canonical keys derived from the corpus) — our plan keeps vocab in code, not YAML. Extractor maps into it or flags `new_attribute`.

## 3. Alias + anti-alias ledger (OUTPUT)
Committed as `src/house_harness/pipeline/aliases.py` — **9 anti-alias pairs** (both Marias; Tan Wei Ming/Daniel Tan; Pedro Almeida/Sofia Almeida; Gabriel Souza/Camila Souza; Aaron Wong/Aaron Goh; Aisha Mahmud/Aisha Yusof; three Priyas; POS/POS-SS; the Wei cluster) plus **3 non-person identities** (`noise`, `Nikita@local`, misattributed `Aiman Idris`). This is the ground truth VALIDATION A1 (precision ≥0.95) grades against.

## 4. Source-tier map (OUTPUT)
`ontology.RELIABILITY`: filing(5)=q1-results/board-deck PDFs; board(4)=board-update + exec email; official(3)=all-hands/weekly-review/dashboards; interview(2); chat(1). Tie-break verified on T1/T3/T8: board+recency correctly picks the current value over the all-hands line.

## 5. Budget decision
**Measured ≈54.5K tokens** (md+html) + 2 PDFs + 4 charts — **fits → whole_corpus**, SQLite store, no vector index. Hybrid/pgvector documented as the scale path only.

## 6. Eval-class coverage
All classes have a **confirmed** case in `evals/evals.json`: hierarchy (`reports-to-sofia`), financial+staleness (`q1-revenue`, `confluence-launch`), decisions/policy (`discount-authority`), status/risk (`brazil-pipeline`, `cosmos-hotels`), identity/alias (`maria-resolution`, `pos-antialias`; CEO assembly via Wei Chen), contradiction (`nps-segmented`, `confluence-launch`), abstention (`eu-churn-gap`), entity-hygiene negative (`non-person-identity`). The held-out set adds `v-abstain` (2027 headcount).

## 7. Held-out discipline
`evals/validation/validation.json` authored separately (paraphrases + abstain/reliability negatives); locked before tuning; diff vs `evals.json` proves no leakage.

## GO / NO-GO — **GO.**
All blocking rows green; T3 corrected; three vocab artifacts committed; budget decided; classes covered; held-out locked. Phase 1 (build the vertical slice) is unblocked.
