# Changelog

## Unreleased

- `loop-review` v2: one consolidated review per push. The first review covers the whole PR; later reviews cover only
  new commits, judge every open finding (reply and resolve when fixed, reply "Not fixed" when not), and warn when the
  PR grew past 1.5x its first reviewed size.
- `loop-review` gates the merge: the check fails while P0/P1 reviewer threads are unresolved
  (`blocking_severities` input). Review submissions and review comments re-run only the gate, without a model call.
- New inputs `review_model` (default `openai-latest-balanced`), `reasoning_effort`, `blocking_severities`, `loop_ref`.
- factory-loop reviews its own PRs with the workflow from the PR branch (`self-review.yml`).
- Template: the `review` job also runs on `pull_request_review` and `pull_request_review_comment`.

## v0.1.1 — 2026-10-29

- Loop contract lives in `.factory/loop-contract.md` (an `AGENTS.md` `## Loop contract` section still works).
- `scripts/install.sh` adds the contract file and `specs/README.md`.
- Guard hook checks each part of a chained command separately, so `git push <branch> && gh pr create --base main` is
  no longer blocked.

## v0.1.0 — 2026-10-29

- Plugin marketplace `factory-loop` with plugin `crucible-loop`.
- Skills: `idea-discovery`, `spec-writer`, `acceptance-contract`, `implement-spec`, `loop-orchestrator`.
- Droids: `researcher`, `spec-reviewer-arch`, `spec-reviewer-product`, `code-reviewer`, `verifier`.
- Guard hook blocking pushes to `main`, force pushes, and PR merges.
- Reusable workflows: `loop-implement`, `loop-review`, `loop-mention`, `loop-spec-merged`.
- Per-repo templates and `scripts/install.sh`.
