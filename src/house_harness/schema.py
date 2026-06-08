"""The integration contract between all worktrees.

Change this file deliberately — these types are the only coupling between the
ingest / pipeline / synthesis / serve modules; no raw dicts cross those lines.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    transcript = "transcript"
    ticket = "ticket"
    doc = "doc"
    code = "code"
    chat = "chat"


class Artifact(BaseModel):
    """A normalized unit of ingested org knowledge."""

    id: str
    source: str  # dataset/system it came from
    type: ArtifactType
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class SourceSpan(BaseModel):
    """Provenance: points a playbook step back at real artifact text."""

    artifact_id: str
    start: int
    end: int


class PlaybookStep(BaseModel):
    text: str
    source: SourceSpan  # REQUIRED — unsourced steps must be dropped, never invented


class Playbook(BaseModel):
    """An operational playbook in the harness; rendered into a section of <COMPANY>.md."""

    name: str
    description: str  # when-to-use description
    steps: list[PlaybookStep]
    tools: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)


class RelationKind(str, Enum):
    reports_to = "reports_to"
    dotted_reports_to = "dotted_reports_to"  # matrix / dotted-line org
    owns = "owns"
    uses = "uses"
    depends_on = "depends_on"
    produces = "produces"


class GraphEdge(BaseModel):
    src: str
    dst: str
    relation: RelationKind


class CompanyGraph(BaseModel):
    nodes: list[str]
    edges: list[GraphEdge]
    centrality: dict[str, float] = Field(default_factory=dict)  # node -> leverage score


# ── Trust envelope (every answer ships one) ──────────────────────────────────


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    abstain = "abstain"


class Claim(BaseModel):
    text: str
    sources: list[str]  # artifact/span ids — never empty (cite-or-abstain)
    as_of: str | None = None
    scope: str | None = None  # qualifier: "SEA-enterprise" vs "aggregate" — both can be true
    assertion_id: str | None = None  # the ontology assertion this claim projects
    verified: bool | None = None  # entailment-checked: does the cited span support it?


class Dissent(BaseModel):
    point: str
    sources_disagree: list[str]


class Escalation(BaseModel):
    """Routes a coverage gap to the owning authority already in the harness."""

    gap: str
    owner: str
    evidence: list[str] = Field(default_factory=list)


class Status(str, Enum):
    answered = "answered"  # grounded answer returned
    abstained = "abstained"  # no source covers it — a real coverage gap
    degraded = "degraded"  # partial: some stage failed, answer is incomplete
    failed = "failed"  # could not complete (retrieval/LLM/system error)


class ServeMode(str, Enum):
    """Provenance of the answer. `live` = the real pipeline (the only mode that may
    be graded/shipped). `mock` = canned skeleton answer (Phase-1 deploy-first only);
    it self-identifies so a mock can never masquerade as a real answer."""

    live = "live"
    mock = "mock"


class AnswerPath(str, Enum):
    """Which query path produced the answer. `ontology` = answered from the resolved
    ontology slice (the default and the only valid path for in-namespace/graded
    questions — every claim carries an `assertion_id`). `fallback` = raw retrieval
    over the corpus for out-of-namespace questions (no assertion_ids; capped lower
    confidence). A graded trap returned via `fallback` is a bug, not an answer."""

    ontology = "ontology"
    fallback = "fallback"


class TrustEnvelope(BaseModel):
    answer: str
    status: Status = Status.answered
    mode: ServeMode = ServeMode.live  # `mock` answers stamp themselves; validate FAILs on mock
    answer_path: AnswerPath = AnswerPath.ontology  # ontology-first by default; fallback self-flags
    claims: list[Claim] = Field(default_factory=list)
    freshness: str | None = None
    dissent: list[Dissent] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    escalate_to: list[Escalation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)  # operational failures, not gaps
    confidence: Confidence = Confidence.medium


# ── House Harness (the defining-artifact library) ────────────────────────────


class Target(BaseModel):
    """An eval the company holds itself to."""

    name: str
    target: str
    current: str | None = None
    source: SourceSpan


class Guardrail(BaseModel):
    """A policy/constraint plus who may decide on it."""

    rule: str
    authority: str | None = None
    sources: list[SourceSpan] = Field(default_factory=list)


class HouseHarness(BaseModel):
    """Renders to HELIXPAY.md / <COMPANY>.md."""

    company: str
    charter: str  # mission + operating principles
    taxonomy: CompanyGraph
    targets: list[Target] = Field(default_factory=list)
    guardrails: list[Guardrail] = Field(default_factory=list)
    playbooks: list[Playbook] = Field(default_factory=list)


# ── Retrieval + ingestion contracts (no raw dicts across boundaries) ─────────


class RetrievedChunk(BaseModel):
    """A typed retrieval hit. Replaces the untyped dict at the retrieval boundary."""

    artifact_id: str
    text: str
    score: float
    as_of: str | None = None
    retriever: str  # "dense" | "sparse" | "graph" — provenance of the hit


class IngestFailure(BaseModel):
    """One file that could not be ingested. A failed file is an honest coverage
    gap, not silently missing data."""

    source: str
    error: str


# ── Privilege boundary: reader pod (untrusted) -> executor pod (privileged) ──


class RequestKind(str, Enum):
    """Closed action vocabulary. No arbitrary fetch, no URL, no shell — the
    reader can only *request* these; the executor validates and runs them."""

    retrieve = "retrieve"  # pull more context for an entity/topic
    escalate = "escalate"  # route a coverage gap to an owner


class PlanRequest(BaseModel):
    """A typed, allowlisted action the reader may request but never perform.
    `target` is an ontology id / topic / gap — validated against the harness,
    never an external URL."""

    kind: RequestKind
    target: str


class ReaderOutput(BaseModel):
    """All the reader pod (which sees the untrusted query + content) may emit:
    a structured answer draft plus typed requests — never tool calls or commands.
    Injection can, at worst, yield a request that fails allowlist validation."""

    draft: TrustEnvelope
    requests: list[PlanRequest] = Field(default_factory=list)


# ── Adaptive ingestion: profile -> pipeline config ──────────────────────────


class ContextStrategy(str, Enum):
    ontology_first = "ontology_first"  # DEFAULT: answer from the resolved ontology slice
    whole_corpus = "whole_corpus"  # fallback for out-of-ontology questions (raw, fits in context)
    hybrid = "hybrid"  # scale path: dense+sparse+graph index


class CorpusProfile(BaseModel):
    """Measured shape of the input corpus — the planner's only input."""

    token_estimate: int
    format_mix: dict[str, int] = Field(default_factory=dict)  # type -> file count
    entity_estimate: int = 0
    has_images: bool = False
    date_span_days: int | None = None
    languages: list[str] = Field(default_factory=lambda: ["en"])


