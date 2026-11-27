# factory-loop

The Crucible delivery loop for [Factory Droid](https://factory.ai): an idea becomes a reviewed spec PR, and an approved
spec becomes a tested implementation PR. Shared by every `crucibledx` repo, so each repo only keeps what is specific to
it.

## How the loop works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/dark/delivery-loop.svg">
  <img alt="Crucible delivery loop: board stages, Root routing code work to the Forge, Ember and Other workstreams, who acts at each stage, and how every problem reaches Root through problems.jsonl" src="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/light/delivery-loop.svg">
</picture>

1. A request arrives in Slack. An idea goes through discovery and a spec PR checked by two reviewer droids; merging
   the spec creates one `loop:implement` issue per target repo. Code work that the Slack bridge does not route straight
   to a workstream (see below) goes to the Root workstream, which opens the issue with a `ws:*` label and hands it to
   the Forge, Ember or Other workstream.
2. Each workstream's orchestrator starts one agent per issue, each in its own worktree and branch.
3. The agent implements, runs the repo's checks and the local `verifier` and `code-reviewer` droids, and opens a
   draft PR. It marks the PR ready once they pass.
4. `loop-review` reviews the PR. The `review / review` check stays red while a P0 or P1 finding is open.
5. The agent fixes the findings, replies on each thread, and pushes. The next review covers the new commits and
   resolves what is fixed.
6. With CI and the review gate green, Nazar reviews and approves. His approval turns on auto-merge, and GitHub merges.
   If the PR is already mergeable, the `crucible-smith` app merges the approved commit once its required checks pass.
7. Every agent reports every problem it hits with a tool, skill, script, automation, CI, relay or machine setup, fixed
   or not, to its workstream's orchestrator, which records it in `~/crucible-agents/.workstream/problems.jsonl` (hq
   `docs/workstream.md`, "Problem reports"). Root reads the new lines on each tick, acts on the unfixed ones, and lists
   the day's problems, fixed and unfixed, in the end-of-day summary. A loop fix ships as a PR to this repo through the
   same gate, and moving the `v0` tag rolls workflow fixes out to every repo.

### Requests from Slack

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/dark/multiplayer-slack.svg">
  <img alt="Multiplayer Slack: messages from every Slack user go through the Slack bridge to the Root, Forge, Ember and Other workstreams, traced by Ember" src="https://github.com/crucibledx/assets/raw/main/factory-loop/diagrams/light/multiplayer-slack.svg">
</picture>

Anyone in the Slack channel can make a request. The Slack bridge (a Cloudflare Worker) checks each message, routes
it, records it, and delivers it to a workstream's relay: by a `forge:`, `ember:` or `other:` prefix (also as
`@Crucible ember:`), by the workstream that claimed the thread, or else by channel, which sends `#crucible-work` to
Root. Only once the relay accepts the message does the bridge acknowledge it in the thread. The workstream replies in
the requester's thread. Ember joins every session into one tree (Root, workstream, agent) and attributes it to the
active Slack user, and `slack-ledger.jsonl` records usage per requester.

