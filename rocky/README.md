# Rocky Teacher-Labeling Pipeline

`rocky/` is a first-pass, script-driven dataset pipeline for block-level teacher labels.
It intentionally reuses existing FinBERT repo logic:

- Transcript fetch/discovery: `finbert_site.transcript_pipeline.fetch_transcripts_for_analysis`
- Transcript normalization: `finbert_site.normalizer.normalize_transcript_document`
- Existing transcript section structure (`speaker`, `speaker_role`, `section_type`, `text`, `order_index`)

## Phase Flow

1. Phase 1: Collect transcript envelopes (using existing fetch/discovery path)
2. Phase 2: Normalize transcript documents (using existing normalization path)
3. Phase 3: Flatten to block-level rows with adjacency metadata
4. Phase 4: Deterministic pre-label triage flags (do not delete rows)
5. Phase 5: Label labelable rows through LM Studio OpenAI-compatible API
6. Phase 6: Capture metric labels + teacher confidence + dataset quality labels
7. Phase 7: Save all outputs incrementally with resume support

## Scripts

- Builder: `scripts/build_teacher_dataset.py`
- Labeler: `scripts/label_blocks_with_lmstudio.py`

Both wrappers call the implementation in `rocky/`.

## Output Layout

Default output directory: `output/teacher_dataset/`

- `raw_transcripts/<TICKER>/fetch_*.json`
- `raw_transcripts/<TICKER>/<transcript_id>.json`
- `normalized_transcripts/<TICKER>/<transcript_id>.json`
- `blocks_full.jsonl`
- `blocks_labelable.jsonl`
- `labeled_blocks.jsonl`
- `failures.jsonl`
- `run_manifest.json`

## Builder Usage

### Default bootstrap run (about 100 transcript cap)

```bash
.venv/bin/python scripts/build_teacher_dataset.py --max-transcripts 100
```

### Inline tickers

```bash
.venv/bin/python scripts/build_teacher_dataset.py \
  --tickers AAPL MSFT NVDA AMZN \
  --max-transcripts 100
```

### Tickers from file + resume

```bash
.venv/bin/python scripts/build_teacher_dataset.py \
  --tickers-file rocky/tickers.txt \
  --max-transcripts 100 \
  --resume
```

### Builder flags

- `--tickers`
- `--tickers-file`
- `--max-transcripts`
- `--transcripts-per-ticker`
- `--output-dir`
- `--resume`

## Block Row Format

Each row in `blocks_full.jsonl` contains one speaker block and includes:

- identity: `sample_id`, `transcript_id`, `ticker`, `company_name`, `quarter`, `published_date`
- source metadata: `transcript_source_url`
- block fields: `speaker`, `canonical_speaker`, `speaker_role`, `section_type`, `order_index`, `text`
- counts: `char_count`, `word_count`
- adjacency: `previous_speaker`, `next_speaker`, `previous_role`, `next_role`, `previous_section_type`, `next_section_type`
- context flags: `transcript_has_qa`, `is_short_block`, `is_operator_or_host_like`
- triage flags: `should_skip_labeling`, `skip_reasons`
- future pairing support: `metadata` (position, participant map, adjacent sample ids, Q&A hints, evidence snippets)

## Default Skip/Triage Behavior

Rows are still written to `blocks_full.jsonl` even when skipped.

`should_skip_labeling=true` is set for obvious low-value blocks, including:

- malformed/near-empty text
- tiny acknowledgments
- legal/disclaimer fragments
- procedural/admin/operator routing
- short low-information blocks
- low-value `section_type=other` blocks without substantive signal

Labelable rows are written to `blocks_labelable.jsonl`.

## Labeler Usage (LM Studio)

The labeler sends OpenAI-compatible requests to `http://127.0.0.1:1234/v1`.

### First labeling pass

```bash
.venv/bin/python scripts/label_blocks_with_lmstudio.py \
  --model gemma-3-27b-it \
  --max-rows 200
```

### Resume and skip already labeled rows

```bash
.venv/bin/python scripts/label_blocks_with_lmstudio.py \
  --model gemma-3-27b-it \
  --resume \
  --skip-labeled
```

### Custom system prompt file (optional)

```bash
.venv/bin/python scripts/label_blocks_with_lmstudio.py \
  --model gemma-3-27b-it \
  --system-prompt-file rocky/system_prompt.txt
```

By default, no script-side system prompt is sent. This lets LM Studio use the model/system behavior you configured there.

### Labeler flags

- `--input-jsonl`
- `--output-dir`
- `--model`
- `--base-url` (default `http://127.0.0.1:1234/v1`)
- `--api-key` (default `lm-studio`)
- `--temperature` (default `0`)
- `--timeout-seconds`
- `--retries`
- `--max-rows`
- `--resume`
- `--skip-labeled`
- `--system-prompt-file`

## Structured Label Schema

Label responses are validated against the strict schema implemented in `rocky/label_schema.py`.
Required label dimensions include:

- metric bands + metric scores
- `teacher_confidence`
- `dataset_quality_band`
- `dataset_quality_score`
- `dataset_quality_reasons`
- `evidence_snippets`
- `notes`

## Resumability

`run_manifest.json` is updated during both build and label runs.

- Builder resume:
  - `--resume` reads `processed_transcript_ids` and continues without reprocessing completed transcripts.
- Labeler resume:
  - `--resume` and/or `--skip-labeled` skip rows already present in `labeled_blocks.jsonl`.
  - failures are appended to `failures.jsonl`; reruns can retry them.
