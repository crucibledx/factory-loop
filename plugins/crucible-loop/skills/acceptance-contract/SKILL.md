---
name: acceptance-contract
description: Define an executable standard of completion for a spec before implementation starts. Inventory every observable behavior and attach a runnable check to each. Use when writing or revising the Acceptance contract section of a Crucible spec.
---

# Acceptance contract

Agents stop when they believe they are done. Their checks cover what they thought to build and miss what they never
represented. The contract fixes this: the whole outcome is inventoried and made checkable before any code exists, and
the implementation is measured against it rather than against itself.

## Build the inventory

Derive behaviors from the spec's Goals and Design, and from sources of truth (existing CLI help, docs, config schemas,
the harness formats being targeted). For each one, ask: how would a user notice this works, or fails?

Cover, at minimum:

- every command, flag, config key, or page the spec adds or changes, including the error path for each;
- each supported harness or platform separately (Droid, Claude Code, Codex, Cursor, ...), when behavior differs;
- compatibility: what existing behavior must stay the same;
- docs and website changes the spec promises.

## Attach a check to each behavior

| Check type     | Use for                         | Example                                                    |
|----------------|---------------------------------|------------------------------------------------------------|
| `test`         | logic, parsing, domain rules    | `bun test test/compiler/merge.test.ts`                     |
| `cli snapshot` | CLI output and exit codes       | `forge sync --dry-run` in a fixture repo, compare snapshot |
| `e2e`          | multi-step flows on a real repo | e2e framework scenario name                                |
| `screenshot`   | web pages                       | page URL + viewport, captured in the PR                    |
| `doc`          | docs that must exist or change  | file path + section heading                                |

A check must be runnable by someone other than the implementer and give pass/fail without judgment. If a behavior
cannot be checked automatically, say exactly what evidence the PR must include.

## Rules

- IDs are stable (`AC-1`, `AC-2`, ...). Never renumber.
- During implementation the contract is frozen. Changes are proposed in the implementation PR description and approved
  by Nazar.
- Prefer 10-40 rows. Fewer usually means behaviors are missing; more usually means the spec should be split.
