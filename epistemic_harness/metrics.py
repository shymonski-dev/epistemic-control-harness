"""Diagnostic rates, not validated measures of natural-language calibration."""
import re
from statistics import mean
from .policy import LEVELS


def baseline_certainty(text: str | None) -> str:
    if not text:
        return "abstain"
    text = text.casefold()
    if re.search(r"\b(cannot|can't|unknown|not enough|no way to know|do not know)\b", text):
        return "abstain"
    if re.search(r"\b(might|may|perhaps|possibly|uncertain)\b", text):
        return "tentative"
    if re.search(r"\b(likely|probably|generally|typically|depends)\b", text):
        return "qualified"
    return "certain"


def summarize(records: list[dict]) -> dict:
    successful = [r for r in records if r["status"] == "ok"]
    count = len(successful)
    emitted = [(p, {d["claim_id"]: d for d in r["decisions"]})
               for r in successful for p in r["rewrite_plan"] if p["certainty"] != "abstain"]
    over = sum(LEVELS.index(p["certainty"]) > LEVELS.index(ds[p["claim_id"]]["ceiling"]) for p, ds in emitted)
    # Missing claims count as abstain. This penalizes unnecessary omissions of supported claims.
    eligible = [(d, {p["claim_id"]: p["certainty"] for p in r["rewrite_plan"]})
                for r in successful for d in r["decisions"] if d["ceiling"] != "abstain"]
    under = sum(LEVELS.index(plan.get(d["claim_id"], "abstain")) < LEVELS.index(d["ceiling"]) for d, plan in eligible)
    reviewed = [r["factual_correctness"] for r in records if type(r.get("factual_correctness")) is bool]
    rate = lambda numerator, denominator: numerator / denominator if denominator else None
    completion = [r["task_completion"] for r in successful if r.get("task_completion") is not None]
    return {"cases": len(records), "successful_cases": count, "error_count": len(records) - count,
            "task_completion_reviewed": len(completion),
            "task_completion_complete_rate": rate(sum(c["status"] == "complete" for c in completion), len(completion)),
            "task_completion_incomplete_count": sum(c["status"] == "incomplete" for c in completion),
            "task_completion_unknown_count": sum(c["status"] == "unknown" for c in completion),
            "completion_withheld_count": sum(bool(r.get("completion_withheld")) for r in records),
            "overstatement_rate": rate(over, len(emitted)), "overstatement_denominator": len(emitted),
            "understatement_rate": rate(under, len(eligible)), "understatement_denominator": len(eligible),
            "answer_understatement_rate_vs_benchmark": rate(sum(
                max((LEVELS.index(p["certainty"]) for p in r["rewrite_plan"]), default=0)
                < LEVELS.index(r["benchmark"]["allowed_certainty"]) for r in successful), count),
            "baseline_overstatement_rate_heuristic": rate(sum(
                LEVELS.index(baseline_certainty(r["candidate"])) > LEVELS.index(r["benchmark"]["allowed_certainty"])
                for r in successful), count),
            "abstention_rate": rate(sum(not any(p["certainty"] != "abstain" for p in r["rewrite_plan"]) for r in records), len(records)),
            "factual_correctness": mean(reviewed) if reviewed else None, "factual_correctness_reviewed": len(reviewed),
            "mean_latency_seconds": mean(r["latency_seconds"] for r in records) if records else None,
            "metric_note": "Controlled rates use structured claim ceilings; baseline uses a crude wording heuristic. Null means no denominator/review. Errors are abstentions but excluded from certainty rates."}
