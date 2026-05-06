# Strengths and Limitations

## Strengths

- End-to-end pipeline with stage-level progress and structured completion.
- Typed report contract with explicit audit and diagnostics sections.
- Deterministic-first transcript processing with bounded LLM assists.
- Graceful degradation on provider/model/normalization failures.
- Local cache for re-openable analyses and recomputation of management-facing aggregates.

## Limitations

- Provider/source coverage is variable by ticker and period.
- Some transcript and feature paths depend on API keys or local model artifacts.
- The repository does not include a formal benchmark package for latency/accuracy or competitive claims.

## Operating guidance

Use Data Audit and transcript quarter status as first-class confidence signals; do not interpret a completed run as complete provider coverage.

## Citations

- `finbert_site/progress.py:15`
- `finbert_site/schemas.py:316`
- `finbert_site/schemas.py:397`
- `finbert_site/transcript_pipeline.py:60`
- `finbert_site/jobs.py:111`
- `finbert_site/main.py:498`
