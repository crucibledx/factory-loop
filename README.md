# factory-loop

The Crucible delivery loop for [Factory Droid](https://factory.ai): an idea becomes a reviewed spec PR, and an approved
spec becomes a tested implementation PR. Shared by every `crucibledx` repo, so each repo only keeps what is specific to
it.

## How the loop works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/dark/delivery-loop.svg">
  <img alt="Crucible delivery loop: board stages, who acts at each stage, and how the loop fixes itself" src="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/light/delivery-loop.svg">
</picture>

1. A request arrives in Slack. An idea goes through discovery and a spec PR checked by two reviewer droids; merging
   the spec creates one `loop:implement` issue per target repo. Code work goes straight to the orchestrator.
2. The Workstream orchestrator starts one agent per issue, each in its own worktree and branch.
3. The agent implements, runs the repo's checks and the local `verifier` and `code-reviewer` droids, and opens a
   draft PR. It marks the PR ready once they pass.
4. `loop-review` reviews the PR. The `review / review` check stays red while a P0 or P1 finding is open.
5. The agent fixes the findings, replies on each thread, and pushes. The next review covers the new commits and
   resolves what is fixed.
6. With CI and the review gate green, Nazar reviews and approves. His approval turns on auto-merge, and GitHub merges.
7. When an agent hits a problem in the loop itself, it reports it to the orchestrator. The fix ships as a PR to this
   repo through the same gate, and moving the `v0` tag rolls workflow fixes out to every repo.

The diagram source is
[`factory-loop/diagrams/delivery-loop.drawio`](https://github.com/crucibledx/assets/blob/main/factory-loop/diagrams/delivery-loop.drawio)
in `crucibledx/assets`.

## What's inside

| Path                                  | What it is                                                              |
|---------------------------------------|-------------------------------------------------------------------------|
| `.factory-plugin/marketplace.json`    | Droid plugin marketplace `factory-loop`                                 |
| `plugins/crucible-loop/skills/`       | `idea-discovery`, `spec-writer`, `acceptance-contract`, `implement-spec`, `loop-orchestrator`, `engineering-standards` |
| `plugins/crucible-loop/droids/`       | `researcher`, `spec-reviewer-arch`, `spec-reviewer-product`, `code-reviewer`, `verifier` |
| `plugins/crucible-loop/hooks/`        | Guard: blocks pushes to `main`, force pushes, and PR merges             |
| `.github/workflows/loop-*.yml`        | Reusable workflows: review + merge gate, auto-merge on approval, `@droid` mentions, spec merged (`loop-implement` is deprecated) |
| `templates/repo/`                     | The thin per-repo files: caller workflow, `.factory/settings.json`, `.factory/loop-contract.md` |

## Add the loop to a repo

```sh
scripts/install.sh ~/crucible/projects/<repo>
```

Then edit `.factory/loop-contract.md` with the repo's real check commands. (A `## Loop contract` section in
`AGENTS.md` also works.)

Secrets, set once:

- `FACTORY_API_KEY`: org secret for public repos; repo secret for private repos on the GitHub Free plan.
- `SMITH_CLIENT_ID` (variable, the app's client ID) and `SMITH_PRIVATE_KEY` (secret): the `crucible-smith` GitHub
  App, used when a merged spec creates `loop:implement` issues in other repos. Set them on the repos that hold specs; for a private repo on
  the GitHub Free plan (`hq`), they must be repo-level, since org variables and secrets don't reach it.
  `LOOP_GH_TOKEN` (fine-grained token, Issues read/write) still works as a fallback when the variable is not set.

The Factory Droid GitHub App must be installed on the org; workflows authenticate through it.

## Auto-merge

When an allowed approver (input `approvers`, default `NazarUsik`) approves a PR, `loop-automerge` turns on GitHub
auto-merge for the approved commit, as the `crucible-smith` app. Every review and push re-checks it, so a new push
turns it off until the new head is approved. GitHub merges once the branch ruleset is satisfied,
so the ruleset is what makes it safe: require 1 approval from a code owner (`.github/CODEOWNERS`: `* @NazarUsik`),
dismissed on new pushes, resolved conversations, and the
`review / review` check plus the repo's CI checks. The repo also needs "Allow auto-merge" turned on and the
`SMITH_CLIENT_ID` variable and `SMITH_PRIVATE_KEY` secret. Without them the job skips with a notice. Private repos on the
Free plan have no rulesets or auto-merge; merge those by hand.

## Use the plugin locally

```sh
droid plugin marketplace add crucibledx/factory-loop
droid plugin install crucible-loop@factory-loop --scope user
```

Repos with the template `.factory/settings.json` enable it automatically.

## Versioning

Callers pin `@v0`. Breaking changes to workflow inputs or skill contracts bump the major tag.
