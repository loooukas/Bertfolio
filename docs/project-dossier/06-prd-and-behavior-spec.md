# PRD and Behavior Spec

This dossier references the existing full behavior specification and records its status as canonical product behavior documentation.

## Canonical behavior spec

- See `docs/site_behavior_and_user_progression.md` for detailed user progression, runtime shape, stage behavior, and degraded/failure states.

## Key acceptance behaviors

- User can start a run with ticker input and receive stage-level progress.
- Completed run yields 5-section report with data audit diagnostics.
- Failed run yields explicit error state.
- Cached runs can be listed, opened, and deleted.

## Citations

- `docs/site_behavior_and_user_progression.md:1`
- `app/page.tsx:98`
- `app/page.tsx:200`
- `app/page.tsx:208`
- `app/page.tsx:212`
- `finbert_site/main.py:477`
- `finbert_site/main.py:483`
- `finbert_site/main.py:512`
