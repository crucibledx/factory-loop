# Changelog

## Unreleased

- New `loop-automerge` workflow: auto-merge is on exactly while an allowed approver (default `NazarUsik`) has
  approved the current head, set by the `crucible-smith` app on every review and push. The template calls it, and
  ships `.github/CODEOWNERS` so rulesets can require that approval.
- `loop-spec-merged` authenticates as the `crucible-smith` GitHub App (`SMITH_CLIENT_ID` variable,
  `SMITH_PRIVATE_KEY` secret). `LOOP_GH_TOKEN` is now an optional fallback.
- App tokens use the app's client ID (`SMITH_CLIENT_ID` variable) instead of the deprecated `app-id` input of
  `actions/create-github-app-token`, pinned to the v3.3.0 commit.

## v0.3.0 — 2026-11-09

- `implement-spec` owns the PR until CI and the review gate are green: batch fixes, direct thread replies, escalation
  rules instead of a fixed round limit, ~1,500-line PR budget.
- `spec-writer` sizes implementation milestones and skips evidence tooling unless asked.
- `loop-orchestrator` Workstream mode: one implementer agent per issue, WIP default 3.
- Template no longer calls `loop-implement` (deprecated; it never started a run).
- `engineering-standards` skill v1: org rules for scope, design, architecture, tests, style, and CI, each with a
  review severity. Read by the implementer, the local `code-reviewer` droid, and the PR review workflow.

## v0.2.0 — 2026-11-09

- `loop-review` v2: one consolidated review per push. The first review covers the whole PR; later reviews cover only
  new commits, judge every open finding (reply and resolve when fixed, reply "Not fixed" when not), and warn when the
  PR grew past 1.5x its first reviewed size.
- `loop-review` gates the merge: the check fails while P0/P1 reviewer threads are unresolved
  (`blocking_severities` input). Review submissions re-run only the gate, without a model call. The gate also fails while the checked-out commit has no completed review.
- New inputs `review_model` (default `openai-latest-balanced`), `reasoning_effort`, `blocking_severities`, `loop_ref`.
- factory-loop reviews its own PRs with the workflow from the PR branch (`self-review.yml`).
- Template: the `review` job also runs on `pull_request_review`.

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
