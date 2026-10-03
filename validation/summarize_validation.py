"""Recompute the recorded replay results offline; write only results.json.

Run from any directory: python3 validation/summarize_validation.py
The original evaluation source is checked inside evaluation-source.zip because
the deliverable's transport was repaired after the recorded live evaluation.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ("supported", "contradicted", "unknown")
LEVELS = ("abstain", "tentative", "qualified", "certain")
EVIDENCE = ("none", "weak", "moderate", "strong")
sys.dont_write_bytecode = True


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_rows(relative_path):
    data = (ROOT / relative_path).read_bytes()
    return [json.loads(line) for line in data.splitlines() if line.strip()], digest(data)


def validate_snapshot():
    manifest_data = (ROOT / "validation/freeze.json").read_bytes()
    manifest = json.loads(manifest_data)
    hashes = manifest["sha256"]
    archive_path = ROOT / "validation/evaluation-source.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Evaluation snapshot has duplicate ZIP member names")
        if archive.read("validation/freeze.json") != manifest_data:
            raise ValueError("Evaluation snapshot freeze manifest differs from freeze.json")
        for relative_path, expected in hashes.items():
            if digest(archive.read(relative_path)) != expected:
                raise ValueError("Evaluation snapshot hash mismatch: " + relative_path)
    # Gold labels, replay inputs, and the diagnostic implementation used below
    # must still match the original evaluated source, independent of repairs.
    for relative_path in ("benchmarks/evidence-pairs.jsonl",
                          "validation/frozen-replay.jsonl",
                          "epistemic_harness/metrics.py", "epistemic_harness/policy.py"):
        if digest((ROOT / relative_path).read_bytes()) != hashes[relative_path]:
            raise ValueError("Recorded evaluation input changed: " + relative_path)
    return {
        "verified": True,
        "method": "Check every original freeze.json hash against its ZIP member",
        "snapshot_path": "validation/evaluation-source.zip",
        "snapshot_sha256": digest(archive_path.read_bytes()),
        "manifest_path": "validation/freeze.json",
        "manifest_sha256": digest(manifest_data),
        "frozen_files_verified": len(hashes),
        "note": "The ZIP contains original evaluation source, before later transport repairs.",
    }


def emitted(row):
    return any(part["certainty"] != "abstain" for part in row["rewrite_plan"])


def verdict(row):
    if len(row["decisions"]) != 1:
        raise ValueError("Recorded replay must have one whole-answer decision per case")
    return row["decisions"][0]["verification"]


def raw_jev_label(row):
    choices = [part["jev"]["choice"]
               for part in verdict(row)["evidence_check"]["parts"]]
    if not choices or any(choice not in STATUSES for choice in choices):
        raise ValueError("Recorded Jev span labels are missing or invalid")
    return ("contradicted" if "contradicted" in choices else
            "supported" if all(choice == "supported" for choice in choices) else
            "unknown")


def fraction(numerator, denominator, case_ids=None):
    result = {"numerator": numerator, "denominator": denominator,
              "rate": numerator / denominator if denominator else None}
    if case_ids is not None:
        result["case_ids"] = sorted(case_ids)
    return result


def label_metrics(predictions, gold):
    correct = [case_id for case_id, predicted in predictions.items()
               if predicted == gold[case_id]["gold_support"]]
    errors = [{"case_id": case_id, "gold": gold[case_id]["gold_support"],
               "predicted": predicted}
              for case_id, predicted in sorted(predictions.items())
              if predicted != gold[case_id]["gold_support"]]
    wrong_contradictions = [error["case_id"] for error in errors
                            if error["predicted"] == "contradicted"]
    confusion = {actual: {predicted: 0 for predicted in STATUSES} for actual in STATUSES}
    for case_id, predicted in predictions.items():
        confusion[gold[case_id]["gold_support"]][predicted] += 1
    return {
        "accuracy": fraction(len(correct), len(predictions)),
        "errors": errors,
        "wrong_contradictions": {"count": len(wrong_contradictions),
                                  "case_ids": wrong_contradictions},
        "confusion_gold_then_predicted": confusion,
    }


def arm_metrics(rows, gold):
    useful = [row for row in rows if gold[row["case_id"]]["gold_support"] == "supported"
              and gold[row["case_id"]]["gold_coverage"] == "complete"]
    retained = [row["case_id"] for row in useful if emitted(row)]
    unsupported = [row["case_id"] for row in rows if emitted(row)
                   and gold[row["case_id"]]["gold_support"] != "supported"]
    unsupported_candidates = sum(gold[row["case_id"]]["gold_support"] != "supported"
                                 for row in rows)
    emission_count = sum(emitted(row) for row in rows)
    return {
        "useful_retention": fraction(len(retained), len(useful), retained),
        "useful_withheld_case_ids": sorted(row["case_id"] for row in useful if not emitted(row)),
        "unsupported_emissions": {
            "count": len(unsupported), "case_ids": sorted(unsupported),
            "among_emissions": fraction(len(unsupported), emission_count),
            "among_unsupported_candidates": fraction(len(unsupported), unsupported_candidates),
        },
        "emissions": fraction(emission_count, len(rows)),
        "abstentions": fraction(len(rows) - emission_count, len(rows)),
        "combined_evidence_labels": label_metrics(
            {row["case_id"]: verdict(row)["status"] for row in rows}, gold),
        "audit_passes": fraction(sum(row["audit"]["passed"] is True for row in rows), len(rows)),
        "pipeline_errors": {"count": sum(row["status"] != "ok" for row in rows),
                            "case_ids": sorted(row["case_id"] for row in rows if row["status"] != "ok")},
    }


def case_arm(row, include_jev=False):
    verification = verdict(row)
    result = {
        "pipeline_status": row["status"], "verification_status": verification["status"],
        "support_score": verification["score"], "evidence_strength": verification["evidence_strength"],
        "certainty_ceiling": row["decisions"][0]["ceiling"],
        "emitted": emitted(row),
        "emitted_certainty_levels": [part["certainty"] for part in row["rewrite_plan"]
                                     if part["certainty"] != "abstain"],
        "completion_status": row["task_completion"]["status"],
        "completion_withheld": row["completion_withheld"],
        "audit_passed": row["audit"]["passed"],
        "recorded_case_latency_seconds": row["latency_seconds"],
        "recorded_verification_latency_seconds": row["stage_latency_seconds"]["verification"],
    }
    if include_jev:
        result["raw_jev_status"] = raw_jev_label(row)
        result["span_labels"] = [
            {"text": part["text"], "initial_status": part["initial_status"],
             "raw_jev_status": part["jev"]["choice"], "combined_status": part["status"]}
            for part in verification["evidence_check"]["parts"]]
    return result


def latency_metrics(rows):
    values = sorted(row["stage_latency_seconds"]["verification"] for row in rows)
    if not values or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
                         for value in values):
        raise ValueError("Invalid recorded Jev verification latency")
    position = (len(values) - 1) * .95
    lower = int(position)
    interpolated = values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)
    return {
        "count": len(values), "mean_seconds": mean(values),
        "p95_seconds": values[math.ceil(.95 * len(values)) - 1],
        "p95_method": "nearest rank: sorted[ceil(0.95 * n) - 1]",
        "p95_linear_interpolation_seconds": interpolated,
        "minimum_seconds": values[0], "maximum_seconds": values[-1],
        "scope": "Recorded Jev verification stage, including local mapping and validation overhead",
        "note": "This is not isolated network time. Cached baseline timing cannot establish an end-to-end speed comparison.",
    }


def main():
    snapshot = validate_snapshot()
    fixtures, fixture_hash = read_rows("benchmarks/evidence-pairs.jsonl")
    gold = {row["id"]: row for row in fixtures}
    if len(gold) != len(fixtures):
        raise ValueError("Duplicate fixture IDs")
    sources, frozen_replay_hash = read_rows("validation/frozen-replay.jsonl")
    frozen = {row["case_id"]: row for row in sources}
    if set(frozen) != set(gold) or len(frozen) != len(sources):
        raise ValueError("Frozen replay IDs differ from fixtures")
    arms, source_logs = {}, {}
    for arm in ("baseline", "jev"):
        path = "runs/replay-" + arm + ".jsonl"
        records, log_hash = read_rows(path)
        rows = [row for row in records if "case_id" in row]
        indexed = {row["case_id"]: row for row in rows}
        if set(indexed) != set(gold) or len(indexed) != len(rows):
            raise ValueError("Replay IDs differ from fixtures: " + arm)
        run_ids = {row["run_id"] for row in rows}
        if len(run_ids) != 1:
            raise ValueError("Replay log contains multiple runs: " + arm)
        for case_id, row in indexed.items():
            if row["candidate"] != gold[case_id]["fixed_candidate"] or row["candidate"] != frozen[case_id]["candidate"]:
                raise ValueError("Recorded candidate differs from frozen fixture: " + case_id)
            if arm == "baseline" and (row["final"] != frozen[case_id]["historical_final"]
                                      or row["rewrite_plan"] != frozen[case_id]["historical_plan"]):
                raise ValueError("Baseline differs from frozen historical result: " + case_id)
        arms[arm] = [indexed[case_id] for case_id in sorted(gold)]
        source_logs[arm] = {"path": path, "sha256": log_hash,
                            "run_id": next(iter(run_ids)), "case_records": len(rows)}
    sys.path.insert(0, str(ROOT))
    from epistemic_harness.metrics import summarize

    metrics = {arm: arm_metrics(rows, gold) for arm, rows in arms.items()}
    metrics["jev"]["raw_jev_labels"] = label_metrics(
        {row["case_id"]: raw_jev_label(row) for row in arms["jev"]}, gold)
    metrics["jev"]["recorded_latency"] = latency_metrics(arms["jev"])
    reported_usage_data = (ROOT / "validation/usage.json").read_bytes()
    reported_usage = json.loads(reported_usage_data)
    usages = [verdict(row)["evidence_check"]["jev"]["usage"] for row in arms["jev"]]
    recomputed_usage = {"requests": len(usages),
                        "input_tokens": sum(usage["input_tokens"] for usage in usages),
                        "output_tokens": sum(usage["output_tokens"] for usage in usages),
                        "reported_cost_usd": sum(usage["cost"] for usage in usages)}
    if (recomputed_usage["requests"] != reported_usage["requests"]
            or recomputed_usage["input_tokens"] != reported_usage["input_tokens"]
            or not math.isclose(recomputed_usage["reported_cost_usd"], reported_usage["reported_cost_usd"],
                                rel_tol=1e-12, abs_tol=1e-15)
            or reported_usage["unknown_usage"] is not False):
        raise ValueError("Recorded usage does not match response usage")
    per_case = []
    increases = Counter({key: 0 for key in ("support_score", "evidence_strength", "certainty_ceiling", "rendered_certainty")})
    for baseline, jev in zip(arms["baseline"], arms["jev"]):
        case_id = baseline["case_id"]
        fixture = gold[case_id]
        a, b = case_arm(baseline), case_arm(jev, include_jev=True)
        increases["support_score"] += b["support_score"] > a["support_score"]
        increases["evidence_strength"] += EVIDENCE.index(b["evidence_strength"]) > EVIDENCE.index(a["evidence_strength"])
        increases["certainty_ceiling"] += LEVELS.index(b["certainty_ceiling"]) > LEVELS.index(a["certainty_ceiling"])
        increases["rendered_certainty"] += max((LEVELS.index(level) for level in b["emitted_certainty_levels"]), default=0) > max((LEVELS.index(level) for level in a["emitted_certainty_levels"]), default=0)
        per_case.append({"case_id": case_id, "pair_id": fixture["pair_id"], "split": fixture["split"],
                         "gold_support": fixture["gold_support"], "gold_coverage": fixture["gold_coverage"],
                         "candidate": baseline["candidate"], "baseline": a, "jev": b})
    result = {
        "schema_version": 1,
        "design": {"cases": len(gold), "pairs": len({row["pair_id"] for row in fixtures}),
                   "split_counts": dict(sorted(Counter(row["split"] for row in fixtures).items())),
                   "gold_support_counts": dict(sorted(Counter(row["gold_support"] for row in fixtures).items())),
                   "requested_jev_models": sorted({verdict(row)["evidence_check"]["jev"]["requested_model"] for row in arms["jev"]}),
                   "returned_jev_models": sorted({verdict(row)["evidence_check"]["jev"]["model"] for row in arms["jev"]}),
                   "note": "Candidates, initial evidence maps and completion checks frozen; Jev decision calls were the only live inference."},
        "metric_definitions": {
            "useful_retention": "Final emission among gold supported AND gold complete cases",
            "unsupported_emission": "Final emission where gold_support is unknown or contradicted",
            "emission": "At least one rewrite-plan entry with certainty other than abstain",
            "combined_label": "Final verification.status before the separate completion gate",
            "raw_jev_label": "Contradicted if any span contradicted; supported if all spans supported; unknown otherwise",
            "wrong_contradiction": "Predicted contradicted where gold_support is supported or unknown",
            "audit_pass": "Renderer and policy consistency; does not establish semantic correctness",
        },
        "metrics": metrics,
        "diagnostic_rates": {"note": "Existing summarize() diagnostics kept separate from gold-label metrics. Baseline latency is cached replay time, not end-to-end inference latency.",
                             **{arm: summarize(rows) for arm, rows in arms.items()}},
        "monotonicity_increase_counts": dict(increases),
        "per_case": per_case,
        "source_logs": source_logs,
        "source_inputs": {
            "fixtures": {"path": "benchmarks/evidence-pairs.jsonl", "sha256": fixture_hash},
            "frozen_replay": {"path": "validation/frozen-replay.jsonl", "sha256": frozen_replay_hash},
        },
        "freeze_validation": snapshot,
        "usage": {"path": "validation/usage.json", "sha256": digest(reported_usage_data),
                  "recorded": reported_usage, "recomputed_from_responses": recomputed_usage,
                  "recorded_totals_match": True},
        "limitations": [
            "One replay of 24 fixed cases across 12 pairs; eight development and 16 holdout cases.",
            "Only p01b/p02b labels were human-confirmed; remaining gold labels were assistant-authored before inference.",
            "A fixed replay isolates the added decision gate and does not measure newly generated answers or general factual accuracy.",
            "Useful p02a remains withheld by a frozen completion judgment although both evidence arms classify it supported.",
            "Recorded latency includes local verification overhead; cached baseline timing does not support an end-to-end speed comparison.",
            "Three unknown cases remain wrongly labelled contradicted; audit passes measure policy compliance rather than semantics.",
            "The live evaluation used the source archived in evaluation-source.zip, before later transport repairs.",
        ],
    }
    output = ROOT / "validation/results.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print("Recomputed validation/results.json from recorded logs; no network calls.")


if __name__ == "__main__":
    main()