The diagram sources are
[`factory-loop/diagrams/delivery-loop.drawio`](https://github.com/crucibledx/assets/blob/main/factory-loop/diagrams/delivery-loop.drawio)
and
[`factory-loop/diagrams/multiplayer-slack.drawio`](https://github.com/crucibledx/assets/blob/main/factory-loop/diagrams/multiplayer-slack.drawio)
in `crucibledx/assets`.

## What's inside

| Path                                  | What it is                                                              |
|---------------------------------------|-------------------------------------------------------------------------|
| `.factory-plugin/marketplace.json`    | Droid plugin marketplace `factory-loop`                                 |
| `plugins/crucible-loop/skills/`       | `idea-discovery`, `spec-writer`, `acceptance-contract`, `implement-spec`, `loop-orchestrator`, `engineering-standards` |
| `plugins/crucible-loop/droids/`       | `researcher`, `spec-reviewer-arch`, `spec-reviewer-product`, `code-reviewer`, `verifier` |
| `plugins/crucible-loop/hooks/`        | Guard: blocks pushes to `main`, force pushes, and PR merges             |
| `.github/workflows/loop-*.yml`        | Reusable workflows: review + merge gate, auto-merge on approval, `@droid` mentions, spec merged, org CI for Bun repos (`loop-ci`; `loop-implement` is deprecated) |
| `templates/repo/`                     | The thin per-repo files: caller workflows (`crucible-loop.yml`, `ci.yml`), `.factory/settings.json`, `.factory/loop-contract.md` |

## Add the loop to a repo

```sh
scripts/install.sh ~/crucible/projects/<repo>
```

Then edit `.factory/loop-contract.md` with the repo's real check commands. (A `## Loop contract` section in
`AGENTS.md` also works.)

`.github/workflows/ci.yml` calls `loop-ci`: format, lint, and typecheck scripts that `package.json` defines, `bun test`,
and an optional build. Set its `with:` inputs for repo-specific commands, and add `ci / quality`, `ci / test` (and
`ci / build` when `build_command` is set) as required checks on the `main` ruleset. `install.sh` keeps an existing
`ci.yml`; replace it by hand.

The caller's `review` job skips draft PRs itself, so the required `review / review` check only comes from runs on
non-draft PRs. `install.sh` keeps an existing `crucible-loop.yml`; in a repo that already has one, add
`&& !github.event.pull_request.draft` to the `review` job's `if` by hand.

`loop-review` reviews without running the repo's code by default. With `run_checks: true` in the caller's `review` job,
it installs Bun and the dependencies (when the repo has `bun.lock`) and `actionlint` (when the loop contract lists it),
and the reviewer runs the loop contract's checks. That runs PR code in a job holding `FACTORY_API_KEY` and a write
token, so turn it on only in repos where every PR author is trusted.

Secrets, set once:

- `FACTORY_API_KEY`: org secret for public repos; repo secret for private repos on the GitHub Free plan.
- `SMITH_CLIENT_ID` (variable, the app's client ID) and `SMITH_PRIVATE_KEY` (secret): the `crucible-smith` GitHub
  App, used when a merged spec creates `loop:implement` issues in other repos. Set them on the repos that hold specs,
  and on this repo for `loop-review-retry` (see below); for a private repo on
  the GitHub Free plan (`hq`), they must be repo-level, since org variables and secrets don't reach it.
  `LOOP_GH_TOKEN` (fine-grained token, Issues read/write) still works as a fallback when the variable is not set.

The Factory Droid GitHub App must be installed on the org; workflows authenticate through it.

## Auto-merge

When an allowed approver (input `approvers`, default `NazarUsik`) approves a PR, `loop-automerge` turns on GitHub
auto-merge for the approved commit, as the `crucible-smith` app. Every review and push re-checks it, so a new push
turns it off until the new head is approved. If the PR is already mergeable (GitHub refuses auto-merge then), it merges
the approved commit directly once every required check of the base branch has passed on it. Either way, GitHub merges
only once the branch ruleset is satisfied, so the ruleset is what makes it safe: require 1 approval from a code owner (`.github/CODEOWNERS`: `* @NazarUsik`),
dismissed on new pushes, resolved conversations, and the
`review / review` check plus the repo's CI checks. The repo also needs "Allow auto-merge" turned on and the
`SMITH_CLIENT_ID` variable and `SMITH_PRIVATE_KEY` secret. Without them the job skips with a notice. Private repos on the
Free plan have no rulesets or auto-merge; merge those by hand.

## Review at the usage limit

The hosted review runs `droid exec` on the same Factory plan as the workstreams. When the plan's usage limit stops
the reviewer, the `review / review` check stays red (the commit has no review), but the job reports it as a
"Review usage limit" error with the reset time, not as a review failure. `loop-review-retry` runs in this repo every
30 minutes as the `crucible-smith` app: it re-runs those review jobs in every repo the app is installed on, once the
limit has reset, while the PR is open, not a draft, and still at the same commit. Re-run the job by hand to go sooner.
It needs the `SMITH_CLIENT_ID` variable and `SMITH_PRIVATE_KEY` secret on this repo, and the app's installation needs
Actions write, Checks read (to read the job's annotations) and Pull requests read.

## Use the plugin locally

```sh
droid plugin marketplace add crucibledx/factory-loop
droid plugin install crucible-loop@factory-loop --scope user
```

Repos with the template `.factory/settings.json` enable it automatically.

## Versioning

Callers pin `@v0`. Breaking changes to workflow inputs or skill contracts bump the major tag.
