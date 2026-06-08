# Public Repository Hygiene Audit

Date: 2026-06-08

Scope: tracked files at `HEAD`, `origin/main` after `git fetch --all --prune`, and commits reachable from local refs/remotes in this clone.

## Summary

No committed live API keys, access tokens, private keys, passwords, personal phone numbers, street addresses, or personal email addresses were found in tracked file content during this pass.

The scan identified and remediated a few public-hygiene items:

- Historical Git commit metadata used a personal-looking author name and email address. The visible branch history was rewritten to use a neutral maintainer identity.
- Historical documentation commits referenced local filesystem paths under a user home directory and a local draft filename. The visible branch history was rewritten to replace those references with neutral placeholders.
- Student classifier model weights are tracked through Git LFS under `output/student_models/...`. This is not PII or credential material, but it does publish the model artifacts if the repository and LFS objects are public.
- Environment variable names for OpenAI and Alpha Vantage appear in examples and code as expected placeholders/configuration names. No committed values were found.

## Remediation Applied

- Replaced the README quick-start clone command with a neutral `<repository-url>` placeholder so the setup instructions do not expose or hard-code a personal GitHub handle.
- Rewrote visible branch history to replace personal-looking Git author/committer metadata with `Bertfolio Maintainer <noreply@users.noreply.github.com>`.
- Rewrote visible branch history to replace historical local-path, local-draft-file, and personal GitHub-handle references with neutral placeholders.

## Follow-Up Decisions

- Git LFS student model artifacts are intentionally left as public repository artifacts.

## Commands Used

- `rtk git fetch --all --prune`
- `rtk trufflehog git file://<local-repo-path> --no-update --json`
- `rtk git grep` scans for secret, PII, local-path, private-note, and public-hygiene patterns against `HEAD` and `origin/main`
- `rtk git log --all` and `rtk git log --all -G ...` scans for historical pattern matches
- Read-only subagent audits for current tracked files and reachable Git history
- Temporary-clone history rewrite with LFS smudge disabled
- Post-rewrite `trufflehog` scan with LFS smudge disabled

## Coverage Limits

This audit covered local reachable Git refs after fetching remotes known to this clone. It did not inspect deleted remote branches unavailable locally, GitHub issues, pull request comments, CI logs, GitHub release assets, Git LFS server object history beyond tracked pointers, local stashes/reflogs, or untracked working-tree files.
