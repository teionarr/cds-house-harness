"""Headless eval runner — the uplift gate.

`make eval` / `evals.yml` invoke this as `python -m evals.harness`. It runs every
gold case through TWO arms and measures the delta:

  - **with_harness**  = the engine answering ontology-first (`serve.app.answer` in
    live mode -> the resolved ontology slice + trust envelope).
  - **without_harness** = a FAIR raw-corpus baseline (same model, same full corpus
    in context, same cite-or-abstain instruction) — the 'search box'. The ONLY
    difference is the ontology/harness layer, so the delta isolates its value.

Grading is DETERMINISTIC (the stable gate): each gold case carries `checks`
(`includes`/`excludes` token groups, `abstain`/`escalate` flags) graded in code —
no LLM judge in the loop, so the gate is reproducible and measures the system, not
judge variance. Mechanical envelope tripwires (valid envelope, ontology-first
answer_path + per-claim assertion_id) also apply to the harness arm. A legacy LLM
judge remains only for any case without `checks`.

Because the baseline arm and the harness fallback call the SAME raw-corpus answerer
(`respond.raw_corpus_answer`), the harness is never weaker than the baseline on a
question the ontology doesn't cover (a guaranteed tie); the uplift comes from the
resolved trap classes. Exit nonzero under `--gate` if any case errored or
`delta.pass_rate <= 0`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:  # src/ layout, robust to editable-install state
    sys.path.insert(0, str(ROOT / "src"))

from house_harness.config.structured import llm_json  # noqa: E402
from house_harness.schema import AnswerPath, Confidence, Status, TrustEnvelope  # noqa: E402


class _Verdict(BaseModel):
    passed: bool
    evidence: str = ""


# ── arms ──────────────────────────────────────────────────────────────────────


def _with_harness(prompt: str) -> TrustEnvelope:
    os.environ["HOUSE_HARNESS_SERVE_MODE"] = "live"
    from house_harness.serve import app

    app.reset_state()  # always read the freshly-built ontology
    return app.answer(prompt)


def _without_harness(prompt: str) -> str:
    """The fair baseline: the SAME raw whole-corpus answerer the engine falls back to
    (`respond.raw_corpus_answer`) — identical model, corpus, and cite-or-abstain
    prompt, no ontology. Sharing the function is what guarantees the harness is never
    weaker than the baseline on questions the ontology doesn't cover."""
    from house_harness.synthesis import respond

    return respond.raw_corpus_answer(prompt).answer


# ── grading ─────────────────────────────────────────────────────────────────--


def _render_envelope(env: TrustEnvelope) -> str:
    gaps = "; ".join(env.coverage_gaps)
    esc = "; ".join(f"{e.gap}->{e.owner}" for e in env.escalate_to)
    dis = "; ".join(d.point for d in env.dissent)
    return (
        f"{env.answer}\n[status={env.status.value} confidence={env.confidence.value}]\n"
        f"coverage_gaps: {gaps}\nescalate_to: {esc}\ndissent: {dis}"
    )


_ABSTAIN_RE = re.compile(
    r"cannot|can't|could not|couldn't|unable|no (data|source|information|figure|record|mention|"
    r"coverage)|not (available|covered|in the)|don't have|do not have|no such|insufficient",
    re.IGNORECASE,
)
_ROUTE_RE = re.compile(
    r"\b(ask|contact|owner|escalat|route|reach out|check with|refer to)\b", re.IGNORECASE
)


def _passes_checks(checks: dict, text: str, env: TrustEnvelope | None) -> bool:
    """Deterministic grade — the stable gate. `includes`: every group must have at
    least one of its alternatives present (case-insensitive). `excludes`: none may
    appear. `abstain`/`escalate`: structural for the harness (envelope), text-based
    for the baseline (which has no envelope) — so the harness's structured abstention
    and authority-routing are exactly the uplift that text-only baseline can't match."""
    t = text.lower()
    for group in checks.get("includes", []):
        if not any(tok.lower() in t for tok in group):
            return False
    for tok in checks.get("excludes", []):
        if tok.lower() in t:
            return False
    if checks.get("abstain"):
        ok = env.status is Status.abstained if env is not None else bool(_ABSTAIN_RE.search(t))
        if not ok:
            return False
    if checks.get("escalate"):
        if env is not None:
            ok = any(e.owner and e.owner != "unresolved" for e in env.escalate_to)
        else:
            ok = bool(_ROUTE_RE.search(t))
        if not ok:
            return False
    return True


def _judge(question: str, assertion: str, rendered_answer: str) -> bool:
    v = llm_json(
        "You grade whether an ANSWER satisfies a required ASSERTION. Pass ONLY if the "
        "answer clearly satisfies it; quote the supporting span in `evidence`. Be strict.\n\n"
        f"QUESTION: {question}\nASSERTION: {assertion}\nANSWER:\n{rendered_answer}",
        _Verdict,
    )
    return v.passed


