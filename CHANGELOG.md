# Changelog

## Unreleased

- `scripts/problems.py` skips a report line nested more than 32 levels deep before parsing it, so it gives the same
  result on every Python version. Before, it relied on json's `RecursionError`, which Python 3.9 raises on deep input
  but 3.12 does not, so a deeply nested line was skipped on 3.9 and read on 3.12, and `test-problems.py` failed on
  the CI runner's 3.12. Integers longer than 4300 digits, which 3.11 and later refuse, are skipped on 3.9 too.
- Reusable workflows pin every directly referenced third-party action to a release commit and version comment.
  Checkout v7.0.1, setup-bun v2.2.0, JUnit report v6.7.1, and create-github-app-token v3.4.0 run on Node 24;
  droid-action v14 is the current composite release. Workflow inputs and the `@v0` caller interface are unchanged.
- The end-of-day summary (`loop-orchestrator`) has a "Problems" section: the day's problem reports from
  `~/crucible-agents/.workstream/problems.jsonl`, fixed and open, grouped by kind. `scripts/problems.py` prints it,
  checks each line against the format in hq `docs/workstream.md` and skips invalid ones. README step 7 follows the
  rule that every problem is reported to Root, fixed or not.
- `loop-review` keeps PR code away from the write token (factory-loop#37). The new `reviewer` job runs collect, the
  `run_checks` installs and `droid exec` with read-only permissions, and uploads `result.json` as an artifact. The
  `review` job (still the required `review / review` check) needs it, holds the write token, and checks out only
  factory-loop. It takes nothing from the reviewer job but `result.json`, which it schema-checks; a blocking finding
  without a usable file and line keeps the head unreviewed, as one that cannot be threaded does. The head, mode,
  size and open threads come from the API, not `context.json`, and thread verdicts apply only to the reviewer's
  open threads. It runs even in a cancelled run and then fails, as it does when the reviewer job did not finish, so
  the required check is never skipped. `loop-review-retry` re-runs the stopped `reviewer` job, and GitHub re-runs
  the gate after it. Callers don't change. With `run_checks`, PR code can still read `FACTORY_API_KEY` and shape the
  verdict, so the input stays off by default. factory-loop's own self-review still runs the PR's workflow and
  `review/` scripts with the write token, by design.

## v0.6.0 — 2026-11-27

- The caller template's `review` job skips draft PRs (`!github.event.pull_request.draft`), and so does this repo's
  self review. Before, a PR opened as a draft and marked ready got two runs: the draft run's `review / review` was
  skipped inside `loop-review`, and GitHub could create that skipped check after the real review, so it became the
  check's newest result. Skipped counts as passed for rulesets and `loop-automerge`, so it hid the review's verdict,
  including a failing gate. Now a draft run reports only a skipped `review` check. `install.sh` keeps existing
  callers: add the condition to the `review` job's `if` by hand.
- `engineering-standards` holds Go to the same structure bar as TypeScript (implement and review stages): a
  domain-driven layout (context packages without I/O, thin adapters, imports pointing inward), soft size limits for
  files, functions and packages with their review severity, refactoring rules (when to extract a package, consumer-side
  interfaces, constructors), three test layers like forge-cli (unit, contract, e2e), and `make` as the task runner.
  Code implementing a framework's interface (Collector components) follows that framework's conventions. A new
  library-first rule for TypeScript and Go says when a library fits (MPL-2.0 now counts as compatible) and when to
  write your own; it replaces the two dependency rules in section 1. Section 6 names a Go context's interfaces as the
  mock boundary.
- `loop-review` has a `run_checks` input (default `false`). When it is on, the job installs the repo's toolchain
  before the review so the reviewer can run the checks in the repo's `.factory/loop-contract.md`: Bun (from
  `.bun-version`, else `package.json`) and the dependencies, without lifecycle scripts, when the repo has `bun.lock`;
  `actionlint` (checksum-verified) when the loop contract lists it. A failed install does not block the review, and
  the reviewer is told. This runs PR code in a job with `FACTORY_API_KEY` and a write token, so turn it on only where
  every PR author is trusted. Without it, the prompt now tells the reviewer not to run any repository code. Both
  checkouts move to `actions/checkout` v7.0.1 (Node 24), and every action in the job is pinned to a commit SHA.
- When the Factory usage limit stops the reviewer (`droid exec` 402), `loop-review` reports a "Review usage limit"
  error with the reset time instead of an unexplained failure. A new scheduled workflow in this repo,
  `loop-review-retry`, re-runs those review jobs (only the review job) across the org as the `crucible-smith` app
  once the limit has reset, so the PR gets its review without a manual re-run. The app's installation needs Actions
  write, Checks read and Pull requests read, and this repo needs `SMITH_CLIENT_ID` and `SMITH_PRIVATE_KEY`.
