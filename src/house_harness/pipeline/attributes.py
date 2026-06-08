"""Controlled attribute namespace — a universal KERNEL + a per-corpus DOMAIN vocab.

The extractor MUST map every fact onto a canonical `attribute` key (or emit
`new_attribute:<slug>` for review). This is what makes `ontology.resolve()`'s
grouping by (subject, attribute, scope) actually fire: without it, "MRR" /
"recurring revenue" / "rev" become three non-conflicting assertions and
contradiction detection silently fails. Cheap, deterministic, decisive.

GENERALITY: the namespace has two halves.
- `_KERNEL` — universal org/person attributes (reports_to, owns, role, …). These
  transfer to ANY company unchanged; they are real engine config.
- The DOMAIN half (a company's metrics, programs, products) is NOT universal. It is
  *induced* from the corpus (`pipeline/vocab.py`) and pinned per corpus, then
  installed via `install_vocab()`. `_SEED_DOMAIN` below is the pinned vocab for the
  bundled corpus — regenerable, not hardcoded engine config. On a new corpus,
  induction replaces it, so the engine works turnkey without hand-authoring keys.

Scope is the qualifier that separates "both true" from "conflict": NPS at
scope="sea_enterprise" (62) and scope="aggregate" (47) co-exist; two values at
the *same* scope conflict.
"""

from __future__ import annotations

from collections.abc import Iterable

# Universal org/person attributes — engine config, present for every corpus.
_KERNEL: dict[str, str] = {
    "reports_to": "manager (solid line)",
    "dotted_reports_to": "functional dotted-line manager",
    "owns": "owner/authority for an area (e.g. pricing, a product, a program)",
    "role": "a person's role/title",
    "location": "a person's location",
}

# Pinned DOMAIN vocab for the BUNDLED corpus — induced from it, not engine config.
# A new corpus replaces this via `install_vocab(vocab.induce(...))`.
_SEED_DOMAIN: dict[str, str] = {
    # financials
    "revenue.quarter_actual": "recognized revenue for a quarter (currency per scope)",
    "revenue.quarter_target": "revenue plan/target for a quarter",
    "revenue.month_actual": "recognized revenue MTD/for a month",
    "net_new_merchants": "net new merchants in a period",
    "runway_months": "months of runway at current burn",
    "ebitda_status": "EBITDA posture (e.g. negative)",
    # program / roadmap
    "confluence.ga_date": "Project Confluence GA / launch date",
    "confluence.owner": "owner of Project Confluence",
    "confluence.status": "Confluence schedule status (on-track/behind/re-baselined)",
    "tap.launch_date": "HelixPay Tap launch date (by region scope)",
    "product.attach_rate": "attach rate for a product (scope = product+region)",
    # customer / GTM
    "nps": "Net Promoter Score (scope = segment, e.g. aggregate/sea_enterprise)",
    "crm.system_of_record": "active CRM (scope = region: sea/brasil)",
    "crm.hubspot_pipeline_pct": "% of pipeline in HubSpot (scope = region)",
    "crm.migration_owner": "owner of the CRM migration",
    "pipeline_coverage": "pipeline coverage ratio (scope = region)",
    # accounts / churn
    "account.status": "account state (active/at-risk/churned)",
    "account.churn_reason": "why an account churned",
    "account.arr": "ARR for an account (or ARR delta)",
    "churn.arr_total": "total ARR lost to churn in a period",
    # ops / quality
    "bug.status": "status of a known bug/issue",
    "bug.impact": "scope/impact of a bug (e.g. merchants affected)",
    "hiring.status": "hiring posture for a team (scope = team/region)",
}

# The live namespace: kernel + the currently-installed domain vocab. Defaults to the
# bundled corpus's pinned vocab so behavior is unchanged until induction installs one.
_ACTIVE: dict[str, str] = {**_KERNEL, **_SEED_DOMAIN}

# scope vocabulary the extractor should prefer (free-form allowed, but normalize to these)
SCOPES: dict[str, list[str]] = {
    "region": ["sea", "brasil", "singapore", "hq"],
    "segment": ["aggregate", "sea_enterprise", "sea_smb", "brasil_enterprise", "brasil_smb"],
}


def kernel() -> dict[str, str]:
    """The universal attributes induction must NOT re-mint (it excludes these)."""
    return dict(_KERNEL)


def active_vocab() -> dict[str, str]:
    """The live controlled namespace (kernel + installed domain). What the extractor
    is shown and what `classify`/`nonconformant` grade against."""
    return _ACTIVE


def domain_vocab() -> dict[str, str]:
    """The installed DOMAIN half only (kernel excluded) — what gets pinned to the store
    (the kernel is re-added on every `install_vocab`)."""
    return {k: v for k, v in _ACTIVE.items() if k not in _KERNEL}


def install_vocab(domain: dict[str, str]) -> None:
    """Install a corpus's induced/pinned DOMAIN vocab (kernel always stays). Called at
    extraction (after induction) and at serving boot (from the pinned vocab) so
    grouping/grading run against THIS corpus's namespace, not a hardcoded one."""
    global _ACTIVE
    _ACTIVE = {**_KERNEL, **domain}


def is_known(attribute: str) -> bool:
    """True if the attribute is in the controlled vocabulary. The extractor flags
    `new_attribute:<slug>` for anything that isn't, for human review — never
    silently invents a synonym."""
    return attribute in _ACTIVE


# The escape hatch: an out-of-vocab attribute is allowed ONLY when explicitly
# flagged for human review with this prefix. Anything else is a silent synonym.
NEW_ATTRIBUTE_PREFIX = "new_attribute:"


def classify(attribute: str) -> str:
    """Three outcomes, no fourth:
    - 'known'     — in the controlled vocab; resolve() will group on it.
    - 'new'       — explicit `new_attribute:<slug>` flag, queued for human review.
    - 'violation' — an unsanctioned attribute. This is the silent killer: a synonym
      like 'recurring_rev' never collides with 'revenue.quarter_actual' in resolve(),
      so no conflict is ever surfaced and the engine *looks* like it works. Never
      store one — drop + log."""
    if attribute in _ACTIVE:
        return "known"
    if attribute.startswith(NEW_ATTRIBUTE_PREFIX):
        return "new"
    return "violation"


def nonconformant(attributes: Iterable[str]) -> list[str]:
    """The extractor MUST run this on every batch before upsert (see
    pipeline/harness.py). Returns the offending attribute strings — empty means
    conformant. A non-empty result is a hard error in the extraction eval, not a
    warning: an unflagged synonym silently disables contradiction detection."""
    return [a for a in attributes if classify(a) == "violation"]
