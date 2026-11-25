---
name: spec-writer
description: Write a Crucible spec from an approved idea, get it reviewed by two independent reviewer droids, fix their findings, and open the spec PR. Use after idea discovery returns "go", or when asked to write or revise a spec.
---

# Spec writer

Output: one spec PR that Nazar can approve by merging. The spec must be good enough that a different agent can
implement it without asking questions, and it must define how completion is measured.

## Where the spec goes

- Org-level or cross-project: `crucibledx/hq`, file `specs/NNNN-slug.md`, `scope: org`.
- One project: that repo, file `specs/NNNN-slug.md`, `scope: project`.
- `NNNN` is the next free number in that repo's `specs/` folder.

Start from `hq/specs/_template.md` and follow `hq/specs/README.md`.

## Steps

1. Gather the idea issue, the preview brief, Nazar's answers, and the research notes. Read the code or docs the spec
   touches, so the design matches what exists.
2. Draft every section of the template. Be concrete: commands, file paths, config keys, data shapes, error cases.
   Mark real unknowns under Open questions instead of guessing.
3. Write the acceptance contract with the `acceptance-contract` skill. It is part of the spec, not an afterthought.
4. If `assets: needed`, follow the assets section below.
5. **Independent review.** Run the `spec-reviewer-arch` and `spec-reviewer-product` droids in parallel on the draft.
   Give each the spec path and the idea brief, nothing else.
6. Fix every finding you agree with. For findings you reject, note why in the PR description. Run the reviewers once
   more if you changed the design; stop after two rounds.
7. Set frontmatter `status: approved` (merging the PR is the approval) and link `idea_issue`.
8. Open the PR on a branch `spec/NNNN-slug`, title `spec(NNNN): <title>`, label `spec`. The description contains: a
   five-line summary, the reviewer findings and how each was resolved, and open questions for Nazar.
9. Move the idea issue to `stage:spec-review` and link the PR. If you came from Slack, post the PR link in the thread.

## Assets

Diagrams, demo recordings, and images live in `crucibledx/assets` (Git LFS; run `git lfs install` first). Open a
companion PR there on a branch with the same name, put the sources (`.drawio`, `.tape`) and rendered files in the
product's folder, and link both PRs to each other. The spec references the final raw GitHub URLs.

## Rules

- Never push to `main`; never merge.
- Keep the spec under ~400 lines. Split into several specs if it grows beyond that.
- Size the implementation: each implementation PR should stay under ~1,500 changed lines including tests. If the spec
  needs more, define milestones in the spec, each closing a group of contract rows and shipping as its own PR.
- Do not ask for readiness checkers, evidence bundles, or attestation tooling unless Nazar asked for them. The
  acceptance contract plus CI is the evidence.
