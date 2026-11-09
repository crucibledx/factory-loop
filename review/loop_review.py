#!/usr/bin/env python3
"""Crucible loop review helper: collect PR state, post one consolidated review, follow up threads, gate merges.

Subcommands (all read GH_TOKEN, REPO=owner/name, PR=number from the environment):
  collect  write .loop-review/context.json, diff.patch and prompt.md; print the mode (full|followup|gate)
  post     read .loop-review/result.json, reply to/resolve earlier threads, post the review
  gate     exit 1 while unresolved reviewer threads with a blocking severity remain
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
OUT = os.environ.get("LOOP_REVIEW_DIR", ".loop-review")
REVIEW_MARK = re.compile(r"<!-- crucible-review sha=([0-9a-f]{7,40})(?: first_size=(\d+))? -->")
FINDING_MARK = re.compile(r"<!-- crucible-finding sev=(P[0-2]) -->")
SEVERITIES = ("P0", "P1", "P2")


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        sys.exit(f"missing environment variable {name}")
    return value


def request(method, path, body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {env('GH_TOKEN')}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path} -> {err.code}: {err.read().decode()[:500]}") from err


def graphql(query, **variables):
    result = request("POST", "/graphql", {"query": query, "variables": variables})
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"])[:500])
    return result["data"]


THREADS_QUERY = """
query($owner: String!, $name: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes { databaseId body author { login } }
          }
        }
      }
    }
  }
}"""

THREAD_COMMENTS_QUERY = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { databaseId body author { login } }
      }
    }
  }
}"""


def thread_comments(node):
    comments = list(node["comments"]["nodes"])
    page = node["comments"].get("pageInfo") or {}
    while page.get("hasNextPage"):
        more = graphql(THREAD_COMMENTS_QUERY, id=node["id"], after=page["endCursor"])["node"]["comments"]
        comments += more["nodes"]
        page = more["pageInfo"]
    return comments


def reviewer_login():
    return os.environ.get("LOOP_REVIEWER_LOGIN", "github-actions")


def is_reviewer(login):
    return (login or "").replace("[bot]", "") == reviewer_login()


def threads():
    owner, name = env("REPO").split("/")
    out, after = [], None
    while True:
        data = graphql(THREADS_QUERY, owner=owner, name=name, pr=int(env("PR")), after=after)
        page = data["repository"]["pullRequest"]["reviewThreads"]
        for node in page["nodes"]:
            first = (node["comments"]["nodes"] or [None])[0]
            if not first:
                continue
            mark = FINDING_MARK.search(first["body"] or "")
            if not (is_reviewer((first.get("author") or {}).get("login")) and mark):
                continue
            comments = thread_comments(node)
            out.append({
                "id": node["id"],
                "comment_id": first["databaseId"],
                "severity": mark.group(1),
                "resolved": node["isResolved"],
                "outdated": node["isOutdated"],
                "path": node["path"],
                "line": node["line"],
                "finding": FINDING_MARK.sub("", first["body"]).strip()[:1500],
                "replies": [
                    {"author": (c.get("author") or {}).get("login"), "body": (c["body"] or "")[:800]}
                    for c in comments[1:]
                ],
            })
        if not page["pageInfo"]["hasNextPage"]:
            return out
        after = page["pageInfo"]["endCursor"]


def last_review_marker():
    marker = None
    page = 1
    while True:
        reviews = request("GET", f"/repos/{env('REPO')}/pulls/{env('PR')}/reviews?per_page=100&page={page}")
        for review in reviews:
            if is_reviewer((review.get("user") or {}).get("login")):
                found = REVIEW_MARK.search(review.get("body") or "")
                if found:
                    marker = {"sha": found.group(1), "first_size": int(found.group(2) or 0)}
        if len(reviews) < 100:
            return marker
        page += 1


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def checked_out_head():
    out = git("rev-parse", "HEAD")
    if out.returncode != 0:
        sys.exit(f"cannot read the checked-out commit: {out.stderr.strip()}")
    return out.stdout.strip()


def ensure_commit(sha):
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        fetched = git("fetch", "--quiet", "origin", sha)
        if fetched.returncode != 0:
            sys.exit(f"cannot fetch {sha}: {fetched.stderr.strip()}")


