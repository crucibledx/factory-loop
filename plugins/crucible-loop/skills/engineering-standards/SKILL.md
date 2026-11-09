---
name: engineering-standards
description: Crucible org engineering standards for design, architecture, tests, and code style. Read before implementing or reviewing code in any crucibledx repo. The PR reviewer checks changes against it; repo AGENTS.md and CONTRIBUTING.md add repo-specific rules and win on conflict.
---

# Crucible engineering standards (v1)

These rules apply to every crucibledx repo. A repo's `AGENTS.md` / `CONTRIBUTING.md` can be stricter or override a
rule; say so there explicitly. Severity hints in brackets tell the reviewer how to classify a violation
(see `review/prompt.md`): **[P1]** blocks the merge, **[P2]** should be fixed or answered, **[nit]** never blocks.

## 1. Scope and size

- One behavior per PR. Unrelated cleanups, refactors, and pre-existing problems go in follow-up issues. [P2]
- Aim for under ~1,500 changed lines per PR including tests; split larger work into milestones. [P2]
- No process artifacts in the repo unless the spec asks: adjudication docs, evidence bundles, readiness or attestation
  scripts, review transcripts. The PR body and CI are the record. [P2]
- Don't add a dependency for something the standard library or an existing dependency already does. [P2]
- Prefer a maintained open-source library over writing your own when one already solves the problem well. Every new
  dependency must be checked before it is added, and the PR says so: license compatible with MIT (no GPL/AGPL in
  shipped code), no known vulnerabilities (the package manager's audit and public advisories), actively maintained,
  and an acceptable size, install, and runtime cost for the product that ships it (binary size and startup for a
  CLI, bundle size for a web app). [P1 for an incompatible license or a
  known vulnerability; P2 for an unchecked or heavy dependency, or for reinventing what a vetted library does]

## 2. Design

- Make the change in the place that owns the behavior; extend through the existing extension points (registries,
  `how-to-add-*` guides) instead of special cases in callers. [P2]
- Adding a variant (assistant, source, command, transform) means a new folder plus one registration, with zero edits
  to existing handlers. [P2]
- Validate input at the boundary (config files, CLI args, network, file contents) with a schema (`zod` in TS repos);
  inside the core, trust the types. [P1 when unvalidated external input reaches the core]
- Errors: fail with a message that tells the user what to do. Never swallow an error silently; never print a stack
  trace for an expected failure. [P1 for swallowed errors on user paths]
- Cross-platform: macOS, Linux, and Windows are supported. Use path utilities, not string concatenation with `/`;
  no shell-specific commands in product code. [P1]
- Security: no secrets in code, logs, or test fixtures; no shell interpolation of untrusted input; file writes stay
  inside the intended directory. [P0/P1]

## 3. Architecture (TypeScript repos)

DDD with three layers under `src/`:

- `domain/`: pure types, logic, schemas. No I/O, no framework dependencies. Imports only `domain`. [P1]
- `application/`: command handlers that orchestrate domain and infrastructure.
- `infrastructure/`: all I/O (filesystem, git, network, prompts, config parsing, logging). Never imports handler
  logic from `application` (types only). [P1]

Imports: path aliases across layers (`@domain/*`, `@application/*`, `@infrastructure/*`), relative imports within a
layer. [nit]

## 4. Code style (TypeScript)

- Functions, not classes: plain functions and object literals. Classes only for custom `Error` subclasses. [P2]
- Maps over `switch`: dispatch with `Record<Key, Handler>`. [nit]
- Const objects for unions:
  ```ts
  export const SYNC_FILE_STATUSES = {NEW: 'new', UPDATE: 'update'} as const
  export type SyncFileStatus = (typeof SYNC_FILE_STATUSES)[keyof typeof SYNC_FILE_STATUSES]
  ```
  [nit]
- Formatting and lint belong to the repo's Prettier and ESLint configs. Reviewers never comment on what these tools
  enforce.
- Names say what a thing is in the domain's words; no `utils.ts` grab bags, no `helpers2`. [nit]
- Comments explain why, not what. No commented-out code. [nit]

## 5. Tests

- Every behavior change has a test that fails without the change. [P1 when an acceptance-contract row has no test]
- A test must test what its name says. Tests that only assert a mock was called, or that pass with the code deleted,
  don't count. [P1]
- Unit tests sit next to the code (`*.test.ts`) and mock only at the infrastructure boundary, never whole files of
  domain logic. [P2]
- End-to-end tests use temp directories and run the real CLI or app. No network in unit tests. [P2]
- No snapshot tests of large generated output unless the output is the product. [nit]

## 6. Git, CI, and releases

- Commits follow the repo's commit style from its `AGENTS.md` or loop contract. [nit]
- CI must be green: format check, lint, typecheck, tests, build. A PR never disables or skips a check to get green. [P1]
- Version bumps, tags, and publishing happen only in a release PR or when the spec says so. [P1]
- Docs: update the README, `AGENTS.md`, or `docs/` when the change alters a command, config key, or workflow users
  or agents rely on. [P2]
