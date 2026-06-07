"""Controlled attribute namespace — derived from the real HelixPay corpus.

Corpus-specific SEED, not generic engine config: regenerate this vocab per corpus
(the engine is generic; these keys are not). Same applies to pipeline/aliases.py.

The extractor MUST map every fact onto a canonical `attribute` key here (or emit
`new_attribute:<slug>` for review). This is what makes `ontology.resolve()`'s
grouping by (subject, attribute, scope) actually fire: without it, "MRR" /
"recurring revenue" / "rev" become three non-conflicting assertions and
contradiction detection silently fails. Cheap, deterministic, decisive.

Scope is the qualifier that separates "both true" from "conflict": NPS at
scope="sea_enterprise" (62) and scope="aggregate" (47) co-exist; two values at
the *same* scope conflict.
"""

from __future__ import annotations

from collections.abc import Iterable

# canonical attribute key -> human description. Extractor maps into these.
ATTRIBUTES: dict[str, str] = {
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
    # org / ownership
    "reports_to": "manager (solid line)",
    "dotted_reports_to": "functional dotted-line manager",
    "owns": "owner/authority for an area (e.g. pricing, a product, a program)",
    "role": "a person's role/title",
    "location": "a person's location",
    # ops / quality
    "bug.status": "status of a known bug/issue",
    "bug.impact": "scope/impact of a bug (e.g. merchants affected)",
    "hiring.status": "hiring posture for a team (scope = team/region)",
}

# scope vocabulary the extractor should prefer (free-form allowed, but normalize to these)
SCOPES: dict[str, list[str]] = {
    "region": ["sea", "brasil", "singapore", "hq"],
    "segment": ["aggregate", "sea_enterprise", "sea_smb", "brasil_enterprise", "brasil_smb"],
}


def is_known(attribute: str) -> bool:
    """True if the attribute is in the controlled vocabulary. The extractor flags
    `new_attribute:<slug>` for anything that isn't, for human review — never
    silently invents a synonym."""
    return attribute in ATTRIBUTES


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
    if attribute in ATTRIBUTES:
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
