# Changelog

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
