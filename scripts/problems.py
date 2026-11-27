#!/usr/bin/env python3
"""The day's problem reports for the end-of-day summary.

Reads the workstream problem reports (`problems.jsonl`, one JSON object per line; the format is in hq
`docs/workstream.md`, "Problem reports") and prints one Slack line per kind with that day's problems, fixed and
unfixed. A problem is (ws, kind, name); its latest line up to the end of the day is its state, so a problem reported
earlier and fixed today shows as fixed. Every line is untrusted data: a line that does not match the format is skipped
with a warning on stderr that names only the line number, and text is escaped for Slack. A line nested more than 32
levels deep is skipped too, on every Python version. A missing or empty file prints nothing and exits 0, so the
summary leaves the section out; a file that cannot be read exits 1.

Usage: problems.py [path] [YYYY-MM-DD]
Defaults: ~/crucible-agents/.workstream/problems.jsonl, today in local time.
"""
import json
import os
import re
import sys
from datetime import date, datetime

DEFAULT_PATH = os.path.expanduser("~/crucible-agents/.workstream/problems.jsonl")
WORKSTREAMS = ("root", "forge", "ember", "other")
KINDS = ("tool", "skill", "script", "automation", "ci", "relay", "env", "other")
# The same limits as hq scripts/workstream/report-problem.sh, which writes the file.
LIMITS = {"name": 100, "summary": 500, "fix": 500}
AT = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
AGENT = re.compile(r"[A-Za-z0-9-]{1,64}")
LINK = re.compile(r"https://\S{1,492}")
# Lone surrogates too: json.loads accepts an escaped one, and printing it fails.
UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff]")
# SECRET_RE of report-problem.sh: the format allows no credentials in any field, and the summary would post them.
SECRET = re.compile(
    r"\b(gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|xox[abeprs]-[a-z0-9-]{10,}|sk-[a-z0-9_-]{20,}|akia[0-9a-z]{16})"
    r"|-----begin [a-z ]*private key|\bbearer [a-z0-9._~+/=-]{16,}|hooks\.slack\.com/services/"
    r"|(secret|token|password|passwd|api[_-]?key)[\"']?\s*[=:]\s*[\"']?(?=[^\s\"']*[0-9])[^\s\"']{16,}",
    re.IGNORECASE)
SLACK_SAFE_LINK = re.compile(r"[^<>|]+")
# Reports are flat objects. Deeper lines are skipped before parsing, so the result does not depend on the Python
# version: json raises RecursionError on deep input in 3.9 but parses it in 3.12.
MAX_DEPTH = 32


def too_deep(text):
    """Whether JSON text nests arrays and objects deeper than MAX_DEPTH, ignoring brackets inside strings."""
    depth, in_string, escaped = 0, False, False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                return True
        elif ch in "]}":
            depth = max(depth - 1, 0)
    return False


def parse_int(digits):
    """int() with the 4300-digit limit of Python 3.11+ on every version; 3.9 has none and is slow on long numbers.

    json passes the sign too; like Python's limit, this counts only the digits.
    """
    if len(digits.lstrip("-")) > 4300:
        raise ValueError("integer too long")
    return int(digits)


def at_time(entry):
    return datetime.fromisoformat(entry["at"].replace("Z", "+00:00"))


def invalid_reason(entry):
    """Why an entry does not match the format, or None. Unknown extra fields are allowed."""
    if not isinstance(entry.get("at"), str) or not AT.fullmatch(entry["at"]):
        return "bad at"
    try:
        at_time(entry)
    except ValueError:
        return "bad at"
    if entry.get("ws") not in WORKSTREAMS:
        return "bad ws"
    if entry.get("kind") not in KINDS:
        return "bad kind"
    if not isinstance(entry.get("agent"), str) or not AGENT.fullmatch(entry["agent"]):
        return "bad agent"
    for field, limit in LIMITS.items():
        value = entry.get(field)
        if not isinstance(value, str) or not value or len(value) > limit or UNSAFE.search(value):
            return f"bad {field}"
    if not isinstance(entry.get("fixed"), bool):
        return "bad fixed"
    link = entry.get("link")
    if link is not None and not (isinstance(link, str) and LINK.fullmatch(link) and not UNSAFE.search(link)):
        return "bad link"
    for field in ("agent", "name", "summary", "fix", "link"):
        if isinstance(entry.get(field), str) and SECRET.search(entry[field]):
            return f"credential-like {field}"
    return None


def load_entries(path, warn=None):
    """Valid entries in file order. A missing file reads as empty; other read failures raise."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        return []
    entries = []
    # Split on newlines only and decode line by line: a write cut short can split a UTF-8 character, and JSON strings
    # may hold U+0085 or U+2028 raw; neither may cost the file's other lines.
    for lineno, raw in enumerate(data.split(b"\n"), 1):
        if not raw.strip():
            continue
        try:
            text = raw.decode("utf-8")
        except ValueError:
            text = ""
        if too_deep(text):
            reason = "nested too deep"
        else:
            try:
                entry = json.loads(text, parse_int=parse_int)
            except ValueError:
                entry = None
            reason = "not a JSON object" if not isinstance(entry, dict) else invalid_reason(entry)
        if reason:
            if warn:
                warn(f"{path}:{lineno}: {reason}, line skipped")
            continue
        entries.append(entry)
    return entries


def day_problems(entries, day):
    """The problems with a line on day, each as its latest line up to the end of day."""
    latest, seen_today = {}, set()
    for entry in entries:
        when = at_time(entry).astimezone().date()
        if when > day:
            continue
        key = (entry["ws"], entry["kind"], entry["name"])
        if key not in latest or at_time(entry) >= at_time(latest[key]):
            latest[key] = entry
        if when == day:
            seen_today.add(key)
    return [latest[key] for key in seen_today]


def slack_text(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_lines(problems):
    """`• *<kind>* (n): <name> (<ws>, open|fixed), …` per kind in format order; open problems first."""
    lines = []
    for kind in KINDS:
        group = sorted((p for p in problems if p["kind"] == kind), key=lambda p: (p["fixed"], p["name"], p["ws"]))
        if not group:
            continue
        items = []
        for p in group:
            name = slack_text(p["name"])
            # A link that would break Slack's <url|text> markup is left out; the name still shows.
            if p.get("link") and SLACK_SAFE_LINK.fullmatch(p["link"]):
                name = f"<{p['link']}|{name.replace('|', '¦')}>"
            items.append(f"{name} ({p['ws']}, {'fixed' if p['fixed'] else 'open'})")
        lines.append(f"• *{kind}* ({len(group)}): " + ", ".join(items))
    return lines


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_PATH
    if len(argv) > 2:
        try:
            day = date.fromisoformat(argv[2])
        except ValueError:
            print("usage: problems.py [path] [YYYY-MM-DD]", file=sys.stderr)
            return 2
    else:
        day = date.today()
    try:
        entries = load_entries(path, warn=lambda msg: print(msg, file=sys.stderr))
    except OSError as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        print(f"problems.py: cannot read {path}: {detail}", file=sys.stderr)
        return 1
    for line in format_lines(day_problems(entries, day)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