def _mechanical(case: dict, env: TrustEnvelope) -> list[str]:
    """Ontology-first + envelope tripwires. Returns a list of failures (empty=ok)."""
    fails: list[str] = []
    if env.confidence not in set(Confidence):
        fails.append("invalid confidence")
    if env.status not in set(Status):
        fails.append("invalid status")
    if env.status is Status.abstained:
        if not env.coverage_gaps:
            fails.append("abstained without a coverage gap")
    elif env.status is Status.answered:
        # an answered ontology result must be grounded + ontology-first
        if env.answer_path is AnswerPath.ontology:
            if not env.claims:
                fails.append("answered with no claims")
            if any(c.assertion_id is None for c in env.claims):
                fails.append("ontology claim missing assertion_id")
        if not env.answer.strip():
            fails.append("answered with empty answer")
    return fails


def _grade_case(case: dict, rendered: str, env: TrustEnvelope | None) -> dict:
    """Deterministic when the case carries `checks` (the stable gate); the LLM judge
    is only a legacy fallback for cases that don't. Mechanical envelope tripwires
    apply to the with_harness arm regardless."""
    mech = _mechanical(case, env) if env is not None else []
    if "checks" in case:
        passed = not mech and _passes_checks(case["checks"], rendered, env)
        return {"passed": passed, "mechanical_failures": mech, "graded": "deterministic"}
    results = [
        {"assertion": a, "passed": _judge(case["prompt"], a, rendered)}
        for a in case.get("assertions", [])
    ]
    passed = not mech and all(r["passed"] for r in results)
    return {"passed": passed, "mechanical_failures": mech, "assertions": results}


# ── run ─────────────────────────────────────────────────────────────────────--


def run(suite_path: Path, subset: int | None, report: Path | None, gate: bool) -> int:
    data = json.loads(suite_path.read_text())
    cases = data["evals"]
    if subset:
        cases = cases[:subset]

    per_case = []
    wins = {"with_harness": 0, "without_harness": 0}
    canary_split = None
    errors = 0
    for case in cases:
        # Per-case isolation: one API/transient error (rate limit, exhausted credits)
        # records a failed case, never crashes the whole gate.
        try:
            env = _with_harness(case["prompt"])
            with_grade = _grade_case(case, _render_envelope(env), env)
            base = _without_harness(case["prompt"])
            without_grade = _grade_case(case, base, None)
            path, status = env.answer_path.value, env.status.value
        except Exception as exc:  # noqa: BLE001 — isolation is the point
            errors += 1
            with_grade = {"passed": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
            without_grade = {"passed": False, "error": "not run (with_harness errored)"}
            path, status = "error", "error"
        wins["with_harness"] += with_grade["passed"]
        wins["without_harness"] += without_grade["passed"]
        if case.get("id") == "uplift-canary":
            canary_split = with_grade["passed"] and not without_grade["passed"]
        per_case.append(
            {
                "id": case.get("id"),
                "answer_path": path,
                "status": status,
                "with_harness": with_grade,
                "without_harness": without_grade,
            }
        )
        print(
            f"  {case.get('id'):24} with={'PASS' if with_grade['passed'] else 'fail'}"
            f"  without={'PASS' if without_grade['passed'] else 'fail'}"
            f"  [{path}/{status}]"
        )

    n = len(cases)
    rates = {k: round(v / n, 3) for k, v in wins.items()}
    delta = round(rates["with_harness"] - rates["without_harness"], 3)
    benchmark = {
        "n": n,
        "with_harness": {"pass_rate": rates["with_harness"], "passed": wins["with_harness"]},
        "without_harness": {
            "pass_rate": rates["without_harness"],
            "passed": wins["without_harness"],
        },
        "delta": {"pass_rate": delta},
        "uplift_canary_split": canary_split,
        "errors": errors,
        "cases": per_case,
    }
    out = report or (suite_path.parent / "benchmark.json")
    out.write_text(json.dumps(benchmark, indent=2))
    print(
        f"\nwith_harness={rates['with_harness']}  without_harness={rates['without_harness']}  "
        f"delta={delta}  canary_split={canary_split}  errors={errors}  -> {out}"
    )

    if gate:
        if errors:
            print(f"GATE FAIL: {errors} case(s) errored (e.g. API/credits) — run is incomplete.")
            return 1
        if delta <= 0:
            print("GATE FAIL: harness did not beat the baseline (delta.pass_rate <= 0).")
            if canary_split is False:
                print("  uplift-canary did NOT split -> the rig is mis-wired, not the harness.")
            return 1
        if rates["with_harness"] < 0.6:
            print("GATE FAIL: with_harness pass_rate below 0.6.")
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="House Harness uplift eval gate")
    ap.add_argument("--suite", nargs="*", default=None, help="(reserved) suite name filter")
    ap.add_argument("--subset", type=int, default=None, help="run only the first N cases")
    ap.add_argument("--heldout", type=str, default=None, help="dir holding validation.json")
    ap.add_argument("--report", type=str, default=None, help="benchmark.json output path")
    ap.add_argument("--gate", action="store_true", help="exit nonzero if delta.pass_rate<=0")
    args = ap.parse_args()

    if args.heldout:
        suite_path = Path(args.heldout) / "validation.json"
    else:
        suite_path = ROOT / "evals" / "evals.json"
    report = Path(args.report) if args.report else None
    return run(suite_path, args.subset, report, args.gate)


if __name__ == "__main__":
    raise SystemExit(main())
