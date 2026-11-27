## Org rules

These apply to every crucibledx repo. The repo's `AGENTS.md` and `.factory/loop-contract.md` win on conflict.

- Platform: CLIs in TypeScript on Bun, shipped as single binaries built with `bun build --compile`. Ember is the one
  Go exception (a custom OpenTelemetry Collector distribution). No rewrites into other languages.
- "Complete, don't compete": integrate with existing coding harnesses and tools; don't replace them.
- License: MIT everywhere.
- Every spec, doc or architecture write-up includes at least one assetkit diagram from `crucibledx/assets`, with light
  and dark renders, linked or embedded.
- Each project repo installs its own dependencies and commits its own `bun.lock`.
- Commit style: forge-cli `feat(v0.x.y): ...` / `fix(v0.x.y): ...`; web and forge-skills-starter `v0.x.y: ...`; other
  repos follow their `git log`.
- Versioning: semver, annotated tags, one `CHANGELOG.md` per project (assets uses `v1`, `v2` tags). Releases are
  manual.
- `homebrew-tap` and `scoop-bucket` are rewritten by the forge-cli release workflow; flag hand edits to them.
- Agents never push to `main`, never merge, and never edit an approved acceptance contract; they propose contract
  changes in the PR.
