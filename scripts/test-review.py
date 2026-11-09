#!/usr/bin/env python3
"""Offline tests for review/loop_review.py: thread parsing, follow-up actions, fallbacks, and the gate."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review"))
import loop_review as lr  # noqa: E402

os.environ.update({"GH_TOKEN": "x", "REPO": "o/r", "PR": "7"})
calls = []
HEAD = "abcdef1234567"


def thread(tid, sev, resolved=False, author="github-actions", more=False):
    body = f"**{sev}** t\n\nb\n\n<!-- crucible-finding sev={sev} -->" if sev else "plain comment"
    return {"id": tid, "isResolved": resolved, "isOutdated": False, "path": "a.ts", "line": 3,
            "comments": {"pageInfo": {"hasNextPage": more, "endCursor": "c1" if more else None},
                         "nodes": [{"databaseId": int(tid[1:]), "body": body, "author": {"login": author}}]}}


NODES = [thread("T1", "P1", more=True), thread("T2", "P2"), thread("T3", "P0", resolved=True),
         thread("T4", "P1", author="NazarUsik"), thread("T5", None)]
state = {"reviews": [{"user": {"login": "github-actions[bot]"}, "body": f"<!-- crucible-review sha={HEAD} -->"}],
         "reject_inline": False, "reject_file": False}


def fake_graphql(query, **variables):
    calls.append(("graphql", query.split("(")[0].strip(), variables))
    if "reviewThreads" in query:
        return {"repository": {"pullRequest": {"reviewThreads": {
            "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": NODES}}}}
    if "node(id" in query:
        return {"node": {"comments": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                      "nodes": [{"databaseId": 99, "body": "late reply", "author": {"login": "n"}}]}}}
    return {}


def fake_request(method, path, body=None):
    calls.append((method, path, body))
    if method == "GET" and "/reviews" in path:
        return state["reviews"]
    if state["reject_inline"] and path.endswith("/reviews") and body and body.get("comments"):
        raise RuntimeError("POST reviews -> 422: line not in diff")
    if state["reject_inline"] and path.endswith("/pulls/7/comments"):
        if body.get("subject_type") != "file" or state["reject_file"]:
            raise RuntimeError("POST comments -> 422")
    return {}


lr.graphql, lr.request = fake_graphql, fake_request
lr.checked_out_head = lambda: HEAD
failures = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def exit_code(fn):
    try:
        fn()
        return 0
    except SystemExit as exc:
        return exc.code


found = lr.threads()
check("only reviewer threads with a finding marker are parsed", [t["id"] for t in found] == ["T1", "T2", "T3"])
check("severity is read from the marker", [t["severity"] for t in found] == ["P1", "P2", "P0"])
check("replies past the first page are fetched", [r["body"] for r in found[0]["replies"]] == ["late reply"])

for blocking in ("P0,P1", "P0,P1,P2"):
    os.environ["BLOCKING_SEVERITIES"] = blocking
    check(f"gate fails with unresolved blocking threads ({blocking})", exit_code(lr.gate) == 1)
NODES[0]["isResolved"] = True
os.environ["BLOCKING_SEVERITIES"] = "P0,P1"
check("gate passes once P1 is resolved and only P2 remains", exit_code(lr.gate) == 0)
state["reviews"] = [{"user": {"login": "github-actions[bot]"}, "body": "<!-- crucible-review sha=1111111 -->"}]
check("gate fails when the current head has no completed review", exit_code(lr.gate) == 1)
state["reviews"] = []
check("gate fails when there is no review at all", exit_code(lr.gate) == 1)

with tempfile.TemporaryDirectory() as out:
    lr.OUT = out
    context = {"mode": "followup", "head": HEAD, "size": 400, "first_size": 200,
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
    check("review body carries the sha marker", f"<!-- crucible-review sha={HEAD} first_size=200 -->" in body)
    check("scope warning when the PR grew past 1.5x", "Scope warning" in body)
    check("nits stay in the body", "Non-blocking nits" in body)

    state["reject_inline"] = True
    calls.clear()
    code = exit_code(lr.post)
    files = [c for c in calls if c[1].endswith("/pulls/7/comments") and c[2].get("subject_type") == "file"]
    reviews = [c for c in calls if c[0] == "POST" and c[1].endswith("/reviews")]
    check("422 fallback posts a line outside the diff as a file thread", code == 0 and len(files) == 1)
    check("file-thread fallback keeps the sha marker", "crucible-review sha=" in reviews[-1][2]["body"])

    state["reject_file"] = True
    calls.clear()
    code = exit_code(lr.post)
    reviews = [c for c in calls if c[0] == "POST" and c[1].endswith("/reviews")]
    last = reviews[-1][2]["body"]
    check("an unthreadable blocking finding fails the run", code not in (0, None))
    check("an unthreadable blocking finding leaves the head unreviewed", "crucible-review sha=" not in last
          and "could not be posted as threads" in last)

    result["findings"][0]["severity"] = "P2"
    json.dump(result, open(f"{out}/result.json", "w"))
    code = exit_code(lr.post)
    reviews = [c for c in calls if c[0] == "POST" and c[1].endswith("/reviews")]
    check("an unthreadable P2 finding goes to the body and does not block", code == 0
          and "crucible-review sha=" in reviews[-1][2]["body"])

    os.remove(f"{out}/result.json")
    check("missing result.json fails the job", exit_code(lr.post) not in (0, None))

sys.exit(1 if failures else 0)
