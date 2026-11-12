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
- The README's loop diagram lives in `crucibledx/assets`: source `factory-loop/diagrams/delivery-loop.drawio`, renders
  `factory-loop/diagrams/{light,dark}/delivery-loop.svg`. A change to the loop flow (stages, who acts, gates, the
  self-fix path) ships with an assets PR that updates the source and both renders. Link the two PRs to each other.

## Checks

- JSON parses: `python3 -m json.tool` on `.factory-plugin/*.json` and `plugins/*/.factory-plugin/*.json`, `hooks.json`.
- Workflows lint: `actionlint .github/workflows/*.yml templates/repo/.github/workflows/*.yml`.
- Review helper: `python3 scripts/test-review.py`.
- Guard hook: `sh scripts/test-guard.sh`.
- Auto-merge script: `sh scripts/test-automerge.sh`.

Commits: `feat: ...`, `fix: ...`, `docs: ...`. Tag releases `v0.x.y` and move the `v0` tag.
