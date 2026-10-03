# Jev integration validation and handover

The optional integration is implemented and the bounded evaluation is complete. Keep Jev opt-in. The replay catches the known unsupported reading/observation substitution without additional useful-answer loss, but evidence classification and completion errors remain.

## Recorded comparison

The experiment reuses 24 historical candidate answers across 12 paired fixtures: eight development and 16 previously held-out cases. For this Jev experiment all are regression cases, not a new unseen holdout. Initial evidence maps and requirement-completion judgments are frozen from the stage 3 baseline. Only Jev makes live calls; the baseline uses cached assessments.

| Measure | Frozen baseline | Baseline + Jev |
|---|---:|---:|
| Supported, complete answers emitted / eligible | 11/12 | 11/12 |
| Unsupported answers emitted | 1 | 0 |
| Incomplete answers emitted | 1 | 0 |
| Combined evidence labels matching fixture labels | 18/24 | 21/24 |
| Unknown incorrectly called contradicted | 5 | 3 |
| Abstentions | 12/24 | 13/24 |
| Final certainty audits passed | 24/24 | 24/24 |
| Pipeline errors | 0 | 0 |

Jev's raw whole-answer labels also match 21/24, aggregating spans as contradicted if any span is contradicted, supported if all are supported, otherwise unknown. Remaining incorrect contradictions are p04b, p06b and p10b. Jev corrected p07b and p11b to unknown, and withheld p01b's reading/observation substitution. Supported p02a is still withheld by the frozen completion reviewer, which demands information about unspecified opening days. Evidence support and task completion are separate failure sources.

Only p01b and p02b evidence labels were independently confirmed by the user. Other labels were authored by the assistant before the original inference and remain provisional. The sample is small, paired and familiar. Agreement between different models does not establish statistical independence or entailment proof. These results do not establish general accuracy or calibration.

All emitted model-supported answers remain tentative. Structured overstatement against assessed ceilings is zero in both arms. Audit success establishes compliance with those ceilings, not truth. Factual correctness remains null in runtime logs. Diagnostic understatement and benchmark-certainty rates have different denominators; see `validation/results.json` rather than interpreting them as semantic accuracy.

The replay used 24 requests for 27 span decisions, with 13,100 reported input tokens and reported cost of approximately $0.0005502. Three earlier access checks brought the integration's live request count to 27. The requested model resolved to `typesafe/jev-1.13-20260917`. Mean Jev verification-stage latency was 0.515242 seconds; nearest-rank p95 was 0.938460 seconds. These include local overhead. Cached baseline timing cannot support an end-to-end speed comparison. No retries, new generation or fresh chat-model calls occurred in this comparison.

## Code check and release verification

The quick code review reproduced two defects and both were repaired: an enormous valid JSON integer could cause an uncaught OverflowError; default HTTP redirects could forward authentication beyond the configured endpoint. Numeric validation now rejects unrepresentable values. Both native Jev and the general chat transport reject redirects before forwarding credentials. Regression tests cover the pipeline's fail-closed error record and both endpoint paths.

The live replay preceded these transport/validation repairs. Its exact 35 frozen input files and original manifest are preserved in `validation/evaluation-source.zip`; `validation/freeze.json` describes that original evaluation. Assessment prompts, combination rules, scores, evidence caps and policy were not tuned to the results. `validation/release-freeze.json` hashes the repaired runtime and validation scripts. The offline recorded-response check runs all 48 pipeline records through the repaired code and verifies unchanged verdicts, plans, completion and final audits, including each Jev request hash. It makes no network calls.

107 tests pass, including the 87 inherited tests and 20 Jev/transport tests. The clean ZIP is checked with the same tests, 20 offline demo cases and recorded replay reproduction. `validation/package-check.json` records those checks; `artifact-manifest.json` records deliverable hashes. Earlier frozen projects are preserved and credentials are excluded.

## Handover

Use Jev only as an optional second evidence reviewer. The native adapter, independent reviewer configuration, blinded span checks, strict response validation and public traces are complete. No new dependencies, training, Bayesian thresholds, wider arithmetic grammar or retrieval system were added. This private GitHub repository contains the opt-in Jev integration. The previous stage 3 version is preserved in Git history.

A future decision about promotion needs a separately approved, independently labelled unseen evaluation that distinguishes evidence errors from completion errors. That is outside this integration. The unresolved errors are documented rather than hidden by retries, relaxed guards or increased certainty.