def collect():
    os.makedirs(OUT, exist_ok=True)
    pr = request("GET", f"/repos/{env('REPO')}/pulls/{env('PR')}")
    # Review exactly what is checked out; a newer push gets its own run.
    head, base = checked_out_head(), pr["base"]["sha"]
    ensure_commit(base)
    size = pr["additions"] + pr["deletions"]
    marker = last_review_marker()
    event = os.environ.get("EVENT_NAME", "pull_request")
    if event != "pull_request" or (marker and head.startswith(marker["sha"])):
        mode = "gate"
    elif marker and git("merge-base", "--is-ancestor", marker["sha"], head).returncode == 0:
        mode = "followup"
    else:
        mode = "full"
    since = marker["sha"] if mode == "followup" else base
    diff = git("diff", "--unified=5", f"{since}...{head}" if mode == "full" else f"{since}..{head}")
    if diff.returncode != 0:
        sys.exit(f"git diff {since} {head} failed: {diff.stderr.strip()}")
    with open(f"{OUT}/diff.patch", "w", encoding="utf-8") as fh:
        fh.write(diff.stdout)
    first_size = marker["first_size"] if marker and marker["first_size"] else size
    context = {
        "mode": mode,
        "repo": env("REPO"),
        "pr": int(env("PR")),
        "title": pr["title"],
        "body": (pr.get("body") or "")[:6000],
        "head": head,
        "base": base,
        "since": since,
        "size": size,
        "first_size": first_size,
        "open_threads": [t for t in threads() if not t["resolved"]] if mode != "gate" else [],
    }
    with open(f"{OUT}/context.json", "w", encoding="utf-8") as fh:
        json.dump(context, fh, indent=2)
    template_path = os.environ.get("LOOP_REVIEW_PROMPT", os.path.join(os.path.dirname(__file__), "prompt.md"))
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()
    prompt = template.replace("{{MODE}}", mode).replace("{{CONTEXT_PATH}}", f"{OUT}/context.json")
    prompt = prompt.replace("{{DIFF_PATH}}", f"{OUT}/diff.patch").replace("{{RESULT_PATH}}", f"{OUT}/result.json")
    prompt = prompt.replace("{{STANDARDS_PATH}}", os.environ.get("LOOP_STANDARDS", ""))
    with open(f"{OUT}/prompt.md", "w", encoding="utf-8") as fh:
        fh.write(prompt)
    print(mode)


def finding_body(finding):
    sev = finding.get("severity", "P2")
    if sev not in SEVERITIES:
        sev = "P2"
    title = finding.get("title", "").strip()
    text = finding.get("body", "").strip()
    return f"**{sev}** {title}\n\n{text}\n\n<!-- crucible-finding sev={sev} -->"


def reply(comment_id, body):
    request("POST", f"/repos/{env('REPO')}/pulls/{env('PR')}/comments/{comment_id}/replies", {"body": body})


def resolve(thread_id):
    graphql("mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { id } } }", id=thread_id)


