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
- The README's diagrams live in `crucibledx/assets`: sources
  `factory-loop/diagrams/{delivery-loop,multiplayer-slack}.drawio`, renders
  `factory-loop/diagrams/{light,dark}/<name>.svg`. A change to the loop flow (stages, who acts, gates, the self-fix
  path) or the Slack routing ships with an assets PR that updates the source and both renders. Link the two PRs to
  each other.

## Checks

`sh scripts/check.sh` runs them all; CI's `checks` job (`.github/workflows/self-checks.yml`) runs the same script on
every PR and on `main`. It needs `python3`, `git`, `shellcheck` and `actionlint` 1.7.12 (the version CI pins).

- Every tracked `scripts/test-*`: `.py` with `python3`, `.sh` with `sh`. A new test is picked up by its name once
  it is added to git.
- Workflows lint: `actionlint .github/workflows/*.yml templates/repo/.github/workflows/*.yml`.
- Every tracked `*.json` file parses.

Commits: `feat: ...`, `fix: ...`, `docs: ...`. Tag releases `v0.x.y` and move the `v0` tag.
