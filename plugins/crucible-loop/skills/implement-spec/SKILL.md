---
name: implement-spec
description: Implement an approved Crucible spec in one repo and drive it to a PR that is tested and ready for Nazar's final review. Runs the inner loop of implement, independent review, verification against the acceptance contract, and fix, with a round limit. Use for issues labeled loop:implement or when asked to implement a spec.
---

# Implement spec

Input: a `loop:implement` issue (or a direct request) that links a merged spec. Output: a PR that passes every check in
the spec's acceptance contract and CI, marked ready for review, or a draft PR with a clear escalation.

## Before coding

1. Read the spec end to end, the repo's `AGENTS.md`, and the `## Loop contract` section in it (check commands, commit
   style, release rules).
2. Read the code the spec touches. List the acceptance contract rows that apply to this repo.
3. For large specs (`size: mission`) plan milestones that each close a group of contract rows.

## Inner loop (max 4 rounds)

1. **Implement** on a branch `loop/NNNN-slug` (or the branch the workflow gives you). Small, coherent commits in the
   repo's commit style. Add or update tests for each contract row as you go.
2. **Run the repo checks** from the Loop contract (format, lint, typecheck, tests, build). Fix failures before moving on.
3. **Verify** with the `verifier` droid: give it the spec path and the branch. It runs every applicable contract check
   and reports pass/fail per row with evidence. It does not see your reasoning.
4. **Review** with the `code-reviewer` droid in parallel: correctness, security, maintainability, scope creep.
5. **Fix** every failed row and every review finding you agree with. Record rejected findings with a reason.
6. Stop when all applicable rows pass, checks are green, and the reviewer has no blocking findings. Otherwise start the
   next round.

## Finish

- **Done:** open (or update) the PR, title in the repo's commit style, body with: link to spec and issue, a table of
  contract rows with pass/fail and evidence, review findings and resolutions, and anything Nazar should look at first.
  Mark it ready for review.
- **Not done after 4 rounds:** keep the PR as draft, add a comment "Loop stopped after 4 rounds" with the failing rows,
  what was tried, and the decision needed. Do not keep looping.

## Rules

- Never edit the spec's acceptance contract. If a row is wrong or impossible, explain it in the PR and leave it failing.
- Never push to `main`, never force-push, never merge.
- Releases (version bumps, tags, publishing) are out of scope unless the spec says otherwise.
- Stay inside the spec. Unrelated improvements go in a follow-up idea, not this PR.
