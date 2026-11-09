#!/usr/bin/env python3
"""Offline tests for review/loop_review.py: thread parsing, follow-up actions, 422 fallback, and the gate."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review"))
import loop_review as lr  # noqa: E402

os.environ.update({"GH_TOKEN": "x", "REPO": "o/r", "PR": "7"})
calls = []


def thread(tid, sev, resolved=False, author="github-actions"):
    body = f"**{sev}** t\n\nb\n\n<!-- crucible-finding sev={sev} -->" if sev else "plain comment"
    return {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "a.ts", "line": 3,
            "comments": {"nodes": [{"databaseId": int(tid[1:]), "body": body, "author": {"login": author}}]}}


NODES = [thread("T1", "P1"), thread("T2", "P2"), thread("T3", "P0", resolved=True), thread("T4", "P1", author="NazarUsik"),
         thread("T5", None)]


def fake_graphql(query, **variables):
    calls.append(("graphql", query.split("(")[0].strip(), variables))
    if "reviewThreads" in query:
        return {"repository": {"pullRequest": {"reviewThreads": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": NODES}}}}
    return {}


reject_inline = {"on": False}


def fake_request(method, path, body=None):
    calls.append((method, path, body))
    if reject_inline["on"] and path.endswith("/reviews") and body and body.get("comments"):
        raise RuntimeError("POST reviews -> 422: line not in diff")
    if reject_inline["on"] and path.endswith("/pulls/7/comments"):
        raise RuntimeError("POST comments -> 422")
    return {}


lr.graphql, lr.request = fake_graphql, fake_request
failures = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


found = lr.threads()
check("only reviewer threads with a finding marker are parsed", [t["id"] for t in found] == ["T1", "T2", "T3"])
check("severity is read from the marker", [t["severity"] for t in found] == ["P1", "P2", "P0"])

for blocking, expected in (("P0,P1", 1), ("P0,P1,P2", 1)):
    os.environ["BLOCKING_SEVERITIES"] = blocking
    try:
        lr.gate()
        code = 0
    except SystemExit as exc:
        code = exc.code
    check(f"gate fails with unresolved blocking threads ({blocking})", code == expected)
NODES[0]["isResolved"] = True
os.environ["BLOCKING_SEVERITIES"] = "P0,P1"
try:
    lr.gate()
    code = 0
except SystemExit as exc:
    code = exc.code
check("gate passes once P1 is resolved and only P2 remains", code == 0)

with tempfile.TemporaryDirectory() as out:
    lr.OUT = out
    context = {"mode": "followup", "head": "abcdef1234567", "size": 400, "first_size": 200,
               "open_threads": [dict(t) for t in found]}
    result = {"summary": "s", "nits": ["n"], "findings": [{"severity": "P1", "path": "a.ts", "line": 9, "title": "x", "body": "y"}],
              "threads": [{"id": "T1", "verdict": "fixed"}, {"id": "T2", "verdict": "not_fixed", "note": "still there"},
                          {"id": "T3", "verdict": "accepted", "note": "follow-up #12"}, {"id": "nope", "verdict": "fixed"}]}
    json.dump(context, open(f"{out}/context.json", "w"))
    json.dump(result, open(f"{out}/result.json", "w"))
    calls.clear()
    lr.post()
    replies = [c for c in calls if c[0] == "POST" and c[1].endswith("/replies")]
    resolves = [c for c in calls if c[0] == "graphql" and c[1] == "mutation"]
    reviews = [c for c in calls if c[0] == "POST" and c[1].endswith("/reviews")]
    check("one reply per known thread verdict", len(replies) == 3)
    check("fixed and accepted threads are resolved, not_fixed is not", [c[2]["id"] for c in resolves] == ["T1", "T3"])
    check("one review is posted with inline findings", len(reviews) == 1 and len(reviews[0][2]["comments"]) == 1)
    body = reviews[0][2]["body"]
    check("review body carries the sha marker", "<!-- crucible-review sha=abcdef1234567 first_size=200 -->" in body)
    check("scope warning when the PR grew past 1.5x", "Scope warning" in body)
    check("nits stay in the body", "Non-blocking nits" in body)

    reject_inline["on"] = True
    calls.clear()
    lr.post()
    reviews = [c for c in calls if c[0] == "POST" and c[1].endswith("/reviews")]
    check("422 fallback moves findings into the review body", len(reviews) == 2 and "outside the diff" in reviews[-1][2]["body"])

    os.remove(f"{out}/result.json")
    try:
        lr.post()
        code = 0
    except SystemExit as exc:
        code = exc.code
    check("missing result.json fails the job", code not in (0, None))

sys.exit(1 if failures else 0)
