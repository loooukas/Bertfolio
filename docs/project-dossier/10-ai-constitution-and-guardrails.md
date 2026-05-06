# AI Constitution and Guardrails

## Business purpose

Bertfolio uses AI to improve analyst throughput and consistency while preserving accountability. Guardrails ensure AI assistance remains explainable, bounded, and reviewable.

## Canonical source

- `docs/llm_prompt_constitution.md`

## Core guardrail pillars

- Evidence boundaries: no fabricated facts or sources.
- Structured output discipline: schema-constrained responses.
- Deterministic fallback behavior when AI outputs are invalid.
- No direct trading recommendations.
- Management-focused aggregation for company-facing transcript signals.

## Why this matters for adoption

These rules support use in environments where trust, auditability, and defensible interpretation are mandatory.

## Governance recommendations

- Require human review for low-confidence or high-impact summaries.
- Keep diagnostics visible in user-facing outputs.
- Treat missing/ambiguous inputs as explicit uncertainty, not hidden defaults.

## Citations

- `docs/llm_prompt_constitution.md:1`
- `docs/llm_prompt_constitution.md:138`
- `docs/llm_prompt_constitution.md:159`
