# Epistemic-control harness: optional Jev reviewer

Small, inspectable Python 3.10+ project; standard library only. No installation or training required. Run commands from this directory.

The language layer must never silently upgrade the certainty of underlying evidence. The audit enforces assessed certainty ceilings; evidence assessments can still be wrong.

```sh
python3 -m unittest discover -s tests -q
python3 -m epistemic_harness --config config.offline.json --demo --output runs/demo.jsonl
python3 validation/summarize_validation.py
python3 validation/check_recorded_replay.py
```

The tests and recorded replay checks are offline. The demo exercises the 20-question starter benchmark.

## Live use

Start LM Studio's OpenAI-compatible server at `http://localhost:1234/v1` with the configured Qwen model available. Save `OPENROUTER_API_KEY=your-key` in an ignored `.env`, or export it. On this Mac, the existing file can be reused with `--env-file ../epistemic-harness/.env`. Never put a key in model prompts or configuration JSON.

This example reuses recorded candidates while obtaining fresh evidence maps, completion judgments and Jev reviews:

```sh
python3 -m epistemic_harness --config config.jev.json \
  --benchmark benchmarks/replay-cases.jsonl --replay runs/replay-baseline.jsonl \
  --env-file .env --limit 4 --output runs/new-jev.jsonl
```

`config.json` retains the prior stage 3 alignment experiment. Jev is opt-in through `config.jev.json`: local generator/extractor, GPT-4.1 evidence mapping/completion, deterministic rendering, and a separate `decision_reviewer` using `typesafe/jev-1.13`. Assign generator/verifier/rewriter independently to `local` or `openrouter`; `.env.example` documents endpoint and model overrides. Jev uses OpenRouter's native `/api/v1/systemone` endpoint rather than chat completions. Endpoint redirects are rejected.

Question → candidate → claim extraction → verification → epistemic class → deterministic certainty policy → controlled rewrite → task completion → final certainty audit → JSONL.

The first reviewer maps every assertion to supplied reference evidence. Jev receives the full candidate, reference and exact spans, without first-review verdicts, explanations, quotes or gold labels. Support or contradiction survives only on agreement; disagreement becomes unknown. Jev cannot repair missing quotes, promote an initial unknown, raise the first score or raise evidence strength. Its probabilities and confidence are logged separately; model-only support stays weak/tentative. Checked arithmetic stays in Python with the existing limited grammar.

Each case needs question, expected answer, evidence strength, allowed certainty and verification method; requirement checks are separate from factual evidence. JSONL retains decisions, evidence provenance, raw typed Jev answers, usage, completion, final text, audits and latency. Metrics include overstatement, understatement, abstention and a factual-correctness placeholder that remains null until independently reviewed.

See `VALIDATION.md` for results and limitations. The 24-case frozen experiment is preserved in `runs/`; `validation/run_replay.py` refuses to overwrite it. The archive contains no API keys. Jev remains experimental.
