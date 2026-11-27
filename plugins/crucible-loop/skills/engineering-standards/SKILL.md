---
name: engineering-standards
description: Crucible org engineering standards for design, architecture, tests, and code style (TypeScript and Go). Read before implementing or reviewing code in any crucibledx repo. The PR reviewer checks changes against it; repo AGENTS.md and CONTRIBUTING.md add repo-specific rules and win on conflict.
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

## 2. Design

- Make the change in the place that owns the behavior; extend through the existing extension points (registries,
  `how-to-add-*` guides) instead of special cases in callers. [P2]
- Adding a variant (assistant, source, command, transform) means a new folder (or a Go file) plus one registration,
  with zero edits to existing handlers. [P2]
- Validate input at the boundary (config files, CLI args, network, file contents) with a schema (`zod` in TS repos;
  in Go, decode into typed structs and validate them in one function); inside the core, trust the types. [P1 when
  unvalidated external input reaches the core]
- Errors: fail with a message that tells the user what to do. Never swallow an error silently; never print a stack
  trace for an expected failure. [P1 for swallowed errors on user paths]
- Cross-platform: macOS, Linux, and Windows are supported. Use path utilities, not string concatenation with `/`;
  no shell-specific commands in product code. [P1]
- Security: no secrets in code, logs, or test fixtures; no shell interpolation of untrusted input; file writes stay
  inside the intended directory. [P0/P1]

Library first (TypeScript and Go):

- Before writing code for a general problem (parsing, retries, schemas, protocol clients, CLI flags, telemetry), look
  in this order: the standard library, a dependency the repo already has, a well-maintained library, and only then
  your own code. Don't add a dependency for something the first two already do. [P2]
- A library fits when all of these hold. The PR lists them for every new direct dependency (a `go.mod` `require`
  without `// indirect`, a `builder-config.yaml` component, a `package.json` dependency); transitive ones count
  under cost.
  - **Solves the problem through its public API**, without a fork, a patch, reflection on its internals, or an
    adapter bigger than the code it replaces. [P2]
  - **Maintained:** a release or commit in the last 12 months, not archived or deprecated. Go: a tagged semver
    release. [P2]
  - **Used:** widely depended on (npm downloads, pkg.go.dev importers) or published by the project that owns the
    protocol (`golang.org/x`, OpenTelemetry, Cloudflare, Slack). [P2]
  - **License** compatible with MIT: permissive (MIT, BSD, ISC, Apache-2.0) or file-level copyleft (MPL-2.0). No
    GPL, LGPL, AGPL, SSPL, or unlicensed code in shipped code. [P1]
  - **No known vulnerabilities:** the package manager's audit (`bun audit`, `govulncheck`) and public
    advisories. [P1]
  - **Acceptable cost:** transitive dependencies, binary size and startup for a CLI or agent, bundle size for a web
    app or Worker. Go: no cgo unless the repo already needs it, and it builds for every supported OS. [P2]
- Write your own when no library fits, or when the code is short (under ~50 lines) and a library would cost more
  than it saves. Hand-writing what a library that fits already does is [P2]: the reviewer names the library, and the
  PR says why it doesn't fit.
- I/O libraries (HTTP, database, SDK clients) are used only in the I/O layer (`infrastructure/`, Go adapters);
  pure libraries (`zod`, parsers, data models) may be used anywhere. [P2]

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

## 5. Go repos

Go repos follow this section instead of section 3 and the TypeScript-specific rules in section 4. The naming and
comment rules in section 4 and all other sections apply to both.

Layout (domain-driven, the Go form of section 3):

```text
cmd/<name>/                main.go (flags, wiring, run) and generated wiring; nothing else
internal/<context>/        one package per bounded context: its types, rules, use cases, and the interfaces it needs
internal/<adapter>/        one package per technology at the edge: CLI, HTTP, storage, clients, the collector
internal/tools/            repo tooling run with `go run` (see Make)
e2e/commands/              end-to-end tests, one file per command
e2e/contracts/             repo-level contract tests (see Tests)
```

