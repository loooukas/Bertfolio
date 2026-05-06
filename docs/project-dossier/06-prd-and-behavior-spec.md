# PRD and Behavior Spec

## Product intent

Bertfolio should behave like a dependable analyst copilot during earnings cycles: fast to run, transparent about evidence, and explicit about uncertainty.

## Core user journey

1. Enter ticker.
2. Start analysis run.
3. Observe real stage progress.
4. Review completed report by section.
5. Validate confidence with Data Audit.
6. Reopen cached runs for comparison and follow-up.

## Behavioral requirements

- Job creation and polling must be responsive and clear.
- Progress must represent real backend stages.
- Report rendering must preserve section structure and labels.
- Failures must produce clear error states.
- Degraded paths must surface explicit warnings/notices.

## Report contract requirements

- Five primary sections plus audit diagnostics.
- Stable payload shape for downstream UI adapters.
- Sufficient provenance for analyst verification.

## Canonical behavior details

For full UX and progression detail, see `docs/site_behavior_and_user_progression.md`.

## Citations

- `docs/site_behavior_and_user_progression.md:1`
- `app/page.tsx:98`
- `app/page.tsx:200`
- `app/page.tsx:212`
- `finbert_site/main.py:447`
- `finbert_site/main.py:455`
- `finbert_site/main.py:477`
