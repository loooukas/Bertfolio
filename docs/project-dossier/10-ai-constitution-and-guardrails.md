# AI Constitution and Guardrails

## Canonical constitution source

The active AI constitution already exists and should be treated as canonical:

- `docs/llm_prompt_constitution.md`

## Summary of enforceable rules

- Evidence boundaries and no hallucinated facts.
- Strict JSON/schema discipline.
- Deterministic fallback and visible degradation.
- No trading advice generation.
- Management-only aggregation for company-facing transcript signals.

## Prompt and call-site governance

- Runtime prompt templates are versioned under `finbert_site/prompts/`.
- LLM call sites are documented and bounded by function-level responsibilities.

## Citations

- `docs/llm_prompt_constitution.md:1`
- `docs/llm_prompt_constitution.md:138`
- `docs/llm_prompt_constitution.md:159`
- `finbert_site/prompts/analysis_constitution_v1.md`
- `finbert_site/prompts/normalizer_v1.md`
- `finbert_site/prompts/transcript_feature_classifier_v1.md`
