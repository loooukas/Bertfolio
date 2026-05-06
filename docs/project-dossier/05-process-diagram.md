# Process Diagram

```mermaid
flowchart TD
  A["Analyst enters ticker in Next.js"] --> B["POST /api/analyze/jobs"]
  B --> C["FastAPI job manager starts run"]
  C --> D["Fetch transcript, news, social, fundamentals"]
  D --> E["Score with FinBERT and optional local models"]
  E --> F["Assemble Overview, Transcript, Market, Fundamentals"]
  F --> G["Generate Data Audit and diagnostics"]
  G --> H["Return structured report payload"]
  H --> I["Frontend renders report and evidence"]
```

## Operating interpretation

This process replaces a multi-tab manual workflow with one repeatable run that is easier to scale and easier to review.

## Citations

- `app/page.tsx:81`
- `finbert_site/main.py:434`
- `finbert_site/jobs.py:98`
- `finbert_site/analysis.py:1676`
- `finbert_site/schemas.py:413`
