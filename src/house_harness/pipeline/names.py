"""Entity name canonicalization from the authoritative roster.

The org chart is the company's name registry. Mentions arrive inconsistently — full
name in interviews, first name in Slack, casing/transliteration drift in mixed-
language docs ('Sofia' / 'sofia' / 'Sofia Almeida'). Left alone they fragment the
graph and break multi-hop hierarchy. This module builds a registry from the roster
and maps every mention to one canonical entity.

Crucially, a first name maps to a full name ONLY when it is UNAMBIGUOUS in the
roster — 'Sofia' -> 'Sofia Almeida' (unique), but 'Maria'/'Priya'/'Aisha'/'Wei'
stay unmapped because several people share them. That is the same discipline as the
anti-alias ledger: never over-merge.
"""

from __future__ import annotations

import re

# 2–3 capitalised words (accents allowed); the roster's name shape.
_NAME = re.compile(r"[A-ZÀ-Ý][a-zà-ÿ'’]+(?:\s+[A-ZÀ-Ý][a-zà-ÿ'’]+){1,2}")
# Tokens that mark a phrase as a ROLE/place, not a person name.
_NOT_NAME = re.compile(
    r"\b(CEO|CFO|CTO|COO|CRO|VP|Lead|Manager|Head|Director|Officer|Engineer|Eng|"
    r"Backend|Frontend|Mobile|Platform|Product|Sales|Support|Senior|Account|Executive|"
    r"Singapore|Paulo|Brasil|Brazil|Jakarta|Rio|Manila|Board|Counsel|Controller|Associate|SDR|CSM|PM)\b"
)


class Registry:
    def __init__(self, canonical: set[str], variant_to_canonical: dict[str, str]) -> None:
        self.canonical = canonical
        self._map = variant_to_canonical

    def canonicalize(self, name: str) -> str:
        """Map a mention to its canonical full name; unknown/ambiguous pass through."""
        key = name.strip().lower()
        return self._map.get(key, name.strip())

    def find(self, text: str) -> str | None:
        """The canonical person named in a free-text query (longest match first; then
        an unambiguous first name). Used to anchor hierarchy questions robustly."""
        t = text.lower()
        for full in sorted(self.canonical, key=len, reverse=True):
            if re.search(rf"\b{re.escape(full.lower())}\b", t):
                return full
        for variant, full in self._map.items():
            if " " not in variant and re.search(rf"\b{re.escape(variant)}\b", t):
                return full
        return None


def _candidate_names(roster_text: str) -> set[str]:
    names: set[str] = set()
    for m in _NAME.finditer(roster_text):
        cand = m.group(0).strip()
        if not _NOT_NAME.search(cand):
            names.add(cand)
    return names


def build_registry(roster_text: str) -> Registry:
    """Build the canonical name registry from the roster (the org chart). Maps each
    full name (any casing) and each UNAMBIGUOUS first name to its canonical form."""
    canonical = _candidate_names(roster_text)
    first_counts: dict[str, int] = {}
    for full in canonical:
        first_counts[full.split()[0].lower()] = first_counts.get(full.split()[0].lower(), 0) + 1
    mapping: dict[str, str] = {}
    for full in canonical:
        mapping[full.lower()] = full
        first = full.split()[0]
        if first_counts[first.lower()] == 1:  # unambiguous -> first name resolves to full
            mapping.setdefault(first.lower(), full)
    return Registry(canonical, mapping)


_EMPTY = Registry(set(), {})