- Each binary is `cmd/<name>/main.go`. `main` parses flags, wires adapters into contexts, and runs; logic lives in
  packages. Generated wiring (marked `// Code generated ... DO NOT EDIT.`, such as a collector's `components.go`)
  may sit next to it. [P2]
- All other packages live under `internal/`. No `pkg/` unless its packages are a public API that other modules
  import. [P2]
- The repo's `AGENTS.md` lists its context packages; every other package under `internal/` is an adapter or tooling.
  [P2]
- A context package is named for its part of the domain (`budget`, `ingest`, `redact`) and does no I/O: it
  doesn't import `os`, `os/exec`, `net`, `net/http`, `database/sql`, or a network or SDK client. It takes
  `io.Reader`, `io.Writer`, `context.Context`, and its own interfaces instead. `net/url`, `net/netip`, and
  data-model libraries (such as the collector's `pdata`) are fine. [P1]
- Adapters are thin: decode and validate input (section 2), call the context, encode the result. A business rule
  (a decision, a limit, a default) in an adapter moves into its context. [P2]
- Imports point inward: `cmd` imports adapters and contexts, adapters import contexts, and a context never imports
  an adapter or `cmd`. When two contexts need each other, the shared part becomes its own context. A repo can
  enforce this with golangci-lint `depguard`. [P1]
- Name a package for what it provides (`config`, `store`); no `util`, `common`, `helpers`, `shared`, `models`,
  `types`, or `interfaces`. Types live with the context that owns them. [nit]

Size (soft limits for `.go` files; generated files, marked `// Code generated ... DO NOT EDIT.`, are exempt):

| Unit | Aim | Over the limit | Severity when the PR adds or grows one past it |
| --- | --- | --- | --- |
| `.go` file (non-test) | ≤ 300 lines | > 500 lines | [P2] |
| `_test.go` file | ≤ 500 lines | > 800 lines | [P2] |
| Function or method | ≤ 50 lines | > 80 lines | [P2] |
| Package | ≤ 15 non-test files | > 25 non-test files | [nit] |

- Between "aim" and "over the limit" is a [nit] at most. A file's lines are `wc -l`; a function's run from `func` to
  its closing brace, and a test function's case table doesn't count.
- Code that was already over the limit is a follow-up issue, unless the PR grows it.
- Going over is fine when splitting would hurt (one cohesive state machine, a lookup table): the PR body says
  why, and the reviewer accepts a stated reason.
- A repo that enforces the function limit sets golangci-lint `funlen` to `lines: 80` and `statements: -1` and
  excludes `_test.go` files from it; reviewers then leave function length to the linter.

Refactoring:

- Split a file along domain concepts: one main type and its methods per file (`budget.go`, `window.go`), not by
  kind (`types.go`, `errors.go`, `consts.go`). [nit]
- Extract a package when a group of types is its own bounded context, when two packages need the same domain code,
  or when a context package does I/O (the I/O moves to an adapter). Don't extract a package for one caller's
  helpers or to group things by kind. [P2]
- Interfaces belong to the consumer: declare them in the package that calls them, next to that code, with only
  the methods it uses (usually 1 to 3). Producers return concrete types. No interface for a type that has one
  implementation and no test fake. No `I` prefix or `Interface` suffix. [P2] An adapter may assert it implements
  its port at compile time: `var _ ingest.Store = (*Store)(nil)`. [nit]
- Constructors: `New<Type>(store, clock, cfg Config)` returns a ready value, with `error` when it can fail.
  Required dependencies are parameters; optional settings are a `Config` struct validated in `New`. No `Init()`
  after `New`. A constructor doesn't start goroutines or open connections unless its name says so (`Open`, `Dial`,
  `Start`), and what it starts has a `Close` or `Stop`. Functional options only for a public API with many
  optional settings. [P2]
- Code that implements a framework's interface (an OpenTelemetry Collector component or factory) follows that
  framework's constructor, config-validation and lifecycle conventions (`NewFactory`, `Config.Validate`,
  `Start`/`Shutdown`); the rules above apply to the context code behind it. [P2]
- Functions that do I/O or block take `ctx context.Context` first; never store a context in a struct. [P2]
- A PR that moves code doesn't change the moved code's behavior, and its tests change only package clauses,
  imports, and qualifiers. A move over ~300 changed lines is its own PR. [P2]

Errors:

- Wrap with context and `%w`: `fmt.Errorf("load config: %w", err)`. Don't return another package's error bare,
  unless an interface contract requires the bare value (`io.EOF` from `Read`). [P2]
- Check errors with `errors.Is` / `errors.As`, never with `==` or by comparing `err.Error()` text. [P2]
- Sentinel errors (`var ErrNotFound = errors.New(...)`) only where a caller branches on them; otherwise return a
  wrapped error. [P2]
- No `panic` outside `main` and init-time registration (for example a duplicate adapter name). Everything else
  returns an error. `Must*` helpers on constant input at package level (`regexp.MustCompile`) are fine. [P1]

State:

- No package-level mutable variables: no global clients, config, caches, or counters. Pass dependencies as arguments
  or struct fields. Allowed: constants, sentinel errors, values never reassigned or mutated after package init
  (lookup tables, compiled regexps), and an adapter registry (such as harness adapters) filled only by registrations
  in `init()` and read-only after that. [P2]
- `init()` only registers. No I/O, no env or flag reads, no goroutines. [P2]

Tests, in three layers like forge-cli (unit next to the code, contracts, e2e):

- **Unit:** `*_test.go` next to the code, run by `make test`. Contexts are tested with in-memory fakes of their
  own interfaces; adapters against `httptest` servers and `t.TempDir()`. Adapters take their directories (home,
  config, state) as parameters; where code calls `os.UserHomeDir` or `os.UserConfigDir`, the test sets `HOME`,
  `USERPROFILE`, `APPDATA`, and `XDG_CONFIG_HOME`. No network, no real home directory. [P2]
