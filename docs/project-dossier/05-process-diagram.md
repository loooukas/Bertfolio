# Process Diagram

```mermaid
flowchart TD
  A["Analyst enters ticker in Next.js UI"] --> B["POST /api/analyze/jobs"]
  B --> C["FastAPI AnalyzeJobManager starts background run"]

  C --> D1["News Fetch: Alpha Vantage + Yahoo Finance"]
  C --> D2["Social Fetch: Reddit + Stocktwits"]
  C --> D3["Fundamentals Fetch: Yahoo Finance baseline"]
  C --> D4["Fundamentals Validation: Alpha Vantage cross-check/backfill"]
  C --> D5["Transcript Discovery + Scrape: Motley Fool pipeline"]
  D5 --> D6["Transcript Normalization into structured sections"]

  D1 --> E1["FinBERT scores news sentiment"]
  D2 --> E2["FinBERT scores social sentiment"]
  D6 --> E3["FinBERT scores transcript sentiment by segment"]

  D6 --> F1["Local DeBERTa metric models (default on): confidence, directness, outlook_strength"]
  D6 --> F2["Local DeBERTa metric models (default off): specificity, risk_intensity"]
  F1 --> F3["If model unavailable, deterministic lexical fallback + warning"]
  F2 --> F3

  E1 --> G["Weighted aggregation + report assembly"]
  E2 --> G
  E3 --> G
  F3 --> G
  D3 --> G
  D4 --> G

  G --> H["Output sections: Overview, Transcript, Market Reaction, Fundamentals, Data Audit"]
  H --> I["GET /api/analyze/jobs/{id}/result"]
  I --> J["Next.js renders report, evidence, and reliability diagnostics"]
```

## Operating interpretation

This process replaces a multi-tab manual workflow with one repeatable run that is easier to scale and easier to review. The diagram explicitly shows where each signal is sourced and how scoring combines FinBERT sentiment with local DeBERTa communication metrics.

## Default metric behavior (current implementation)

- `On by default`: confidence, directness, outlook strength.
- `Off by default`: specificity, risk intensity.
- All five local model paths are DeBERTa-based artifacts under `output/student_models/...`.
- Missing/failed local models degrade to deterministic fallback behavior with surfaced warnings.

## Citations

- `app/page.tsx:81`
- `finbert_site/main.py:434`
- `finbert_site/jobs.py:98`
- `finbert_site/analysis.py:1700`
- `finbert_site/analysis.py:1718`
- `finbert_site/analysis.py:1776`
- `finbert_site/analysis.py:1789`
- `finbert_site/analysis.py:1833`
- `finbert_site/analysis.py:1738`
- `finbert_site/analysis.py:1750`
- `finbert_site/analysis.py:1676`
- `finbert_site/settings.py:66`
- `finbert_site/settings.py:69`
- `finbert_site/settings.py:84`
- `finbert_site/settings.py:88`
- `finbert_site/settings.py:92`
- `finbert_site/settings.py:96`
- `finbert_site/settings.py:100`
- `README.md:86`
- `finbert_site/schemas.py:413`
