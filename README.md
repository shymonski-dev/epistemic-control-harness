# Epistemic harness — stage 3 experiment

Standard-library Python project, based on frozen consolidated stage 2. No training. Run from this directory with Python 3.10+.

The language layer must never silently upgrade the certainty of underlying evidence. The renderer's audit checks compliance with assessed ceilings; model assessments can still be wrong.

## Run

```sh
python3 -m unittest discover -s tests
python3 -m epistemic_harness --config config.offline.json --demo --output runs/demo.jsonl
python3 -m epistemic_harness --benchmark benchmarks/fresh-tasks.jsonl --env-file .env --output runs/live.jsonl
```

For live runs, start LM Studio at `http://localhost:1234/v1` with `qwen3-1.7b-mlx` available. Put `OPENROUTER_API_KEY=...` in an ignored `.env`, or export it. This Mac can reuse `--env-file ../epistemic-harness/.env`. Keys are excluded from the package. Endpoint and model environment options are in `.env.example`.

`config.json` enables the experimental alignment protocol; `config.baseline.json` uses stage 2 evidence mapping with the same role settings and token budget. Both use local generation, OpenRouter `openai/gpt-4.1` verification/completion and deterministic rendering. Roles can be assigned independently, but the default makes no rewriter-model call. Arithmetic checking, policy and renderer are unchanged from stage 2.

Question → candidate → exact extraction → whole-answer verification → epistemic class and ceiling → fixed rewrite → requirement coverage → final text audit → JSONL.

The proposed verifier maps the full answer, then makes a second call judging subject, relationship, scope and modality. The second reviewer receives reference and exact spans, without first-review statuses, evidence quotes or explanations. Python retains support only when both reviews agree, all dimensions are preserved, an exact reference quote exists, and no counterexample is supplied. Unresolved alignment becomes unknown. Unknown first-pass assessments cannot become supported. Both reviews use the same model: agreement is not independent semantic proof. Model support remains weak/tentative.

Each live case needs curated `expected_answer`, `requirements`, evidence strength and allowed certainty. Arithmetic uses `check: {"type":"arithmetic_derivation","expression":"18 * 7"}`; a failed declaration/proof never falls back to models. The user-confirmed benchmark contract accepts original expression and numeric result, with intermediate working optional. Do not confuse proof correctness with completion of other task requirements.

## Inspect recorded validation

```sh
python3 validation/summarize_validation.py
python3 -m epistemic_harness --benchmark benchmarks/fresh-tasks.jsonl --replay runs/fresh-generation.jsonl --env-file .env --output runs/new-review.jsonl
```

Logs append; replay requires identical benchmark metadata. The original generation's extraction is retained, while verification always checks the entire answer. `validation/run_validation.py --phase evidence|arithmetic|fresh` is the bounded recorded evaluation runner; it refuses to overwrite existing logs. Runtime/evidence and task-contract freezes precede their respective inference phases.

Metrics report support errors, unsupported emission, useful retention, incorrect contradiction, completion, abstention, structured over/understatement and latency. Factual correctness remains null unless separately reviewed. See `PLAN.md` and `VALIDATION.md` for scope, results, limitations and adoption decision. This directory does not change stage 2 defaults.
