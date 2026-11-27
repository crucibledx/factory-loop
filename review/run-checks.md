## Running checks

The runner has the repo's toolchain from `.factory/toolchain.json` (or the inferred stack): a Bun repo has Bun and
the installed dependencies, a Go repo has Go, the downloaded modules and golangci-lint when its Makefile pins a
version, and a repo whose loop contract lists `actionlint` has it. The resolved stack, runners and check commands
are below. You may run the loop contract's checks that the diff affects, quick and focused ones first, for at most
about 10 minutes in total. They may leave build or test output; never edit tracked files. A check that cannot start
because a tool or module is missing is "could not run", not a finding. Say in `summary` which checks you ran and
which you could not.
