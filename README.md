# factory-loop

The Crucible delivery loop for [Factory Droid](https://factory.ai): an idea becomes a reviewed spec PR, and an approved
spec becomes a tested implementation PR. Shared by every `crucibledx` repo, so each repo only keeps what is specific to
it.

```
idea (Slack / hq issue) → discovery brief → spec PR ──merge──▶ loop:implement issue → implementation PR (ready, green)
                                  ▲ 2 reviewer droids                       ▲ verifier + code-reviewer, ≤ 4 rounds
```

## What's inside

| Path                                  | What it is                                                              |
|---------------------------------------|-------------------------------------------------------------------------|
| `.factory-plugin/marketplace.json`    | Droid plugin marketplace `factory-loop`                                 |
| `plugins/crucible-loop/skills/`       | `idea-discovery`, `spec-writer`, `acceptance-contract`, `implement-spec`, `loop-orchestrator` |
| `plugins/crucible-loop/droids/`       | `researcher`, `spec-reviewer-arch`, `spec-reviewer-product`, `code-reviewer`, `verifier` |
| `plugins/crucible-loop/hooks/`        | Guard: blocks pushes to `main`, force pushes, and PR merges             |
| `.github/workflows/loop-*.yml`        | Reusable workflows: implement, review, `@droid` mentions, spec merged   |
| `templates/repo/`                     | The thin per-repo files: caller workflow, `.factory/settings.json`, AGENTS.md loop contract |

## Add the loop to a repo

```sh
scripts/install.sh ~/crucible/projects/<repo>
```

Then append `templates/repo/AGENTS.loop-contract.md` to the repo's `AGENTS.md` with its real check commands.

Secrets, set once:

- `FACTORY_API_KEY`: org secret for public repos; repo secret for private repos on the GitHub Free plan.
- `LOOP_GH_TOKEN`: fine-grained token, Issues read/write on the crucibledx repos, used when a merged spec creates
  `loop:implement` issues in other repos.

The Factory Droid GitHub App must be installed on the org; workflows authenticate through it.

## Use the plugin locally

```sh
droid plugin marketplace add crucibledx/factory-loop
droid plugin install crucible-loop@factory-loop --scope user
```

Repos with the template `.factory/settings.json` enable it automatically.

## Versioning

Callers pin `@v0`. Breaking changes to workflow inputs or skill contracts bump the major tag.
