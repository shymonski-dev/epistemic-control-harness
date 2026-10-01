"""Deterministic claim-level certainty control. No model can modify this policy."""
from dataclasses import asdict, dataclass
import json

LEVELS = ("abstain", "tentative", "qualified", "certain")
EVIDENCE = ("none", "weak", "moderate", "strong")


@dataclass(frozen=True)
class Claim:
    id: str
    text: str


@dataclass(frozen=True)
class Verification:
    status: str  # supported, contradicted, unknown
    score: float  # verifier support score, NOT a calibrated probability of truth
    evidence_strength: str
    method: str
    reason: str
    evidence_check: dict | None = None


@dataclass(frozen=True)
class Decision:
    claim_id: str
    epistemic_class: str
    ceiling: str
    verification: Verification


def decide(claim: Claim, verdict: Verification, allowed: str) -> Decision:
    if allowed not in LEVELS or verdict.evidence_strength not in EVIDENCE:
        raise ValueError("Invalid evidence or certainty level")
    if verdict.status not in ("supported", "contradicted", "unknown"):
        raise ValueError("Invalid verification status")
    if not 0 <= verdict.score <= 1:
        raise ValueError("Score must be finite and between zero and one")
    rank = 0
    epistemic = "unknown"
    if verdict.status == "contradicted":
        epistemic = "contradicted"
    elif verdict.status == "supported":
        rank = min(EVIDENCE.index(verdict.evidence_strength),
                   3 if verdict.score >= .9 else 2 if verdict.score >= .7 else 1 if verdict.score >= .5 else 0)
        epistemic = ("unknown", "plausible", "supported", "established")[rank]
    return Decision(claim.id, epistemic, LEVELS[min(rank, LEVELS.index(allowed))], verdict)


def default_plan(decisions: list[Decision]) -> list[dict]:
    return [{"claim_id": d.claim_id, "certainty": d.ceiling} for d in decisions if d.ceiling != "abstain"]


def validate_plan(plan: object, decisions: list[Decision]) -> list[dict]:
    if not isinstance(plan, list):
        raise ValueError("Rewrite must be a list")
    ceilings = {d.claim_id: LEVELS.index(d.ceiling) for d in decisions}
    seen = set()
    for item in plan:
        if not isinstance(item, dict) or set(item) != {"claim_id", "certainty"}:
            raise ValueError("Rewriter can only select claim IDs and certainty levels")
        cid, certainty = item["claim_id"], item["certainty"]
        if not isinstance(cid, str) or cid not in ceilings or cid in seen:
            raise ValueError("Unknown or duplicate claim")
        if certainty not in LEVELS or LEVELS.index(certainty) > ceilings[cid]:
            raise ValueError("Certainty upgrade rejected")
        seen.add(cid)
    return plan


TEMPLATES = {
    "tentative": "Tentative, unverified proposition (not established as fact): {text}",
    "qualified": "Qualified proposition, with limited supporting evidence: {text}",
    "certain": "Proposition supported by the supplied benchmark evidence: {text}",
}
ABSTENTION = "I cannot establish an answer from the available evidence."


def render(plan: list[dict], claims: list[Claim]) -> str:
    texts = {c.id: c.text for c in claims}
    # Quote source propositions so their own certainty language is visibly scoped.
    lines = [TEMPLATES[p["certainty"]].format(text=json.dumps(texts[p["claim_id"]], ensure_ascii=False))
             for p in plan if p["certainty"] != "abstain"]
    return "\n".join(lines) if lines else ABSTENTION


def audit(final: str, plan: list[dict], claims: list[Claim], decisions: list[Decision]) -> dict:
    """Verify the actual emitted text, not a model's self-reported confidence."""
    try:
        validate_plan(plan, decisions)
        if final != render(plan, claims):
            raise ValueError("Final text differs from the controlled renderer")
    except (ValueError, KeyError, TypeError) as exc:
        return {"passed": False, "reason": str(exc)}
    return {"passed": True, "reason": "All emitted claim levels are within evidence ceilings; text matches fixed templates."}


def decision_dict(decision: Decision) -> dict:
    return asdict(decision)
