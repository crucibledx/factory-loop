# factory-loop — Agent Context

Shared delivery loop for all `crucibledx` repos: a Droid plugin (skills, droids, hooks) and reusable GitHub workflows.
Org context: `crucibledx/hq` `AGENTS.md`.

## Rules

- Everything here is shared by every repo. Keep repo-specific details out; they belong in each repo's
  `.factory/loop-contract.md`.
- Skills and droids are prompts: keep them short, concrete, and testable. Change one behavior per PR and say which loop
  stage it affects.
- Reusable workflows are a public interface. Adding an input with a default is a minor change; renaming or removing one
  is breaking and needs a new major tag (`v1`).
- Never weaken the guard hook (no pushes to `main`, no force pushes, no merges by agents) without Nazar's explicit
  approval.

## Checks

- JSON parses: `python3 -m json.tool` on `.factory-plugin/*.json` and `plugins/*/.factory-plugin/*.json`, `hooks.json`.
- YAML parses: every file in `.github/workflows/` and `templates/repo/.github/workflows/`.
- Guard hook: `sh scripts/test-guard.sh`.

Commits: `feat: ...`, `fix: ...`, `docs: ...`. Tag releases `v0.x.y` and move the `v0` tag.
