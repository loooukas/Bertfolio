# Problem Statement

Bertfolio exists to reduce the time and inconsistency of multi-source earnings analysis by turning transcript, sentiment, market context, and data quality into one structured run.

## Current pain points addressed

- Earnings analysis is fragmented across transcript reading, news/social scanning, and fundamentals checks.
- Manual review quality varies across analysts and across time.
- Typical tooling does not expose a unified audit trail of what was found, skipped, or degraded.

## Product problem definition (code-backed)

The implemented product is explicitly transcript-first and combines:

- Transcript retrieval and normalization.
- FinBERT sentiment scoring.
- Optional local student-style communication metrics.
- Fundamentals/news/social context.
- Data-audit diagnostics in the same response payload.

## Citations

- `README.md` (product scope and workflow)
- `finbert_site/analysis.py:1` (core pipeline role)
- `finbert_site/schemas.py:413` (single `AnalysisResponse` contract)
- `finbert_site/schemas.py:397` (explicit data-audit section)
- `docs/site_behavior_and_user_progression.md:5` (analyst-support workflow)
