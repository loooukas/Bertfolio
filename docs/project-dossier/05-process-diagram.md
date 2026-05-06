# Process Diagram

```mermaid
flowchart TD
  A["User enters ticker"] --> B["POST /api/analyze/jobs (Next proxy)"]
  B --> C["FastAPI job manager creates background run"]
  C --> D["News + social fetch and FinBERT scoring"]
  C --> E["Fundamentals fetch + validation"]
  C --> F["Transcript discovery and scrape"]
  F --> G["Normalization and speaker-level scoring"]
  D --> H["Report assembly + data audit"]
  E --> H
  G --> H
  H --> I["Persist cache envelope"]
  I --> J["GET /api/analyze/jobs/{id}/result"]
  J --> K["Frontend adapts payload and renders report"]
```

## Citations

- `lib/finbert/client.ts:39`
- `finbert_site/main.py:434`
- `finbert_site/jobs.py:208`
- `finbert_site/progress.py:15`
- `finbert_site/analysis.py:1676`
- `finbert_site/main.py:455`
- `lib/finbert/adapters.ts:289`