- **Contract:** two kinds. [P2 when a port has no shared suite; a spec promise without a test is P1 under section 6]
  - A port with more than one implementation (including a test fake) has one shared suite,
    `internal/<context>/<port>test.Run(t, newImpl)`, run against every implementation, so fakes can't drift from the
    real thing. `<port>test` imports the context for the port's type, so the context's own tests that run the suite
    are in an external test package (`package ingest_test`).
  - Cross-cutting promises from the spec live in `e2e/contracts/`: security (redaction, no secrets in output,
    file confinement), platform (paths and permissions on each OS), compatibility (flags, exit codes, output and
    wire formats, config schema), and performance bounds.
- **E2E:** `e2e/commands/` runs the real binary with `os/exec` against temp directories and local fake servers; no
  real network or credentials. Every command or endpoint the repo implements has at least one success and one
  failure case (exit code and message). [P2]
- Each e2e package's `TestMain` builds the binary through one shared helper package (`e2e/harness`): into a
  directory from `os.MkdirTemp`, named `name + ".exe"` on Windows, removed after `m.Run()`. `TestMain` then returns
  without a value (since Go 1.15 the binary exits with `m.Run()`'s code); it never calls `os.Exit`, which would
  skip the cleanup. [P2]
- `e2e/` sits behind the `e2e` build tag and runs with `make e2e`; port suites run with `make test`; `make check`
  runs both. The golangci-lint config sets `run.build-tags: [e2e]` and `make lint` vets with `-tags e2e`, so tagged
  code is linted too. [P2]
- Table-driven tests with `t.Run` subtests when cases share a shape. [nit]
- Fixtures live in `testdata/` next to the package that reads them; files a test writes go in `t.TempDir()`. [nit]
- CI runs `go test -race ./...` (the race detector needs cgo enabled for that step). [P2]

Make:

- A Go repo has a root `Makefile` as its one task runner, locally and in CI. Required targets: `build`, `test`
  (`CGO_ENABLED=1 go test -race ./...`), `lint` (`golangci-lint run`), `fmt`, `e2e`, and `check` (the checks CI
  runs on every PR, in order; release builds may stay separate targets). A repo with generated code has
  `make generate` and a check that fails when regenerating changes tracked files. `.factory/loop-contract.md` lists
  the targets as the checks. [P2]
- CI calls the targets, not the commands inside them, except that lint may use `golangci/golangci-lint-action` with
  the version from the same variable the Makefile uses. Windows lanes run `make` from `shell: bash`; if a runner has
  no `make`, the step runs the target's recipe word for word and a comment names the target. [P2]
- Targets are `.PHONY`, call `go` and pinned tools with plain arguments (POSIX `sh`, no bash-only syntax), and
  don't install tools (`go install`, `curl`) unless their name says so (`make tools`); module downloads by `go`
  itself are fine. [P2]
- Tool versions are pinned in one place: a Makefile variable, or a `tool` directive in a separate tools module
  (`go tool -modfile=tools/go.mod`). Never put golangci-lint or a code generator in the product's `go.mod`: its
  dependencies would change the shipped binary's versions. [P2]
- A shell script stays only where `make` is worse (loops, parsing, multi-step release logic); a target calls it,
  and a comment at its top says why it isn't a target. Past ~30 lines of shell code (not counting comments and
  blank lines), it becomes a Go program in `internal/tools/` run with `go run`. [P2]

Lint and format:

- CI runs `golangci-lint` with a checked-in config (`version: "2"`) that enables the `gofmt` and `goimports`
  formatters, so code is `gofmt`/`goimports` clean. [P2]
- Reviewers never comment on what golangci-lint enforces.
- A `//nolint` names the linter and the reason: `//nolint:errcheck // best-effort cleanup`. [nit]

## 6. Tests

- Every behavior change has a test that fails without the change. [P1 when an acceptance-contract row has no test]
- A test must test what its name says. Tests that only assert a mock was called, or that pass with the code deleted,
  don't count. [P1]
- Unit tests sit next to the code (`*.test.ts`, `*_test.go`) and mock only at the I/O boundary (`infrastructure/` in
  TS, the interfaces a Go context declares for its adapters), never whole files of domain logic. [P2]
- End-to-end tests use temp directories and run the real CLI or app. No network in unit tests. [P2]
- No snapshot tests of large generated output unless the output is the product. [nit]

## 7. Git, CI, and releases

- Commits follow the repo's commit style from its `AGENTS.md` or loop contract. [nit]
- CI must be green: format check, lint, typecheck, tests, build. A PR never disables or skips a check to get green. [P1]
- Version bumps, tags, and publishing happen only in a release PR or when the spec says so. [P1]
- Docs: update the README, `AGENTS.md`, or `docs/` when the change alters a command, config key, or workflow users
  or agents rely on. [P2]
