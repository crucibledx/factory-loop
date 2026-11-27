#!/usr/bin/env python3
"""Offline tests for scripts/problems.py: validation, the day's state per problem, Slack formatting, and the CLI."""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone

# Days are local dates; pin the zone so the expected days hold on any host.
os.environ["TZ"] = "UTC"
if hasattr(time, "tzset"):
    time.tzset()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import problems as pr  # noqa: E402

failures = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def problem(at="2026-11-26T12:00:00Z", ws="other", kind="tool", name="timeout", fixed=True, link=None, **extra):
    return {"at": at, "ws": ws, "agent": "ec907cc6", "kind": kind, "name": name, "summary": "s", "fixed": fixed,
            "fix": "f", "link": link, **extra}


DAY = date(2026, 11, 26)
# The example line from hq docs/workstream.md.
DOC = json.loads('{"at":"2026-11-26T14:04:34Z","ws":"other","agent":"ec907cc6-410a-4436-a21c-7be1ed34b972",'
                 '"kind":"tool","name":"timeout","summary":"timeout is not installed on the Mac, so the checks '
                 'watcher failed","fixed":true,"fix":"ran gh pr checks --watch without it",'
                 '"link":"https://github.com/crucibledx/assets/pull/14"}')
check("the documented example line is valid", pr.invalid_reason(DOC) is None)
check("unknown extra fields are allowed", pr.invalid_reason(problem(extra_field=1)) is None)
for field, value in [("at", "2026-11-26 12:00"), ("at", "2026-13-40T12:00:00Z"), ("ws", "web"), ("kind", "infra"),
                     ("name", ""), ("name", "x" * 101), ("name", "a\nb"), ("summary", "a\u2028b"), ("summary", 5),
                     ("fix", "x" * 501), ("fix", "a\x85b"), ("agent", None), ("agent", "a b"), ("agent", "a" * 65),
                     ("fixed", "true"), ("link", "http://x"), ("link", "https://x y"),
                     ("link", "https://" + "x" * 493), ("link", "https://x\x1b[2J"), ("link", "https://x\x00"),
                     ("link", "https://x\x85")]:
    check(f"invalid {field}={value!r:.20} is rejected", pr.invalid_reason({**problem(), field: value}) is not None)
missing = problem()
del missing["fix"]
check("a missing required field is rejected", pr.invalid_reason(missing) == "bad fix")
nolink = problem()
del nolink["link"]
check("a missing link reads as none", pr.invalid_reason(nolink) is None)
TOKEN = "gh" + "p_" + "a" * 36  # built at runtime so no token-shaped literal is committed
for field, value in [("name", TOKEN), ("summary", "Bearer " + "x" * 20), ("fix", "api_key=abc123def456ghi789"),
                     ("link", "https://hooks.slack" + ".com/services/T0/B0/x"), ("agent", "xox" + "b-1234567890-ab")]:
    check(f"a credential-like {field} is rejected", pr.invalid_reason({**problem(), field: value}) == f"credential-like {field}")
check("text that only mentions a token is valid", pr.invalid_reason(problem(summary="token: expired, re-ran gh auth")) is None)
for field, value in [("name", "a\ud800b"), ("link", "https://x\udc00")]:
    check(f"a lone surrogate in {field} is rejected", pr.invalid_reason({**problem(), field: value}) == f"bad {field}")
check("a whitespace-only text field is valid, as the writer allows it", pr.invalid_reason(problem(fix=" ")) is None)

entries = [
    problem(at="2026-11-25T09:00:00Z", kind="ci", name="review", fixed=False),
    problem(at="2026-11-26T10:00:00Z", kind="ci", name="review", fixed=True),  # earlier problem fixed today
    problem(at="2026-11-25T09:00:00Z", kind="env", name="disk", fixed=False),  # not touched today: left out
    problem(at="2026-11-26T09:00:00Z", name="bunx", ws="forge", fixed=False),
    problem(at="2026-11-26T11:00:00Z", name="bunx", ws="forge", fixed=False),
    problem(at="2026-11-26T12:00:00Z", name="timeout", link="https://github.com/o/r/pull/1"),
    problem(at="2026-11-27T12:00:00Z", name="timeout", fixed=False, link="https://github.com/o/r/pull/1"),  # tomorrow
    problem(at="2026-11-26T13:00:00Z", kind="skill", name="<!channel> a&b|c"),
]
lines = pr.format_lines(pr.day_problems(entries, DAY))
check("one line per kind in format order, open first, latest state up to the end of the day", lines == [
    "• *tool* (2): bunx (forge, open), <https://github.com/o/r/pull/1|timeout> (other, fixed)",
    "• *skill* (1): &lt;!channel&gt; a&amp;b|c (other, fixed)",
    "• *ci* (1): review (other, fixed)",
])
check("a problem fixed today that was reported earlier shows as fixed", "review (other, fixed)" in lines[2])
check("the same name in another workstream is another problem",
      len(pr.day_problems([problem(ws="forge"), problem(ws="ember")], DAY)) == 2)
