# Loop contract

Read by the Crucible loop agents (`implement-spec`, `verifier`). Keep it accurate.

- **Install:** the stack's setup from `.factory/toolchain.json` (a Bun repo: `bun install`).
- **Checks** (all must pass before a PR is ready): the commands `.factory/toolchain.json` resolves (quality, test,
  build). The template's bun example resolves to `bun test` and `bun run build`, plus `bun run format:check`,
  `bun run lint` and `bun run typecheck` when `package.json` defines those scripts. The Go example
  (`toolchain.go.example.json`) resolves to `make lint && make test && make build`.
- **Commit style:** match `git log` (for example `feat(v0.x.y): ...`)
- **Specs:** `specs/NNNN-slug.md`, see `crucibledx/hq/specs/README.md`
- **Assets:** diagrams and demos live in `crucibledx/assets`
- **Release:** manual. Loop PRs never bump versions, tag, or publish.
