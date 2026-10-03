# Jev integration plan — bounded scope

Status: completed as an opt-in experiment on 1 October 2026. The approved scope below is retained. Implementation and results are in `README.md` and `VALIDATION.md`. Earlier versions are preserved in Git history; Jev remains experimental.

## Purpose

Test one question: does Jev improve evidence assessment inside our existing harness without discarding additional supported answers?

The language layer must never silently upgrade the certainty of underlying evidence. This integration serves the original verification/scoring interface. It does not redesign the harness or establish a new research platform.

## What changes

Add a small standard-library HTTP adapter for Jev through OpenRouter, plus an optional second-review dispatch and its config/tests. Reuse OPENROUTER_API_KEY. OpenRouter documents the TypeSafe-compatible endpoint at https://openrouter.ai/api/v1/systemone; its access guide identifies typesafe/jev-1.13 as the pinned model. Verify that contract with a tiny live check when implementation begins. The existing chat client cannot simply substitute Jev because its API expects state and typed questions rather than chat messages.

Keep the existing verifier role for evidence mapping and task-completion review. Add a separate Jev reviewer configuration; assigning the whole verifier role to Jev would also send generative completion work to it. This separation is necessary for the integration, not a new user-facing workflow.

Sources: [OpenRouter Jev access](https://openrouter.ai/blog/insights/what-is-jev/), [TypeSafe typed API](https://docs.typesafe.ai/api).

## What remains fixed

- Local question answering and exact claim extraction.
- Whole-answer coverage and reference quote guards.
- Declared arithmetic routing and exact proof checking, with no model fallback.
- Existing task-completion review and the user-confirmed arithmetic contract: expression and result suffice; intermediate steps are optional.
- Evidence-strength caps, deterministic assertability, rendering and final certainty audit.
- JSONL and existing evaluation metrics.

No training, new retrieval system, extra model panel, wider arithmetic grammar, new UI or framework migration.

## Jev's job

The initial evidence map provides exact spans and reference quotes. Jev receives the entire candidate, reference and span identifiers as data, without the first reviewer's verdicts/reasons or benchmark labels. Each span gets one Choice question with three options:

- supported: every assertion follows from the reference, preserving subject, relation, conditions, quantities and modality.
- contradicted: the reference establishes an explicit incompatible assertion; missing information is insufficient.
- unknown: neither support nor explicit conflict is established, including unresolved ambiguity.

Python retains support or contradiction only when Jev agrees with the initial assessment. Disagreement becomes unknown. An initially unknown answer cannot become supported. Missing or invalid reference quotes cannot be repaired through Jev approval.

Jev's probabilities and confidence are logged separately. They do not increase evidence strength or the existing score, and they do not alter certainty thresholds. Model-only support remains weak/tentative. Jev does not generate quotes, explanations or final wording; the adapter must not invent them. [Confidence semantics](https://docs.typesafe.ai/confidence).

## Implementation sequence

1. Implement the bounded HTTPS adapter and strict validation of IDs, Choice type, allowed options, finite probabilities, distribution sum and selected option. Handle provider metadata without confusing it with evidence. Credential-bearing headers/bodies never enter logs. Timeouts and malformed responses withhold and record an error; no silent fallback or answer-changing retry.
2. Add opt-in dispatch/configuration and public trace fields. Preserve arithmetic-first routing, offline demo behavior and existing default configuration.
3. Add meaningful offline tests for malformed distributions, missing IDs, blind payloads, disagreement, quote guards, arithmetic bypass, credential exclusion and certainty preservation. Run the existing test suite.
4. Run up to three live contract checks, then replay the 24 recorded evidence-pair cases using the same frozen first-pass maps. This is regression evaluation, not a new unseen holdout. Compare the initial map with map-plus-Jev; keep completion judgements fixed for assessment isolation. Log Jev's raw labels separately from the combined agreement gate.
5. Report unsupported approval, useful retention, unknown incorrectly classified as contradicted, errors, certainty audits and latency/usage using existing metrics and a small results summary. Package and hand over the experiment.

Initial live scope: at most 27 Jev requests (3 checks + 24 cases), one batched request per case. Count exact span questions and token inputs from the frozen maps before running; never silently truncate. Use an explicit request/token/spend bound. No additional fresh-generation run, repeated model panel or expanded benchmark unless these results establish a concrete reason to propose it.

## Decision rule

Leave Jev opt-in. The experiment is useful only if it reduces unsupported approval without increasing loss of supported complete answers or inappropriate contradiction. Structural output improvements alone are insufficient. All emitted text must stay within existing evidence ceilings.

Two boundary labels are user-confirmed; remaining historical labels are provisional. Ambiguous cases must be reported separately, not silently relabelled to improve results. A successful small regression run would justify proposing a separate unseen validation, not automatic promotion.

## Ideas deliberately deferred

Bayesian reliability estimation is conceptually relevant, but adding priors, calibration splits, uncertainty intervals and new acceptance thresholds would create a separate statistical workstream. It is not required to integrate or compare Jev, so it is excluded from this implementation. It may be discussed later if enough independently labelled data exists and the current metrics leave a concrete decision unresolved.

Likewise, new test suites, standalone replacement of the initial evidence mapper, Jev task-completion review and broader model comparisons are deferred. Discuss the problem, expected benefit and scope cost before adding any of them.

The integration may conclude that Jev offers no worthwhile improvement. Stopping with that documented result is a valid outcome.

## Deliverables and remaining prerequisites

Deliver one optional adapter, one experiment configuration, focused tests, frozen replay inputs, JSONL traces and a concise comparison. Preserve existing projects. Publish implementation artifacts to GitHub when authorized for that work.

Before live evaluation, confirm the endpoint/model contract and a bounded spend limit using the existing OpenRouter account. This plan performs no inference calls, installs no dependencies and changes no harness code.