check("a later line on the same day wins, also for equal times (file order)",
      pr.day_problems([problem(fixed=False), problem(fixed=True)], DAY)[0]["fixed"] is True)
check("a link text cannot close the Slack link", pr.format_lines([problem(name="a|b", link="https://x")])
      == ["• *tool* (1): <https://x|a¦b> (other, fixed)"])
check("a valid link that would break Slack markup is left out, the name stays",
      pr.invalid_reason(problem(link="https://x>y|z")) is None
      and pr.format_lines([problem(link="https://x>y|z")]) == ["• *tool* (1): timeout (other, fixed)"])
check("a 500-character link is valid", pr.invalid_reason(problem(link="https://" + "x" * 492)) is None)
check("no problems prints nothing", pr.format_lines(pr.day_problems(entries, date(2026, 11, 20))) == [])

script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "problems.py")


def run(*args):
    return subprocess.run([sys.executable, script, *args], capture_output=True, text=True,
                          env={**os.environ, "TZ": "UTC"})


with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "problems.jsonl")
    secret_line = '{"at":"2026-11-26T12:00:00Z","ws":"other","name":"ghp_SECRETVALUE"}'
    # A future field may hold U+0085 or U+2028 raw; the line must still parse as one line.
    extra = json.dumps({**DOC, "note": "a\x85b\u2028c"}, ensure_ascii=False)
    with open(path, "wb") as fh:
        fh.write((json.dumps(DOC) + "\n\nnot json\n[1]\n" + secret_line + "\n").encode()
                 + b'{"at":"2026-11-26T12:00:00Z","name":"caf\xc3\n'  # cut short inside a UTF-8 character
                 + extra.encode() + b"\n" + b'{"at":"2026-11-26T1')
    warnings = []
    got = pr.load_entries(path, warn=warnings.append)
    check("blank, non-JSON, non-object, invalid and cut-short lines are skipped, the rest are read",
          [e.get("note") for e in got] == [None, "a\x85b\u2028c"])
    check("warnings name the line, never its content",
          [w.split(": ", 1)[0].rsplit(":", 1)[1] for w in warnings] == ["3", "4", "5", "6", "8"]
          and not any("SECRET" in w for w in warnings))
    r = run(path, "2026-11-26")
    check("a cut-short UTF-8 line does not make the file unreadable", r.returncode == 0)
    check("CLI prints the day's lines", r.returncode == 0 and r.stdout ==
          "• *tool* (1): <https://github.com/crucibledx/assets/pull/14|timeout> (other, fixed)\n"
          and "SECRET" not in r.stderr)
    hostile = os.path.join(tmp, "hostile.jsonl")
    valid = json.dumps(problem(name="first")) + "\n"
    with open(hostile, "w", encoding="utf-8") as fh:
        fh.write(valid + "[" * 5000 + "]" * 5000 + "\n"
                 + json.dumps(problem(name="x"))[:-1] + ', "deep": ' + "[" * 5000 + "]" * 5000 + "}\n"
                 + json.dumps(problem(name="x")).replace('"x"', '"a\\ud800"') + "\n"
                 + json.dumps(problem(name="y", link="https://x")).replace('https://x', 'https://x\\udc00') + "\n"
                 + json.dumps(problem(name=TOKEN)) + "\n"
                 + json.dumps(problem(name="last")) + "\n")
    r = run(hostile, "2026-11-26")
    check("deep nesting, lone surrogates and credentials skip only their lines", r.returncode == 0
          and r.stdout == "• *tool* (2): first (other, fixed), last (other, fixed)\n"
          and r.stderr.count("line skipped") == 5 and TOKEN not in r.stderr + r.stdout and "ud800" not in r.stderr)
    r = run(os.path.join(tmp, "nope"))
    check("a missing file exits 0 with no output", r.returncode == 0 and r.stdout == "")
    r = run(tmp)
    check("an unreadable file fails with the path on stderr", r.returncode == 1 and tmp in r.stderr and r.stdout == "")
    r = run(path, "26.11.2026")
    check("a bad date fails with usage on stderr", r.returncode == 2 and "usage:" in r.stderr)
    today = datetime.now(timezone.utc).date().isoformat()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(problem(at=f"{today}T12:00:00Z")) + "\n")
    r = run(path)
    check("the default day is today", r.returncode == 0 and "timeout (other, fixed)" in r.stdout)

sys.exit(1 if failures else 0)
