# Stage 3 plan: assessment boundaries

Goal: reduce unjustified reference support while preserving useful, supported answers. The language layer must never silently upgrade certainty of underlying evidence. Stage 2's frozen project, arithmetic checker, policy and renderer remain unchanged.

1. Create a separate standard-library project based on consolidated stage 2. Add one optional evidence-alignment protocol; leave the stage 2 directory and its defaults intact.
2. Preserve whole-answer mapping. Add a second, blind review of every mapped span against the reference, explicitly judging subject, relationship, scope/conditions and modality. Do not expose the first reviewer's statuses or reasons to the second call. Python requires agreement and exact reference provenance for approval. Disagreement or unresolved dimensions become unknown. Model review remains weak/tentative; this is not a symbolic semantic proof and the same-model calls are correlated.
3. Make arithmetic working requirements explicit in the new benchmarks. Do not change the arithmetic grammar or promote uncertain inputs. Correct proof and task completeness remain separate.
4. Freeze 12 minimal pairs (24 answers): four development pairs and eight held-out pairs. Include supported paraphrases and changes to subject, conditions, negation, modality, quantity, necessity and added procedures. Freeze labels, metadata, prompts and runtime code before inference. Gold labels never enter model payloads. Use the development/held-out distinction only for reporting; do not tune this run.
5. Compare baseline and proposal on identical fixed answers. Then generate six fresh answers once with local Qwen and replay them in both arms. Do not use fresh outputs to revise prompts. Record intermediate verdicts, completion, audits and latency, including extra review cost.
6. Measure unsupported acceptance, supported retention, incorrect contradiction, task coverage and certainty compliance separately. Adoption target: no unsupported emission in the held-out fixtures, no loss of eligible supported complete answers versus baseline, and no certainty upgrades. A passing small set is insufficient proof of general reliability. Regression or ambiguity means experimental status, not silent promotion.
7. Run offline tests, clean-package checks and credential exclusion. Write concise handover with exact denominators, limitations and reproducible logs.

Label provenance: initial labels are assistant-authored before inference. Human review is requested for ambiguous cases; until supplied, conclusions are provisional. Neither a second call to the same model nor an assistant reviewing its own fixtures constitutes independent human adjudication.

Out of scope: training, model upgrades, broader arithmetic grammar, unrestricted inference, automatic browsing/retrieval or a framework rewrite.
