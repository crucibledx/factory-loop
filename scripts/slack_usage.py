#!/usr/bin/env python3
"""Usage per Slack requester for the end-of-day summary.

Reads the workstream Slack ledger (one JSON object per line with `at`, `event`,
`user`, `agent`, `pr`) and prints one line per requester with that user's runs
(`route` events), agents (`agent` events) and PRs (`pr` events) for the day, as
Slack mentions. Malformed lines are skipped with a warning on stderr. A missing
or empty ledger prints nothing and exits 0, so the summary just leaves the
section out; a ledger that cannot be read at all exits 1 with an error.

Usage: slack_usage.py [ledger-path] [YYYY-MM-DD]
Defaults: the workstream ledger at ~/crucible-agents/.workstream/slack-ledger.jsonl,
today in local time.
"""
import json
import os
import re
import sys
from datetime import date, datetime

DEFAULT_LEDGER = os.path.expanduser("~/crucible-agents/.workstream/slack-ledger.jsonl")
EVENTS = ("route", "agent", "pr")
USER_ID = re.compile(r"[A-Z][A-Z0-9]+")


def malformed_reason(entry):
    """Why a ledger entry cannot be counted, or None. Events the helper does not
    know are not malformed: they are ignored so new event types don't break it."""
    event = entry.get("event")
    if event not in EVENTS:
        return None
    user = entry.get("user")
    if not isinstance(user, str) or not USER_ID.fullmatch(user):
        return f"bad Slack user id {user!r}"
    if event in ("agent", "pr") and not (isinstance(entry.get(event), str) and entry.get(event)):
        return f"{event} event with no {event}"
    if entry_day(entry) is None:
        return f"bad timestamp {entry.get('at')!r}"
    return None


def load_entries(path, warn=None):
    """Parse the UTF-8 ledger, warning about and skipping blank or malformed lines.
    A missing file reads as empty; other read failures raise."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return []
    entries = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            if warn:
                warn(f"{path}:{lineno}: not JSON, line skipped")
            continue
        if not isinstance(entry, dict):
            if warn:
                warn(f"{path}:{lineno}: not a JSON object, line skipped")
            continue
        reason = malformed_reason(entry)
        if reason:
            if warn:
                warn(f"{path}:{lineno}: {reason}, line skipped")
            continue
        entries.append(entry)
    return entries


def entry_day(entry):
    """Ledger `at` is an ISO 8601 timestamp; return its local date or None."""
    at = entry.get("at")
    if not isinstance(at, str):
        return None
    try:
        return datetime.fromisoformat(at.replace("Z", "+00:00")).astimezone().date()
    except ValueError:
        return None


def aggregate(entries, day):
    """Per-user counters for one day. Agents and PRs are deduped by their id/URL."""
    users = {}
    for entry in entries:
        if entry_day(entry) != day:
            continue
        event = entry.get("event")
        if event not in EVENTS:
            continue
        user = entry.get("user")
        if not isinstance(user, str) or not user:
            continue
        stats = users.setdefault(user, {"runs": 0, "agents": set(), "prs": set()})
        if event == "route":
            stats["runs"] += 1
        elif event == "agent":
            stats["agents"].add(entry.get("agent"))
        elif event == "pr":
            stats["prs"].add(entry.get("pr"))
    return users


def format_lines(users):
    """One `• <@U…>: n runs · n agents · n PRs` line per user, busiest first."""
    def plural(n, one, many):
        return f"{n} {one if n == 1 else many}"

    def activity(stats):
        return stats["runs"] + len(stats["agents"]) + len(stats["prs"])

    lines = []
    for user, stats in sorted(users.items(), key=lambda kv: (-activity(kv[1]), kv[0])):
        parts = [plural(stats["runs"], "run", "runs"),
                 plural(len(stats["agents"]), "agent", "agents"),
                 plural(len(stats["prs"]), "PR", "PRs")]
        lines.append(f"• <@{user}>: {' · '.join(parts)}")
    return lines


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_LEDGER
    if len(argv) > 2:
        try:
            day = date.fromisoformat(argv[2])
        except ValueError:
            print("usage: slack_usage.py [ledger-path] [YYYY-MM-DD]", file=sys.stderr)
            return 2
    else:
        day = date.today()
    try:
        entries = load_entries(path, warn=lambda msg: print(msg, file=sys.stderr))
    except (OSError, UnicodeDecodeError) as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        print(f"slack_usage.py: cannot read {path}: {detail}", file=sys.stderr)
        return 1
    for line in format_lines(aggregate(entries, day)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
