## Org rules

These apply to every crucibledx repo. A repo's `AGENTS.md`, `CONTRIBUTING.md` or `.factory/loop-contract.md` wins on
conflict. Severity hints in brackets work as in the engineering standards. This is the public copy of the org rules
in the private `crucibledx/hq` `AGENTS.md`; change both together.

- Platform: CLIs in TypeScript on Bun, shipped as single binaries built with `bun build --compile`. Ember is the one
  Go exception (a custom OpenTelemetry Collector distribution). No rewrites into other languages. [P1]
- "Complete, don't compete": integrate with existing coding harnesses and tools; don't replace them. [P2]
- License: MIT everywhere. [P1]
- A new spec, docs page or architecture write-up includes at least one assetkit diagram from `crucibledx/assets`,
  with light and dark renders, linked or embedded. README, CHANGELOG and small doc edits don't need one. [P2]
- Each project repo installs its own dependencies and commits its own `bun.lock`. [P2]
- Commit style: forge-cli `feat(v0.x.y): ...` / `fix(v0.x.y): ...`; web and forge-skills-starter `v0.x.y: ...`; other
  repos follow their `git log`. [nit]
- Versioning: semver, annotated tags, one `CHANGELOG.md` per project (assets uses `v1`, `v2` tags). Releases are
  manual. [P2]
- `homebrew-tap` and `scoop-bucket` are rewritten by the forge-cli release workflow; a hand edit to them is
  flagged. [P1]
- Agents never push to `main`, never merge, and never edit an approved acceptance contract; they propose contract
  changes in the PR. [P1]
