# Stage 3: reference alignment experiment

Stage 3 is implemented and evaluated as an experiment. It catches the known reading/observation substitution, but the recorded results do not justify replacing stage 2: useful retention dropped in development because of one mapping failure, and epistemic classification errors remain. No runtime prompts were tuned after inference began.

## Scope and implementation

The standard-library project adds a second reference review of subject, relationship, scope and modality. The reviewer receives exact spans and reference without first-review verdicts or explanations. Python requires agreement, all dimensions preserved, exact reference provenance and no counterexample before retaining support. Disagreement becomes unknown. Unknown initial support cannot be upgraded. Same-model agreement remains correlated and model-only evidence stays weak/tentative; this is not a formal entailment checker.

Whole-answer routing, arithmetic checking, policy and renderer are unchanged. Arithmetic failures never fall back to models. The user selected a clearer arithmetic contract: original expression plus numeric result suffices, and intermediate working is optional. Both plain equalities and longer checked derivations are accepted under that contract.

87 offline tests pass, including 12 new alignment tests covering uncertainty, changed dimensions, quote provenance, counterexamples, missing/duplicate IDs, blind payloads, fail-closed malformed responses, alias bypass prevention and unchanged arithmetic routing. The 20-case offline CLI smoke test passes.

## Frozen comparison

Four development pairs (8 answers), eight held-out pairs (16 answers), four arithmetic fixtures and six fresh tasks were defined before their inference. Runtime, prompts, configs, paired labels and tests are hashed in `validation/freeze.json`. Arithmetic/fresh metadata was separately frozen in `validation/task-freeze.json` after the user clarified the contract and before those phases ran. The original plan is retained alongside that decision.

The user independently confirmed that the reading/observation substitution and everyday-gallery claim are unknown, and that intermediate working should be optional. Remaining fixed labels are assistant-authored and provisional. Gold labels are excluded from model payloads. The holdout uses familiar failure categories and is not an independently sampled research benchmark.

Both arms use the same GPT-4.1 role and 2048-token budget. This increases the token limit relative to the prior stage 2 run; historical counts are not interchangeable. Fixed candidate answers are identical across arms. Evidence mapping is called separately in each arm, so stochastic mapping/completion differences can contribute to results. Only the second pass is blind to the first verdict; the first map determines its spans.

| Development, 8 answers | Stage 2 protocol | Alignment |
|---|---:|---:|
| Supported, complete emitted / eligible | 3/4 | 2/4 |
| Unsupported emitted | 1 | 0 |
| Incomplete emitted | 1 | 0 |
| Evidence labels matched | 6/8 | 6/8 |
| Pipeline errors | 0 | 1 |
| Mean review latency | 2.338 s | 3.750 s |

The baseline emitted p01b, substituting current observation for the unavailable reading. The alignment reviewer marked the subject unresolved and withheld it. On p02b, the initial map called unspecified other days a contradiction; the second review corrected that to unknown. Both arms wrongly withheld supported p02a (Thursday opening time), because completion review demanded a broader schedule despite unspecified other days. This is residual model interpretation of task requirements.

Alignment-arm p04a, a supported possibility paraphrase, failed with `Evidence map omitted or altered claim text`. The first mapping response failed its structural guard before alignment. The whole pipeline abstained with status error. The log remains intact; no replacement run or automatic retry hides the failure. This observed retention loss cannot be attributed solely to the second-pass algorithm.

| Held-out pairs, 16 answers | Stage 2 protocol | Alignment |
|---|---:|---:|
| Supported, complete emitted / eligible | 8/8 | 8/8 |
| Unsupported emitted | 0 | 0 |
| Supported, complete withheld | 0 | 0 |
| Evidence labels matched | 12/16 | 12/16 |
| Unknown incorrectly labelled contradicted | 4 | 4 |
| Pipeline errors | 0 | 0 |
| Mean review latency | 2.218 s | 3.948 s |

The held-out emission conditions pass, but both arms already pass them; there is no held-out retention or unsupported-emission improvement. Incorrect contradictions persist, with different case IDs in each arm. Labels for modality and sufficiency can also depend on whether wording describes evidence or the underlying world, so these counts need broader human adjudication before treating them as ground truth. Withholding unsupported claims is useful but does not demonstrate accurate epistemic classification.

All four declared arithmetic fixtures were emitted correctly in each arm. Strong-input multiplication was certain; weak-input division remained tentative even with exact checking and score 1. Minimal equalities and longer chains both passed completion under the user-confirmed contract. Arithmetic code and grammar were not broadened.

## Fresh generation

Local Qwen generated six answers once. The full generation log was hashed before either replay arm. Both arms then reviewed the same entire answers. Generation-stage abstentions in `runs/fresh-generation.jsonl` collect candidates with empty benchmark aliases; they are not evaluation failures.

Both arms emitted all six answers. Five are clearly supported and complete under assistant review. The sixth, fresh p06a, says: “Badge approval is necessary but not sufficient for opening the door.” Its reference establishes a necessary condition and says approval alone does not establish whether the door opens. This may faithfully describe evidence insufficiency, or overstate an actual non-sufficiency rule. Human review was requested; the recorded provisional conservative label is unknown. Under that label, both arms emit one unestablished answer; under the supported paraphrase interpretation, both retain 6/6 with no unsupported emission. Neither interpretation shows an advantage for alignment.

Unlike the fixed Thursday paraphrase, the fresh Thursday wording passed completion in both arms. This inconsistent treatment of equivalent schedules is another limit of model-based coverage checking.

Mean fresh review latency was 2.739 s for baseline and 7.127 s for alignment. These six sequential calls are too small a sample for a reliable performance comparison. Replay excludes reused generation/extraction; per-case generation latency is recorded separately and can be added for composed totals. No token-cost measurement is claimed.

## Certainty and interpretation

All 67 successful review records pass final text audits; one failed record abstains with a failed pipeline audit. There are no observed structured certainty upgrades. Model-supported outputs remain tentative, and checked arithmetic preserves source strength and allowed certainty. This measures renderer compliance with assessed evidence ceilings, not factual truth or semantic assessment correctness.

Understatement counts supported claims withheld by completion even where withholding may be appropriate. Unsupported emission and incorrect contradiction are reported separately. Factual correctness remains null in runtime logs; assistant support/coverage review does not silently become a general correctness score.

Recompute results offline with `python3 validation/summarize_validation.py`. It checks both freezes and the generation hash before reconstructing `validation/results.json`. Logs preserve decisions, maps, alignment dimensions, counterexamples, quotes, completion, final text and public model settings. Alignment traces preserve the initial overall status and final per-span statuses; they do not contain a separate full raw first-pass response archive.

## Handover decision

Keep stage 3 experimental. The held-out gate passes, but development retention regresses, one model-format failure remains, contradiction classification is not improved overall, and fresh sufficiency interpretation remains ambiguous. Stage 2 directories/defaults are untouched. The next investigation should distinguish assessment errors from completion errors using clearer independently adjudicated semantic contracts, rather than loosening guards or claiming same-model agreement proves entailment. Training and broader mathematical reasoning remain out of scope.