class PipelineConfig(BaseModel):
    """Architecture chosen for this corpus, plus a human-readable rationale.
    Produced deterministically from a CorpusProfile (never by an LLM)."""

    context_strategy: ContextStrategy
    vision_extraction: bool = False
    build_graph: bool = True
    rerank: bool = False
    rationale: str = ""


# ── Harness health: what's missing / off, and the quick win ─────────────────


class GapKind(str, Enum):
    missing_section = "missing_section"  # an expected element is empty/thin
    unowned = "unowned"  # target/guardrail with no authority
    unresolved_conflict = "unresolved_conflict"  # sources disagree, no source of record
    stale = "stale"  # newest supporting source is old
    coverage_gap = "coverage_gap"  # a cared-about topic no source addresses
    orphan = "orphan"  # entity referenced but never defined


class HarnessGap(BaseModel):
    kind: GapKind
    where: str  # the section / entity / metric the gap is about
    detail: str  # what's missing or off
    severity: int = Field(ge=1, le=5)  # 1 minor .. 5 critical
    suggested_action: str  # the quick win to fix it
    owner: str | None = None  # who should act (from harness authorities)


class HarnessHealth(BaseModel):
    """A mirror the company can read: what the system sees, and the quick wins."""

    completeness: float = Field(ge=0.0, le=1.0)  # share of expected harness populated
    gaps: list[HarnessGap] = Field(default_factory=list)  # prioritized by severity
    summary: str = ""


# ── Feedback (closes the loop: correction -> source + eval case -> re-extract) ─


class Feedback(BaseModel):
    """A correction or an escalation resolution — the input that closes the loop.
    Becomes a new sourced Artifact, a new gold eval case, and a re-extract trigger."""

    question: str
    correct_answer: str
    provided_by: str  # the authority/owner or user who resolved it
    supersedes: list[str] = Field(default_factory=list)  # source ids this overrides


# ── The ontology spine: sourced, dated, scoped assertions ───────────────────


class SourceTier(int, Enum):
    """Reliability ranking — higher wins ties in conflict resolution. A board
    email outweighs a Slack joke; a financial filing outweighs an interview."""

    filing = 5  # audited financials / board deck (PDF)
    board = 4  # board update / email
    official = 3  # all-hands, weekly review, dashboards
    interview = 2  # 1:1 interviews
    chat = 1  # Slack / chat — mostly noise


class Assertion(BaseModel):
    """The atomic unit of the ontology: a sourced, dated, scoped fact.

    Facts are never stored as settled values — they are assertions that can
    co-exist, supersede, or conflict. This single model carries four of the five
    planted traps at once: staleness (`as_of` + `supersedes`), contradiction
    (≥2 live assertions on the same subject+attribute+scope), segmentation
    (`scope` distinguishes "both true" from "conflict": NPS@SEA-enterprise=62 vs
    NPS@aggregate=47), and attribution (`source` on every one). `id` is stable
    (hash of subject+attribute+scope+source) so re-ingestion upserts, not duplicates.

    BITEMPORAL: two independent time axes, never conflated.
    - `as_of` = VALID time: the date the fact was true in the world (the Confluence
      GA slipped *to* Sept 30). Drives supersession — the fresher validity wins.
    - `recorded_at` = TRANSACTION time: the date this was written down / ingested
      (the doc's own date). Drives staleness — "our newest *record* of NPS is 9
      months behind the corpus snapshot" is a transaction-time question, not a
      validity one. Separating them is what lets a freshly-recorded restatement of
      an old fact read differently from a fact nobody has touched in a year.
    """

    id: str
    subject: str  # canonical entity id (post alias-resolution)
    attribute: str  # e.g. "confluence_launch_date", "nps"
    value: str
    scope: str | None = None  # qualifier; None = global. Same scope + differ = conflict
    as_of: str | None = None  # VALID time — when the fact was true (drives supersession)
    recorded_at: str | None = None  # TRANSACTION time — when written/ingested (drives staleness)
    source: SourceSpan
    reliability: SourceTier = SourceTier.official
    confidence: Confidence = Confidence.medium
    supersedes: list[str] = Field(default_factory=list)  # assertion ids
    live: bool = True  # False once superseded by a fresher/higher-tier assertion


class Alias(BaseModel):
    """Entity resolution incl. the anti-alias. `distinct_from` is load-bearing:
    it prevents the silent-corruption over-merge (Maria Santos != Maria Silva;
    POS Self-Service != POS)."""

    canonical: str
    aliases: list[str] = Field(default_factory=list)
    distinct_from: list[str] = Field(default_factory=list)  # must NOT be merged
