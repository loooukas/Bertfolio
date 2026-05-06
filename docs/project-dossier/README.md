# Project Dossier

Bertfolio is an analyst-support earnings intelligence platform. This dossier explains the business case, operating model, implementation path, and governance in plain language.

## Executive Summary

Bertfolio solves a specific operational pain: earnings analysis is high-value but too manual, inconsistent, and slow to scale. The product converts transcript, news, social, and fundamentals review into one repeatable workflow with clear evidence and clear uncertainty signals.

## Read in this order

1. [01 Problem Statement](./01-problem-statement.md)
2. [02 Solution Overview](./02-solution-overview.md)
3. [07 Value Proposition vs Manual Workflow](./07-value-proposition-vs-manual.md)
4. [08 Target Users and Stakeholders](./08-target-users-and-stakeholders.md)
5. [09 Competitive Landscape](./09-competitive-landscape.md)
6. [03 How It Works (Pipeline)](./03-how-it-works-pipeline.md)

## Full Dossier

- [04 Architecture Notes](./04-architecture-notes.md)
- [05 Process Diagram](./05-process-diagram.md)
- [06 PRD and Behavior Spec](./06-prd-and-behavior-spec.md)
- [10 AI Constitution and Guardrails](./10-ai-constitution-and-guardrails.md)
- [11 Strengths and Limitations](./11-strengths-and-limitations.md)
- [12 Design System Notes](./12-design-system-notes.md)

## How Bertfolio works in simple terms

- `Next.js` is the web app where a user enters a ticker and reviews results.
- `FastAPI` runs the analysis job in the background.
- The backend pulls transcripts, news, social, and fundamentals data.
- `FinBERT` scores sentiment with financial-language context.
- Optional local models add communication-style metrics.
- The product returns one structured report with a Data Audit section that shows reliability and gaps.

## Source-of-truth policy

- Business framing: this dossier.
- Product behavior and implementation evidence: `README.md`, `docs/site_behavior_and_user_progression.md`, `docs/llm_prompt_constitution.md`, `DESIGN-SYSTEM.md`, and code in `finbert_site/`, `app/`, and `lib/`.
- External pitch artifacts can inform wording, but repository behavior is authoritative.