def post():
    with open(f"{OUT}/context.json", encoding="utf-8") as fh:
        context = json.load(fh)
    try:
        with open(f"{OUT}/result.json", encoding="utf-8") as fh:
            result = json.load(fh)
    except (OSError, json.JSONDecodeError) as err:
        sys.exit(f"reviewer produced no valid result.json: {err}")
    head = context["head"]
    by_id = {t["id"]: t for t in context["open_threads"]}
    followed = {"fixed": 0, "not_fixed": 0, "accepted": 0}
    unresolved = []
    for verdict in result.get("threads", []):
        thread = by_id.get(verdict.get("id"))
        if not thread:
            continue
        kind = verdict.get("verdict")
        note = (verdict.get("note") or "").strip()
        if kind in ("fixed", "obsolete"):
            reply(thread["comment_id"], f"Fixed in {head[:7]}." + (f" {note}" if note else ""))
            try_resolve(thread, unresolved)
            followed["fixed"] += 1
        elif kind == "accepted":
            reply(thread["comment_id"], f"Reason accepted, resolving. {note}".strip())
            try_resolve(thread, unresolved)
            followed["accepted"] += 1
        elif kind == "not_fixed":
            reply(thread["comment_id"], f"Not fixed in {head[:7]}: {note or 'the issue is still present.'}")
            followed["not_fixed"] += 1

    findings = [f for f in result.get("findings", []) if f.get("path") and f.get("line")]
    counts = {s: sum(1 for f in findings if f.get("severity") == s) for s in SEVERITIES}
    lines = [f"### Crucible review ({context['mode']}, {head[:7]})", "", result.get("summary", "").strip(), ""]
    lines.append("New findings: " + ", ".join(f"{s} {counts[s]}" for s in SEVERITIES))
    if context["mode"] == "followup":
        lines.append(
            f"Earlier threads: {followed['fixed']} fixed, {followed['accepted']} accepted, "
            f"{followed['not_fixed']} not fixed"
        )
    if context["first_size"] and context["size"] > 1.5 * context["first_size"]:
        lines.append(
            f"\n**Scope warning:** the PR grew from {context['first_size']} to {context['size']} changed lines "
            "since the first review. Ask Nazar before growing it further."
        )
    nits = [n for n in result.get("nits", []) if n]
    if nits:
        lines += ["", "<details><summary>Non-blocking nits</summary>", ""] + [f"- {n}" for n in nits] + ["", "</details>"]
    comments = [
        {"path": f["path"], "line": int(f["line"]), "side": "RIGHT", "body": finding_body(f)}
        for f in findings
    ]
    marker = f"\n<!-- crucible-review sha={head} first_size={context['first_size']} -->"
    payload = {"commit_id": head, "event": "COMMENT", "body": "\n".join(lines) + marker, "comments": comments}
    try:
        request("POST", f"/repos/{env('REPO')}/pulls/{env('PR')}/reviews", payload)
    except RuntimeError as err:
        if "422" not in str(err):
            raise
        post_fallback(head, "\n".join(lines), marker, comments)
    print(json.dumps({"findings": counts, "followed": followed}))
    if unresolved:
        sys.exit(f"could not resolve {len(unresolved)} thread(s) judged fixed; the token needs contents: write. "
                 + "; ".join(unresolved))


def try_resolve(thread, unresolved):
    try:
        resolve(thread["id"])
    except RuntimeError as err:
        unresolved.append(f"{thread['path']}:{thread['line']} ({str(err)[:120]})")


def post_comment(comment, head):
    """Post one finding as a thread: on its line, else on its file. Returns False if neither is accepted."""
    url = f"/repos/{env('REPO')}/pulls/{env('PR')}/comments"
    try:
        request("POST", url, {**comment, "commit_id": head})
        return True
    except RuntimeError:
        pass
    location = f"`{comment['path']}:{comment['line']}`\n\n"
    try:
        request("POST", url, {"path": comment["path"], "subject_type": "file", "commit_id": head,
                              "body": location + comment["body"]})
        return True
    except RuntimeError:
        return False


def post_fallback(head, body, marker, comments):
    """Inline review was rejected (a line outside the diff). Thread what fits; blocking leftovers fail the run."""
    blocking = blocking_severities()
    rest = [c for c in comments if not post_comment(c, head)]
    if rest:
        body += "\n\n#### Findings that could not be posted as threads\n" + "\n".join(
            f"- `{c['path']}:{c['line']}` {FINDING_MARK.sub('', c['body']).strip()}" for c in rest
        )
    unthreaded = [c for c in rest if FINDING_MARK.search(c["body"]).group(1) in blocking]
    # Without a thread the gate cannot track a blocking finding, so this head stays unreviewed (no marker).
    request("POST", f"/repos/{env('REPO')}/pulls/{env('PR')}/reviews",
            {"commit_id": head, "event": "COMMENT", "body": body + ("" if unthreaded else marker)})
    if unthreaded:
        sys.exit(f"{len(unthreaded)} blocking finding(s) could not be posted as review threads; see the review body")


def blocking_severities():
    return [s.strip() for s in os.environ.get("BLOCKING_SEVERITIES", "P0,P1").split(",") if s.strip()]


def gate():
    blocking = blocking_severities()
    head = checked_out_head()
    marker = last_review_marker()
    if not (marker and head.startswith(marker["sha"])):
        report(f"No completed review for {head[:7]} yet. The review run for this commit sets this check.")
        sys.exit(1)
    open_blocking = [t for t in threads() if not t["resolved"] and t["severity"] in blocking]
    lines = [f"Unresolved blocking review threads ({'/'.join(blocking)}): {len(open_blocking)}"]
    lines += [f"- {t['severity']} `{t['path']}:{t['line']}` {t['finding'].splitlines()[0][:120]}" for t in open_blocking]
    report("\n".join(lines))
    sys.exit(1 if open_blocking else 0)


def report(text):
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    commands = {"collect": collect, "post": post, "gate": gate}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
