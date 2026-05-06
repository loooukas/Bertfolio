# Strengths and Limitations

## Strengths

- End-to-end pipeline from ticker input to structured report.
- Real stage-level progress and operational transparency.
- Explicit Data Audit diagnostics and missing-data surfacing.
- Consistent response contract that supports repeatable workflows.
- Local-first inspectability and controlled adoption path.

## Limitations

- Source coverage can vary by ticker, region, and timeframe.
- Some capabilities depend on external APIs or local model assets.
- Performance and ROI benchmarks are not yet packaged as formal in-repo studies.

## Risk management guidance

- Treat outputs as analyst-support, not autonomous conclusions.
- Use Data Audit as a required confidence checkpoint.
- Escalate low-confidence or sparse-data runs for deeper manual review.

## Citations

- `finbert_site/progress.py:15`
- `finbert_site/schemas.py:316`
- `finbert_site/schemas.py:397`
- `finbert_site/transcript_pipeline.py:60`
- `finbert_site/jobs.py:111`
