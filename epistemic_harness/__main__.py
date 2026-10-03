import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid
from .client import Client
from .metrics import summarize
from .pipeline import run_case
from .policy import EVIDENCE, LEVELS
from .environment import load_env_file

ROOT = Path(__file__).resolve().parent.parent


def load_cases(path: Path) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    seen = set()
    for case in cases:
        required = ("id", "question", "expected_answer", "verification_method")
        if any(not isinstance(case.get(k), str) or not case[k].strip() for k in required):
            raise ValueError("Benchmark needs non-empty id, question, expected_answer, verification_method")
        if case["id"] in seen:
            raise ValueError("Duplicate benchmark ID")
        seen.add(case["id"])
        if case.get("evidence_strength") not in EVIDENCE or case.get("allowed_certainty") not in LEVELS:
            raise ValueError("Invalid benchmark evidence/certainty")
        for key in ("accepted_claims", "rejected_claims"):
            if not isinstance(case.get(key, []), list) or any(not isinstance(s, str) or not s.strip() for s in case.get(key, [])):
                raise ValueError("Benchmark claim aliases must be lists of non-empty text")
    if not cases:
        raise ValueError("Benchmark is empty")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the epistemic-control starter benchmark")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "benchmarks/starter.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/results.jsonl")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--demo", action="store_true", help="Scripted offline smoke test; no inference or network")
    parser.add_argument("--replay", type=Path, help="Reuse candidates and extracted claims from the latest run in this JSONL log")
    parser.add_argument("--env-file", type=Path, help="Load a local key=value file; existing environment wins; no shell execution")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.demo and args.replay:
        parser.error("--demo and --replay cannot be combined")
    try:
        if args.env_file:
            load_env_file(args.env_file)
        config = json.loads(args.config.read_text())
        if config.get("verification_mode") not in ("benchmark", "model", "deterministic", "arithmetic_derivation", "stage2"):
            raise ValueError("verification_mode must be benchmark, model, deterministic, arithmetic_derivation or stage2")
        if type(config.get("claim_bridge", False)) is not bool:
            raise ValueError("claim_bridge must be a Boolean")
        if config.get("task_completion", "off") not in ("off", "review", "require"):
            raise ValueError("task_completion must be off, review or require")
        if config.get("completion_protocol", "global") not in ("global", "requirements"):
            raise ValueError("completion_protocol must be global or requirements")
        if config.get("rewrite_mode", "model") not in ("model", "deterministic"):
            raise ValueError("rewrite_mode must be model or deterministic")
        if config.get("verification_protocol", "direct") not in ("direct", "evidence_check", "entailment", "evidence_map", "evidence_alignment", "evidence_jev"):
            raise ValueError("verification_protocol must be direct, evidence_check, entailment, evidence_map, evidence_alignment or evidence_jev")
        if config.get("verification_protocol") == "evidence_jev":
            from .jev_client import validate_settings
            validate_settings(config.get("decision_reviewer"))
        roles = config.get("roles")
        if not isinstance(roles, dict) or set(roles) != {"generator", "verifier", "rewriter"}:
            raise ValueError("Config requires generator, verifier and rewriter roles")
        for role in roles.values():
            if not isinstance(role, dict) or role.get("provider") not in ("local", "openrouter"):
                raise ValueError("Each role needs a local or openrouter provider")
            for key in ("model", "model_env", "prompt_suffix"):
                if key in role and not isinstance(role[key], str):
                    raise ValueError(f"Role {key} must be text")
            if "response_format" in role and not isinstance(role["response_format"], dict):
                raise ValueError("Role response_format must be an API format object")
        for key, default in (("timeout_seconds", 60), ("max_tokens", 1024)):
            value = config.get(key, default)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
        cases = load_cases(args.benchmark)
        if args.demo and any(not isinstance(c.get("demo_candidate"), str) or not c["demo_candidate"].strip() for c in cases):
            raise ValueError("Demo cases require demo_candidate text")
        if args.limit:
            cases = cases[:args.limit]
        replay = {}
        if args.replay:
            rows = [json.loads(line) for line in args.replay.read_text().splitlines() if line.strip()]
            rows = [r for r in rows if "case_id" in r]
            if not rows:
                raise ValueError("Replay log contains no case records")
            last_run = rows[-1]["run_id"]
            for row in rows:
                if row["run_id"] == last_run:
                    if row["case_id"] in replay:
                        raise ValueError("Duplicate case in replay run")
                    replay[row["case_id"]] = row
            for case in cases:
                row = replay.get(case["id"])
                if row is None or row["status"] != "ok" or row["benchmark"] != case:
                    raise ValueError("Replay requires successful records with the same benchmark fixtures")
        client = Client(config)
        records = []
        run_id = str(uuid.uuid4())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Append rather than overwrite, so experiments remain inspectable.
        with args.output.open("a", encoding="utf-8") as log:
            for case in cases:
                record = run_case(case, client, config["verification_mode"], args.demo, replay.get(case["id"]))
                record.update(run_id=run_id, timestamp=datetime.now(timezone.utc).isoformat(),
                              demo=args.demo, config=client.public_settings())
                log.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                log.flush()
                records.append(record)
                print(f'{case["id"]}: {record["status"]} | {record["final"]}')
            summary = summarize(records)
            log.write(json.dumps({"type": "summary", "run_id": run_id, "metrics": summary}) + "\n")
        print(json.dumps(summary, indent=2))
        return 1 if summary["error_count"] else 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Configuration/logging error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
