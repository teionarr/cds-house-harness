"""Verified alias / anti-alias ledger — ground truth from the full corpus read.

This is what the alias-resolution eval (VALIDATION A1, precision >=0.95) grades
against, and the seed the extractor's `distinct_from` is mined from. Authored by
reading all of data/ (24 interviews, chat, email, dashboards, PDFs, org-chart).
Corpus-specific SEED — regenerate per corpus; the engine is generic, this is not.

Over-merge is silent corruption, so ANTI_ALIASES is the load-bearing half. Note
the non-person identities at the end: a robust extractor must NOT mint them as
entities at all (they come from the code/contributors analysis).
"""

from __future__ import annotations

# canonical entity -> observed surface forms (safe to merge)
ALIASES: dict[str, list[str]] = {
    "HelixPay Brasil": ["HPB", "Helix Brasil"],
    "HelixPay POS Self-Service": ["Self-Serve", "POS SS", "POS Self-Service", "the kiosk"],
}

# pairs that look mergeable but MUST stay distinct (subject, distinct_from, why)
ANTI_ALIASES: list[tuple[str, str, str]] = [
    ("Maria Santos (Head of CS, Brasil)", "Maria Silva (Head of Sales, Brasil)",
     "org-chart + both interviews open with the interviewer confusing them"),
    ("Tan Wei Ming (backend eng, Sao Paulo)", "Daniel Tan (VP Engineering)",
     "org-chart + contributors-analysis: 'different people'; relocated SG->SP 2026-02-09"),
    ("Pedro Almeida (backend eng, payments)", "Sofia Almeida (CRO)",
     "Camila interview: 'mesmo sobrenome so', same surname only, unrelated"),
    ("Gabriel Souza (Brasil mobile eng)", "Camila Souza (senior backend eng)",
     "contributors-analysis: 'not related to Camila Souza'"),
    ("Aaron Wong (Performance Marketing)", "Aaron Goh (General Counsel)",
     "two different Aarons; Aaron Wong's core-repo commits are a misattribution"),
    ("Aisha Mahmud (FP&A Lead, Finance)", "Aisha Yusof (Sales Manager, SEA)",
     "Aisha Mahmud interview meta flags the calendar mix-up explicitly"),
    ("Priya Raman (COO)", "Priya Devi (HRBP, SEA) / Priya Sharma (Inbound Sales)",
     "three different Priyas; Sarah Ng enumerates them"),
    ("HelixPay POS Self-Service (kiosk)", "HelixPay POS (card-reader terminal)",
     "Vinod/overview: different products, sales reps mix them up"),
    ("Wei Chen (CEO)", "Tan Wei Ming / Yong Wei", "'Wei' recurs across unrelated names"),
]

# commit identities that are NOT people — must never be minted as entities
NON_PERSON_IDENTITIES: list[tuple[str, str]] = [
    ("noise", "former-contractor GitHub account, flagged for cleanup (contributors-analysis)"),
    ("Nikita@local", "unverified local-machine commit signature, likely an existing eng's 2nd machine"),
    ("Aiman Idris (in pos-app commits)", "misattribution — Aiman Idris is a CSM, not an engineer; recycled email"),
]
