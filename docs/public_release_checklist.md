# Bertfolio Public Release Checklist

Use this before making the repository public.

## Must Not Be Tracked

- `.env` or any file containing real API keys.
- Generated files under `output/`.
- Transcript caches, debug payloads, logs, and HTML reports.
- Pickle, archive, CSV, TSV, JSONL, Parquet, SQLite, or local database files.
- Model weights and checkpoints (`*.safetensors`, `*.pt`, `*.pth`, `*.ckpt`, `*.onnx`).
- Teacher-label datasets, student-training datasets, score-calibration outputs, and backtesting results.

## Expected Public Contents

- Product source code for the local Next.js + FastAPI app.
- Safe placeholder configuration in `.env.example`.
- Setup and run instructions in `README.md`.
- Methodology docs that explain runtime scoring behavior without including private datasets or results.
- Tests that use dummy placeholder keys only.

## Verification Commands

```bash
git status --short
git ls-files | rg '(\.env$|\.pkl$|\.zip$|\.csv$|\.tsv$|\.jsonl$|\.parquet$|\.sqlite3?$|\.db$|\.safetensors$|\.pt$|\.pth$|\.ckpt$|\.onnx$|^output/)'
rg -n '(/Users/|Documents/VSCode|sk-[A-Za-z0-9]|gh[pousr]_|xox[baprs]-|BEGIN (RSA|OPENSSH|PRIVATE) KEY)' . --glob '!node_modules/**' --glob '!.next/**' --glob '!.git/**' --glob '!.venv/**'
```

The second command should print nothing. The third command should print nothing except intentionally ignored local-only research files that are not part of the publish snapshot.
