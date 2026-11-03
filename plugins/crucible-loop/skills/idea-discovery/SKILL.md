---
name: idea-discovery
description: Explore a raw Crucible idea with Nazar before any spec is written. Research the space, run the "complete, don't compete" check, ask a few sharp questions, and post a short preview brief. Use when a new idea arrives (Slack, an hq idea issue, or a direct request) or when someone says "dig into this idea".
---

# Idea discovery

Goal: help Nazar understand the idea better and decide, with evidence, whether it is worth a spec. You are a thinking
partner, not a cheerleader. Disagree when the evidence says so.

## Context to load first

1. `hq/AGENTS.md` (org context, principles, products). If not available locally, read it from `crucibledx/hq`.
2. The `AGENTS.md` of any project the idea touches.
3. Existing specs in `hq/specs/` and the project's `specs/` to avoid duplicates.

Crucible builds tools that make coding harnesses (Droid, Claude Code, Codex, Cursor, Kilo Code, ...) work better. Older
docs that describe it as "config management for AI assistants" are outdated.

## Scope

An idea's scope decides where its spec lives. Slack messages may start with a prefix (`ember:`, `[forge]`, `web/`):

| Prefix                  | Scope                  | hq label                    |
|-------------------------|------------------------|-----------------------------|
| `org`, `crucible`, `hq` | org-level (`hq/specs`) | `scope:org`                 |
| `forge`, `cli`          | `forge-cli`            | `repo:forge-cli`            |
| `ember`                 | `ember`                | `repo:ember`                |
| `web`, `site`           | `web`                  | `repo:web`                  |
| `starter`, `skills`     | `forge-skills-starter` | `repo:forge-skills-starter` |
| `assets`, `design`      | `assets`               | `repo:assets`               |

Without a prefix, infer the scope and state the guess so Nazar can correct it. An idea that spans products is org-level.

## Steps

1. **Restate the idea** in two or three sentences, the way you understand it.
2. **Research** with the `researcher` droid: who already does this (harness vendors, MCP servers, OSS), what they miss,
   recent changes in the space. Cite sources.
3. **Complete, don't compete check.** For each existing solution: does the idea replace it (bad) or make it better or
   connect it to others (good)? Would a harness vendor build this themselves soon?
4. **Ask 3-5 questions**, only ones whose answers change the design or the decision. Offer options where you can.
   Wait for answers. Repeat once if the answers open new forks; do not interrogate.
5. **Post the preview brief** (format below) and ask for a go / park / reshape decision.
6. On **go**: create or update the idea issue in `crucibledx/hq` (label `stage:discovery`, template Idea), attach the
   brief as a comment, and hand off to the `spec-writer` skill. On **park**: label `stage:parked` with the reason.

## Preview brief format

```
Idea: <one line>
Verdict: worth a spec | needs reshaping | park — <one line why>
Complements: <tools/harnesses it makes better>
Doesn't compete with: <what it explicitly won't replace>
Shape: <org-level spec | project spec in <repo>> · size: session | mission · assets: none | needed
Core bet: <the assumption that must be true>
Open risks: <2-3 bullets>
Sources: <links>
```

Keep it under 20 lines. In Slack, post it in the same thread.
