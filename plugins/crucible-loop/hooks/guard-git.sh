#!/bin/sh
# Blocks the few git/gh actions the Crucible loop reserves for a human:
# pushing to the default branch, force pushes, and merging PRs.
python3 -c '
import json, re, sys
data = json.load(sys.stdin)
cmd = (data.get("tool_input") or {}).get("command", "") or ""
rules = [
    (r"gh\s+pr\s+merge\b", "Merging PRs is reserved for Nazar. Leave the PR ready for review."),
    (r"gh\s+api\s+.*\bmerge\b", "Merging PRs is reserved for Nazar. Leave the PR ready for review."),
    (r"git\s+push\b.*(\s--force(?!-with-lease)\b|\s-f\b)", "Force pushes are not allowed. Push a new commit instead."),
    (r"git\s+push\b.*(\s|:)(refs/heads/)?(main|master)(\s|$)", "Pushing to main is not allowed. Push a branch and open a PR."),
]
for pattern, reason in rules:
    if re.search(pattern, cmd):
        print(reason, file=sys.stderr)
        sys.exit(2)
sys.exit(0)
'
