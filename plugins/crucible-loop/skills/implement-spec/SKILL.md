---
name: implement-spec
description: Implement an approved Crucible spec or a scoped GitHub issue in one repo and own the PR until it is green and has no open review findings. Runs a local implement/verify/review loop, then answers the PR reviewer in batches until the review gate passes. Use when asked to implement a spec or an issue, or when dispatched by the loop orchestrator.
---

# Implement spec

Input: a merged spec, or a GitHub issue small enough to act as its own spec. Output: a PR whose CI and `review` check
are green on the latest commit, with no unresolved P0/P1 review threads, marked ready for review. Or a draft PR with a
clear escalation. You own the PR until one of those two states; do not stop earlier and do not wait to be asked.

## Before coding

1. Read the spec (or issue) end to end, the repo's `AGENTS.md`, its loop contract (`.factory/loop-contract.md`), and the
   `engineering-standards` skill. Follow the standards from the first commit; the PR reviewer checks them.
2. Read the code the change touches. List the acceptance contract rows that apply to this repo.
3. **Size budget:** one PR should stay under ~1,500 changed lines including tests. If the work is bigger, split it into
   milestones that each close a group of contract rows and ship as separate PRs. Ask in the issue before starting if
   the spec does not allow a split.
4. Work in your own clone or worktree under `~/crucible-agents/` on branch `loop/<issue>-<slug>`. Never in
   `~/crucible/projects/`. Parallel agents never share a branch.

## Local loop (before the PR, max 3 rounds)

1. **Implement** in small, coherent commits in the repo's commit style, with tests for each contract row.
2. **Run the repo checks** from the loop contract (format, lint, typecheck, tests, build). Fix failures.
3. **Verify** with the `verifier` droid (spec path + branch) and **review** with the `code-reviewer` droid in parallel.
4. **Fix** every failed row and every finding you agree with. Stop when rows pass, checks are green, and there are no
   blocking findings.

## PR loop (after the PR is open)

Open the PR as draft first so the hosted review runs once on a complete change, then mark it ready. Then repeat:

1. **Wait** for every check on the head commit, including `review`: `gh pr checks <n> --watch`. Never act on results
   from an older commit.
2. **Collect everything at once:** failing CI jobs (`gh run view <id> --log-failed`) and every unresolved review
   thread (GraphQL `reviewThreads` with `isResolved`, or the gate output in the `review` job summary).
3. **Fix all of it in one batch** and run the repo checks locally. Commit, but do not push yet.
4. **Reply on each thread before pushing**, so the follow-up review sees your replies. Use a direct reply (never a
   pending review):
   `gh api repos/<owner>/<repo>/pulls/<n>/comments/<comment_id>/replies -f body="Fixed in <sha>: <what changed>"`.
   If you disagree or the finding is out of scope, reply with the reason and the follow-up issue link instead. Do not
   resolve the reviewer's threads yourself; the follow-up review resolves them after checking. If the reply fails
   with "one pending review per pull request", Nazar has an unsubmitted review on the PR (agents use his account).
   Do not submit or discard it, and do not push: ask Nazar where the work was requested to submit or discard his
   review, wait, then post the replies and continue. The follow-up review reads only thread replies.
5. **Push once.** One push per round, not one per finding. If the round had replies only (no code change), push an
   empty commit (`git commit --allow-empty -m "chore: request follow-up review"`) so the follow-up review judges
   the replies; nothing else re-runs it.
6. **Done** when CI and `review` are green on the head commit and no P0/P1 thread is unresolved. P2 threads: fix them
   or answer with a reason; they do not block. Update the PR body (below), mark ready, and post the PR link where the
   work was requested (Slack thread or issue).

## When to stop and ask Nazar

Keep the PR as draft and comment with the open items, what you tried, and the decision needed, when:

- the PR grew past 1.5x its first reviewed size (the review posts a scope warning), or past the size budget;
- the same thread came back "Not fixed" twice;
- 6 PR rounds passed without reaching done;
- a finding needs a spec change or a product decision.

## PR body

Link to the spec and issue; a table of contract rows with pass/fail and the check that proves it; review findings you
rejected, with the reason; anything Nazar should look at first. Keep it short. No adjudication documents, evidence
bundles, or attestation tooling in the repo unless the spec asks for them.

Link the issue with a closing keyword only when this PR finishes it:

- `Closes #<n>` (or `Closes <owner>/<repo>#<n>` for another repo) when every contract row this issue covers passes
  in this PR. GitHub closes the issue when the PR merges.
- `Part of #<n>` (or `Part of <owner>/<repo>#<n>` for another repo) when the work is split across PRs. List the rows
  still open. The orchestrator closes the issue after the last PR merges.

## Rules

- Never edit the spec's acceptance contract. If a row is wrong or impossible, explain it in the PR and leave it failing.
- Never push to `main`, never force-push, never merge.
- Releases (version bumps, tags, publishing) are out of scope unless the spec says otherwise.
- Stay inside the spec. Unrelated improvements, including pre-existing problems the reviewer finds, go in follow-up
  issues, not this PR.
