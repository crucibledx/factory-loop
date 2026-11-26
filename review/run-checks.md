
## Running checks

The runner has the repo's toolchain: Bun and the installed dependencies when the repo has `bun.lock`, and `actionlint`
when the loop contract lists it. Run the loop contract's checks that the diff affects, the quick and focused ones
first, for at most about 10 minutes in total. A check that cannot start because a tool or module is missing is "could
not run", not a finding. Say in `summary` which checks you ran and which you could not.