- README's multiplayer Slack caption follows the bridge's order: check, route, record, deliver to the workstream's
  relay, and only then acknowledge in the thread, with prefix routing ahead of the thread claim and the channel.

## v0.5.1 — 2026-11-26

- `loop-automerge` merges an approved PR directly when it is already mergeable (`CLEAN`, or `UNSTABLE` because a
  non-required check such as its own job is pending or failed), where GitHub refuses to turn on auto-merge. It merges
  only the approved head, and only once every required check of the base branch (rulesets and branch protection) has
  passed on it; while one is still pending it turns on auto-merge as before. The app token now also reads checks and
  commit statuses.
- README shows the multiplayer Slack diagram next to the delivery loop diagram, and the loop steps name the four
  workstreams (Root routes code work to Forge, Ember and Other). `AGENTS.md` keeps both diagrams in sync with
  `crucibledx/assets`.

## v0.5.0 — 2026-11-25

- New reusable `loop-ci` workflow for Bun repos: the format, lint and typecheck scripts that `package.json` defines,
  tests (`bun test --pass-with-no-tests` by default), and an optional build, with the repo's commands as inputs. It
  follows the repo's pinned Bun version and passes repos without `package.json` with a notice. The template ships a
  `ci.yml` caller and `scripts/install.sh` adds it.
- `loop-orchestrator` end-of-day summary has a usage per requester section (runs, agents, PRs) from the Slack ledger,
  read by `scripts/slack_usage.py`.
- `engineering-standards` has a Go section: layout, errors, package state, tests, and `golangci-lint`, each with a
  review severity.
- `loop-review`: the review gate waits (up to 40 minutes) for the head's review run still in progress instead of
  failing with "No completed review". The job needs `actions: read`.
- `loop-review` runs the review exec with `--auto medium`, without the write token or checkout credentials; a
  separate step posts the review.
- README shows the delivery loop diagram from `crucibledx/assets`; `AGENTS.md` keeps it in sync with the loop.

## v0.4.0 — 2026-11-10

- New `loop-automerge` workflow: auto-merge is on exactly while an allowed approver (default `NazarUsik`) has
  approved the current head, set by the `crucible-smith` app on every review and push. The template calls it, and
  ships `.github/CODEOWNERS` so rulesets can require that approval.
- `loop-spec-merged` authenticates as the `crucible-smith` GitHub App (`SMITH_CLIENT_ID` variable,
  `SMITH_PRIVATE_KEY` secret). `LOOP_GH_TOKEN` is now an optional fallback.
- App tokens use the app's client ID (`SMITH_CLIENT_ID` variable) instead of the deprecated `app-id` input of
  `actions/create-github-app-token`, pinned to the v3.3.0 commit.
- `implement-spec` writes `Closes #N` only when the PR finishes the issue and `Part of #N` when the work is split;
  `loop-orchestrator` closes split issues after their last PR merges.
- `loop-orchestrator` end-of-day and weekly summaries use a short Slack format: counts, Done, Needs you, Blocked,
  Next.

## v0.3.0 — 2026-11-09

- `implement-spec` owns the PR until CI and the review gate are green: batch fixes, direct thread replies, escalation
  rules instead of a fixed round limit, ~1,500-line PR budget.
- `spec-writer` sizes implementation milestones and skips evidence tooling unless asked.
- `loop-orchestrator` Workstream mode: one implementer agent per issue, WIP default 3.
- Template no longer calls `loop-implement` (deprecated; it never started a run).
- `engineering-standards` skill v1: org rules for scope, design, architecture, tests, style, and CI, each with a
  review severity. Read by the implementer, the local `code-reviewer` droid, and the PR review workflow.

## v0.2.0 — 2026-11-09

- `loop-review` v2: one consolidated review per push. The first review covers the whole PR; later reviews cover only
  new commits, judge every open finding (reply and resolve when fixed, reply "Not fixed" when not), and warn when the
  PR grew past 1.5x its first reviewed size.
- `loop-review` gates the merge: the check fails while P0/P1 reviewer threads are unresolved
  (`blocking_severities` input). Review submissions re-run only the gate, without a model call. The gate also fails while the checked-out commit has no completed review.
- New inputs `review_model` (default `openai-latest-balanced`), `reasoning_effort`, `blocking_severities`, `loop_ref`.
- factory-loop reviews its own PRs with the workflow from the PR branch (`self-review.yml`).
- Template: the `review` job also runs on `pull_request_review`.

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
