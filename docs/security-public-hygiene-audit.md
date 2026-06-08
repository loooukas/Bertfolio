# Public Repository Hygiene Audit

Date: 2026-06-08

Scope: tracked files at `HEAD`, `origin/main` after `git fetch --all --prune`, and commits reachable from local refs/remotes in this clone.

## Summary

No committed live API keys, access tokens, private keys, passwords, personal phone numbers, street addresses, or personal email addresses were found in tracked file content during this pass.

The scan did identify a few public-hygiene items:

- Historical Git commit metadata uses a personal-looking author name and email address. This is not file content, but it remains visible in Git history unless the repository history is rewritten.
- Historical documentation commits referenced local filesystem paths under a user home directory and a local draft filename. Current tracked `HEAD` no longer includes the absolute local paths.
- Student classifier model weights are tracked through Git LFS under `output/student_models/...`. This is not PII or credential material, but it does publish the model artifacts if the repository and LFS objects are public.
- Environment variable names for OpenAI and Alpha Vantage appear in examples and code as expected placeholders/configuration names. No committed values were found.

## Remediation Applied

- Replaced the README quick-start clone command with a neutral `<repository-url>` placeholder so the setup instructions do not expose or hard-code a personal GitHub handle.

## Follow-Up Decisions

- Decide whether to rewrite published Git history to replace personal author metadata and historical local-path references. This requires coordination because it changes commit SHAs and usually requires a force push.
- Decide whether the Git LFS student model artifacts should remain public. If the model weights are proprietary, move them to a private release/storage location and publish download/setup instructions instead.

## Commands Used

- `rtk git fetch --all --prune`
- `rtk trufflehog git file://<local-repo-path> --no-update --json`
- `rtk git grep` scans for secret, PII, local-path, private-note, and public-hygiene patterns against `HEAD` and `origin/main`
- `rtk git log --all` and `rtk git log --all -G ...` scans for historical pattern matches
- Read-only subagent audits for current tracked files and reachable Git history

## Coverage Limits

This audit covered local reachable Git refs after fetching remotes known to this clone. It did not inspect deleted remote branches unavailable locally, GitHub issues, pull request comments, CI logs, GitHub release assets, Git LFS server object history beyond tracked pointers, local stashes/reflogs, or untracked working-tree files.
