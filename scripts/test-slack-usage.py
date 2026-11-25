#!/usr/bin/env python3
"""Offline tests for scripts/slack_usage.py: validation, aggregation, formatting, and CLI behavior."""
import json
import os
import subprocess
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slack_usage as su  # noqa: E402

failures = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def entry(at, event, user="U1", **extra):
    return {"at": at, "event": event, "user": user, "ws": "other", **extra}


def write_ledger(tmp, entries):
    path = os.path.join(tmp, "ledger.jsonl")
    with open(path, "w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


DAY = date(2026, 11, 25)
NOON = "2026-11-25T12:00:00Z"

entries = [
    entry(NOON, "route"),
    entry(NOON, "agent", agent="s1"),
    entry(NOON, "agent", agent="s1"),
    entry(NOON, "agent", agent="s2"),
    entry(NOON, "pr", agent="s1", pr="https://github.com/o/r/pull/1"),
    entry(NOON, "pr", agent="s2", pr="https://github.com/o/r/pull/1"),
]
users = su.aggregate(entries, DAY)
check("runs, agents and PRs are counted per user",
      users["U1"] == {"runs": 1, "agents": {"s1", "s2"}, "prs": {"https://github.com/o/r/pull/1"}})
check("a repeated agent session counts once", len(users["U1"]["agents"]) == 2)
check("a repeated PR URL counts once", len(users["U1"]["prs"]) == 1)

# Less active user inserted first: output must still be busiest first.
two = [
    entry(NOON, "route", user="U2"), entry(NOON, "route", user="U2"),
    entry(NOON, "agent", user="U2", agent="s3"),
] + entries
check("several users are busiest first",
      su.format_lines(su.aggregate(two, DAY)) == [
          "• <@U1>: 1 run · 2 agents · 1 PR",
          "• <@U2>: 2 runs · 1 agent · 0 PRs",
      ])
# Equal activity, inserted reverse alphabetical: output must be alphabetical.
tie = [entry(NOON, "route", user="U9"), entry(NOON, "route", user="U2")]
check("ties are alphabetical",
      su.format_lines(su.aggregate(tie, DAY)) == [
          "• <@U2>: 1 run · 0 agents · 0 PRs",
          "• <@U9>: 1 run · 0 agents · 0 PRs",
      ])
check("singular forms", su.format_lines(su.aggregate(entries, DAY)) ==
      ["• <@U1>: 1 run · 2 agents · 1 PR"])

check("entries from other days are left out",
      su.aggregate([entry("2026-11-24T12:00:00Z", "route"),
                    entry("2026-11-26T12:00:00Z", "route")], DAY) == {})
check("events other than route/agent/pr are ignored",
      su.aggregate([entry(NOON, "claim")], DAY) == {})
check("entries without a user are skipped",
      su.aggregate([entry(NOON, "route", user=None), entry(NOON, "route", user="")], DAY) == {})
check("entries without a parseable timestamp are skipped",
      su.aggregate([entry("not-a-date", "route"), entry(None, "route")], DAY) == {})

check("a list-valued agent id is malformed", su.malformed_reason(
    entry(NOON, "agent", agent=["s1"])) is not None)
check("an agent event without an agent id is malformed", su.malformed_reason(
    entry(NOON, "agent")) == "agent event with no agent")
check("a pr event without a pr URL is malformed", su.malformed_reason(
    entry(NOON, "pr")) == "pr event with no pr")
check("a non-Slack user id is malformed", su.malformed_reason(
    entry(NOON, "route", user="not a user")) is not None)
check("a trailing newline does not sneak past validation", su.malformed_reason(
    entry(NOON, "route", user="U1\n")) is not None)
check("unknown events are not malformed", su.malformed_reason(entry(NOON, "claim")) is None)
check("a valid route entry is not malformed", su.malformed_reason(entry(NOON, "route")) is None)

warnings = []
with tempfile.TemporaryDirectory() as tmp:
    path = write_ledger(tmp, entries)
    check("load_entries reads a real ledger", len(su.load_entries(path)) == 6)
    with open(path, "a") as fh:
        fh.write("\nnot json\n[1,2]\n" + json.dumps(entry(NOON, "agent", agent=["s1"])) + "\n")
    got = su.load_entries(path, warn=warnings.append)
    check("blank and malformed lines are skipped", len(got) == 6)
    check("warnings name the path and line", any("ledger.jsonl:8" in w for w in warnings)
          and any("ledger.jsonl:10" in w for w in warnings))
    check("a missing ledger reads as empty", su.load_entries(os.path.join(tmp, "nope")) == [])

    utf8 = os.path.join(tmp, "utf8.jsonl")
    with open(utf8, "w", encoding="utf-8") as fh:
        fh.write('{"at":"%s","event":"route","user":"U1","user_name":"Nazar Üsik"}\n' % NOON)
    check("a UTF-8 ledger with non-ASCII names reads fine", len(su.load_entries(utf8)) == 1)

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slack_usage.py")

    def run(*args):
        return subprocess.run([sys.executable, script, *args], capture_output=True, text=True)

    r = run(path, "2026-11-25")
    check("CLI prints one line per user", r.returncode == 0
          and r.stdout == "• <@U1>: 1 run · 2 agents · 1 PR\n")
    r = run(os.path.join(tmp, "nope"))
    check("a missing ledger exits 0 with no output", r.returncode == 0 and r.stdout == "")
    r = run(tmp)
    check("an unreadable ledger fails with the path on stderr",
          r.returncode == 1 and tmp in r.stderr and r.stdout == "")
    claims = write_ledger(tmp, [entry(NOON, "claim")])
    r = run(claims, "2026-11-25")
    check("a ledger with only unknown events prints nothing", r.returncode == 0 and r.stdout == "")
    r = run(path, "2026-11-26")
    check("a day with no events prints nothing", r.returncode == 0 and r.stdout == "")
    today = date.today().isoformat()
    write_ledger(tmp, [entry(f"{today}T12:00:00", "route")])
    r = run(path)
    check("the default day is today", r.returncode == 0 and "<@U1>: 1 run" in r.stdout)
    r = run(path, "25.11.2026")
    check("a bad date fails with usage on stderr", r.returncode == 2 and "usage:" in r.stderr)

sys.exit(1 if failures else 0)
