# Loop contract

Read by the Crucible loop agents (`implement-spec`, `verifier`). Keep it accurate.

- **Install:** the stack's setup from `.factory/toolchain.json` (a Bun repo: `bun install`).
- **Checks** (all must pass before a PR is ready): the commands `.factory/toolchain.json` resolves (quality, test,
  build). For the shipped bun example: `bun run format:check && bun run lint && bun run typecheck && bun test &&
  bun run build`. A Go repo ships `toolchain.go.example.json` instead: `make lint && make test && make build`.
- **Commit style:** match `git log` (for example `feat(v0.x.y): ...`)
- **Specs:** `specs/NNNN-slug.md`, see `crucibledx/hq/specs/README.md`
- **Assets:** diagrams and demos live in `crucibledx/assets`
- **Release:** manual. Loop PRs never bump versions, tag, or publish.
