#!/usr/bin/env python3
"""Crucible loop review helper: collect PR state, post one consolidated review, follow up threads, gate merges.

Subcommands (all read GH_TOKEN, REPO=owner/name, PR=number and HEAD_SHA from the environment):
  collect  write .loop-review/context.json, diff.patch and prompt.md; print the mode (full|followup|gate)
  post     read .loop-review/result.json, reply to/resolve earlier threads, post the review
  gate     exit 1 while unresolved reviewer threads with a blocking severity remain

post and gate run in a job that holds the write token but never checks out the PR's code. They take nothing from the
review job except result.json, which they treat as untrusted: the PR state, the mode and the open threads come from the
API. (factory-loop's own self-review runs the PR's workflow and loop_ref by design, so this holds for other repos.)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
OUT = os.environ.get("LOOP_REVIEW_DIR", ".loop-review")
ORG_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugins", "crucible-loop", "skills",
                              "engineering-standards", "org-rules.md")
REVIEW_MARK = re.compile(r"<!-- crucible-review sha=([0-9a-f]{7,40})(?: first_size=(\d+))? -->")
FINDING_MARK = re.compile(r"<!-- crucible-finding sev=(P[0-2]) -->")
SEVERITIES = ("P0", "P1", "P2")
REVIEW_WAIT_SECONDS = 40 * 60  # below the job timeout
REVIEW_POLL_SECONDS = 20
MAX_RESULT_BYTES = 1_000_000
MAX_FINDINGS = 100
MAX_LINE = 10_000_000
VERDICTS = ("fixed", "obsolete", "accepted", "not_fixed")


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
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path} -> {err.code}: {err.read().decode()[:500]}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise RuntimeError(f"{method} {path} -> {err}") from err


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


def last_match(pattern, text):
    found = list(pattern.finditer(text))
    return found[-1] if found else None


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
            # The marker this code appends comes last; an earlier one would be quoted text.
            mark = last_match(FINDING_MARK, first["body"] or "")
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
                found = last_match(REVIEW_MARK, review.get("body") or "")
                if found:
                    marker = {"sha": found.group(1), "first_size": int(found.group(2) or 0)}
        if len(reviews) < 100:
            return marker
        page += 1


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def head_sha():
    """The commit under review: the event's head, else (local runs) the checked-out commit."""
    if os.environ.get("HEAD_SHA"):
        return os.environ["HEAD_SHA"]
    out = git("rev-parse", "HEAD")
    if out.returncode != 0:
        sys.exit(f"cannot read the checked-out commit: {out.stderr.strip()}")
    return out.stdout.strip()


def is_ancestor(old, new):
    """Whether old is new or one of its ancestors. A commit the API no longer knows (rewritten history) is not."""
    try:
        compare = request("GET", f"/repos/{env('REPO')}/compare/{old}...{new}?per_page=1")
    except RuntimeError as err:
        # stderr: collect's stdout is the mode, written to $GITHUB_OUTPUT.
        print(f"cannot compare {old[:7]}...{new[:7]}, reviewing in full: {err}", file=sys.stderr)
        return False
    return compare.get("status") in ("ahead", "identical")


def ensure_commit(sha):
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        fetched = git("fetch", "--quiet", "origin", sha)
        if fetched.returncode != 0:
            sys.exit(f"cannot fetch {sha}: {fetched.stderr.strip()}")


def render_prompt(mode, run_checks):
    """The reviewer's prompt. Only with run_checks may it run repository code; otherwise it is told not to."""
    template_path = os.environ.get("LOOP_REVIEW_PROMPT", os.path.join(os.path.dirname(__file__), "prompt.md"))
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()
    checks_path = os.path.join(os.path.dirname(template_path), "run-checks.md" if run_checks else "no-checks.md")
    with open(checks_path, encoding="utf-8") as fh:
        checks = fh.read().strip()
    prompt = template.replace("{{MODE}}", mode).replace("{{CONTEXT_PATH}}", f"{OUT}/context.json")
    prompt = prompt.replace("{{DIFF_PATH}}", f"{OUT}/diff.patch").replace("{{RESULT_PATH}}", f"{OUT}/result.json")
    prompt = prompt.replace("{{STANDARDS_PATH}}", os.environ.get("LOOP_STANDARDS", ""))
    prompt = prompt.replace("{{ORG_RULES}}", org_rules())
    if run_checks:
        checks += "\n\n" + resolved_checks()
    return prompt.replace("{{CHECKS}}", checks)


def resolved_checks():
    """The repo's resolved toolchain for the run_checks prompt. Never fails the review."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "toolchain.py")
    try:
        proc = subprocess.run([sys.executable, script, "--describe"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as err:
        return f"The toolchain could not be resolved ({err}); report checks that need it as could not run."
    out = (proc.stdout if proc.returncode == 0 else proc.stderr or proc.stdout).strip()
    if proc.returncode != 0:
        return f"The toolchain could not be resolved: {out}. Report its checks as could not run."
    return "The resolved toolchain (from .factory/toolchain.json or the repo's files):\n" + out


def org_rules():
    """The org rules, inlined: the reviewer cannot read the private hq repo they come from."""
    with open(ORG_RULES_PATH, encoding="utf-8") as fh:
        return fh.read().strip()


def pr_state():
    """The review context, from the API only, so the review job and the post job derive the same one."""
    pr = request("GET", f"/repos/{env('REPO')}/pulls/{env('PR')}")
    # Review exactly the event's head; a newer push gets its own run.
    head, base = head_sha(), pr["base"]["sha"]
    size = pr["additions"] + pr["deletions"]
    marker = last_review_marker()
    event = os.environ.get("EVENT_NAME", "pull_request")
    if event != "pull_request" or (marker and head.startswith(marker["sha"])):
        mode = "gate"
    elif marker and is_ancestor(marker["sha"], head):
        mode = "followup"
    else:
        mode = "full"
    return {
        "mode": mode,
        "repo": env("REPO"),
        "pr": int(env("PR")),
        "title": pr["title"],
        "body": (pr.get("body") or "")[:6000],
        "head": head,
        "base": base,
        "since": marker["sha"] if mode == "followup" else base,
        "size": size,
        "first_size": marker["first_size"] if marker and marker["first_size"] else size,
        "open_threads": [t for t in threads() if not t["resolved"]] if mode != "gate" else [],
    }


def followup_diff(since, head, base):
    """The changes since the last review, without what merging the base branch into the PR brought in.

    Returns (diff result, scope). After such a merge, since..head also holds the base's own commits, so the head is
    compared with the reviewed commit merged with the same base commit. When that merge conflicts, the author's
    resolution cannot be told apart, so the whole PR is the diff.
    """
    # Exit 1 with no output: no common ancestor, so the PR holds none of the base's commits.
    forks = git("merge-base", "--all", base, head)
    if forks.returncode not in (0, 1):
        sys.exit(f"git merge-base {base} {head} failed: {forks.stderr.strip()}")
    forks = forks.stdout.split()
    if all(git("merge-base", "--is-ancestor", fork, since).returncode == 0 for fork in forks):
        return git("diff", "--unified=5", f"{since}..{head}"), "since_review"
    # stderr: collect's stdout is the mode, written to $GITHUB_OUTPUT.
    if len(forks) > 1:
        print(f"the PR and the base have {len(forks)} merge bases, reviewing the whole PR diff", file=sys.stderr)
        return git("diff", "--unified=5", f"{base}...{head}"), "whole_pr"
    merged = git("merge-tree", "--write-tree", since, forks[0])
    if merged.returncode == 0:
        return git("diff", "--unified=5", merged.stdout.split()[0], head), "since_review"
    if merged.returncode == 1:
        print(f"the base merge conflicts with {since[:7]}, reviewing the whole PR diff", file=sys.stderr)
    else:
        print(f"git merge-tree failed (it needs git 2.38 or later), reviewing the whole PR diff: "
              f"{merged.stderr.strip()[:300]}", file=sys.stderr)
    return git("diff", "--unified=5", f"{base}...{head}"), "whole_pr"


def collect():
    os.makedirs(OUT, exist_ok=True)
    context = pr_state()
    head, since = context["head"], context["since"]
    ensure_commit(context["base"])
    ensure_commit(since)
    if context["mode"] == "followup":
        diff, context["diff_scope"] = followup_diff(since, head, context["base"])
    else:
        diff, context["diff_scope"] = git("diff", "--unified=5", f"{since}...{head}"), "whole_pr"
    if diff.returncode != 0:
        sys.exit(f"git diff {since} {head} failed: {diff.stderr.strip()}")
    with open(f"{OUT}/diff.patch", "w", encoding="utf-8") as fh:
        fh.write(diff.stdout)
    with open(f"{OUT}/context.json", "w", encoding="utf-8") as fh:
        json.dump(context, fh, indent=2)
    with open(f"{OUT}/prompt.md", "w", encoding="utf-8") as fh:
        fh.write(render_prompt(context["mode"], os.environ.get("LOOP_RUN_CHECKS") == "true"))
    print(context["mode"])


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


def clip(value, limit):
    """A text field of result.json, without HTML comments: a forged review or finding marker must not reach a body."""
    return value.strip()[:limit].replace("<!--", "&lt;!--") if isinstance(value, str) else ""


def entries(result, key):
    items = result.get(key, [])
    if not isinstance(items, list):
        sys.exit(f"result.json: {key} is not a list")
    return [item for item in items if isinstance(item, dict)]


def finding_line(value):
    if isinstance(value, str) and value.strip().isdecimal() and len(value.strip()) <= 8:
        value = int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_LINE else None


def load_result(path):
    """result.json reduced to the fields post uses, with their types and lengths checked. Exits when it is unusable.

    The file comes from the job that ran the reviewer, and with run_checks the PR's code, so nothing in it is trusted.
    """
    try:
        if os.path.getsize(path) > MAX_RESULT_BYTES:
            sys.exit(f"result.json is larger than {MAX_RESULT_BYTES} bytes")
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, RecursionError) as err:
        sys.exit(f"reviewer produced no valid result.json (was the review artifact downloaded?): {err!r}"[:500])
    if not isinstance(raw, dict):
        sys.exit("result.json is not a JSON object")
    findings, unplaced = [], []
    for item in entries(raw, "findings"):
        path_, line = clip(item.get("path"), 400), finding_line(item.get("line"))
        finding = {"severity": item.get("severity") if item.get("severity") in SEVERITIES else "P2",
                   "path": path_, "line": line, "title": clip(item.get("title"), 200),
                   "body": clip(item.get("body"), 6000)}
        if path_ and line:
            findings.append(finding)
        else:
            # Kept, not dropped: a blocking finding without a location must still keep the head unreviewed.
            finding["where"] = clip(str(item.get("path")), 200) + ":" + clip(str(item.get("line")), 40)
            unplaced.append(finding)
    if len(findings) + len(unplaced) > MAX_FINDINGS:
        sys.exit(f"result.json has {len(findings) + len(unplaced)} findings; more than {MAX_FINDINGS} is not a review")
    verdicts = [{"id": item["id"], "verdict": item.get("verdict"), "note": clip(item.get("note"), 800)}
                for item in entries(raw, "threads")
                if isinstance(item.get("id"), str) and item.get("verdict") in VERDICTS]
    nits = raw.get("nits", [])
    nits = [clip(n, 500) for n in nits[:MAX_FINDINGS] if clip(n, 500)] if isinstance(nits, list) else []
    return {"summary": clip(raw.get("summary"), 4000), "findings": findings, "unplaced": unplaced,
            "threads": verdicts, "nits": nits}


def post():
    context = pr_state()
    head = context["head"]
    if context["mode"] == "gate":
        print(f"{head[:7]} already has a review; nothing to post.")
        return
    result = load_result(f"{OUT}/result.json")
    by_id = {t["id"]: t for t in context["open_threads"]}
    followed = {"fixed": 0, "not_fixed": 0, "accepted": 0}
    unresolved = []
    for verdict in result["threads"]:
        thread = by_id.get(verdict["id"])
        if not thread:
            continue
        kind, note = verdict["verdict"], verdict["note"]
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

    findings, unplaced = result["findings"], result["unplaced"]
    counts = {s: sum(1 for f in findings + unplaced if f["severity"] == s) for s in SEVERITIES}
    lines = [f"### Crucible review ({context['mode']}, {head[:7]})", "", result["summary"], ""]
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
    if unplaced:
        lines += ["", "#### Findings without a usable file and line"]
        lines += [f"- **{f['severity']}** `{f['where']}` {f['title']}: {f['body']}" for f in unplaced]
    nits = result["nits"]
    if nits:
        lines += ["", "<details><summary>Non-blocking nits</summary>", ""] + [f"- {n}" for n in nits] + ["", "</details>"]
    comments = [
        {"path": f["path"], "line": f["line"], "side": "RIGHT", "body": finding_body(f)}
        for f in findings
    ]
    unplaced_blocking = [f for f in unplaced if f["severity"] in blocking_severities()]
    # Without a thread the gate cannot track a blocking finding, so this head stays unreviewed (no marker).
    marker = "" if unplaced_blocking else f"\n<!-- crucible-review sha={head} first_size={context['first_size']} -->"
    payload = {"commit_id": head, "event": "COMMENT", "body": "\n".join(lines) + marker, "comments": comments}
    try:
        request("POST", f"/repos/{env('REPO')}/pulls/{env('PR')}/reviews", payload)
    except RuntimeError as err:
        if "422" not in str(err):
            raise
        post_fallback(head, "\n".join(lines), marker, comments)
    print(json.dumps({"findings": counts, "followed": followed}))
    if unplaced_blocking:
        sys.exit(f"{len(unplaced_blocking)} blocking finding(s) have no usable file and line; see the review body")
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


def reviewed(head):
    marker = last_review_marker()
    return bool(marker and head.startswith(marker["sha"]))


def review_runs(workflow_id, head):
    """The other pull_request runs of this workflow on head, newest first."""
    runs = request("GET", f"/repos/{env('REPO')}/actions/workflows/{workflow_id}/runs"
                          f"?event=pull_request&head_sha={head}&per_page=100")
    own = os.environ.get("GITHUB_RUN_ID")
    others = [r for r in runs.get("workflow_runs", []) if str(r["id"]) != own]
    return sorted(others, key=lambda r: r["id"], reverse=True)


def review_run_active(workflow_id, head):
    """True while another pull_request run of this workflow on head is unfinished."""
    return any(r["status"] != "completed" for r in review_runs(workflow_id, head))


def own_workflow_id():
    return request("GET", f"/repos/{env('REPO')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")["workflow_id"]


def no_review_reason(head):
    """Why head has no completed review, for the gate's failure. Says so when its review run stopped at the usage
    limit, which loop-review-retry re-runs after the reset, so the red gate does not read as a problem with the PR."""
    default = f"No completed review for {head[:7]} yet. The review run for this commit sets this check."
    if not os.environ.get("GITHUB_RUN_ID"):
        return default
    try:
        # Imported here: usage_limit imports this module.
        from usage_limit import MAX_ATTEMPTS, fmt, limit_stop
        latest = next(iter(review_runs(own_workflow_id(), head)), None)
        if not latest or latest["status"] != "completed":
            return default
        job, reset = limit_stop(env("REPO"), latest["id"])
    except (ImportError, RuntimeError, KeyError, TypeError, ValueError) as err:
        print(f"cannot look up why the review run stopped: {err!r}"[:300])
        return default
    where = latest.get("html_url") or f"run {latest['id']}"
    by_hand = "Re-run that run's `review / reviewer` job (or its failed jobs)."
    if job:
        if latest.get("run_attempt", 1) >= MAX_ATTEMPTS:
            return (f"Review stopped at the usage limit after {MAX_ATTEMPTS} attempts, so it is not re-run again "
                    f"({where}). {by_hand} This is not a review verdict.")
        when = f"after {fmt(reset)}" if reset else "after the reset (the reset time was not reported)"
        return (f"Review stopped at the usage limit; it re-runs {when}. {head[:7]} has no review yet, so this check "
                f"stays red until that review sets it ({where}). This is not a review verdict.")
    return (f"No completed review for {head[:7]}: its review run ended as {latest.get('conclusion') or 'unknown'} "
            f"without posting one ({where}). {by_hand}")


def wait_for_review(head):
    """Whether head has a completed review, after waiting for a review run of head that is still going.

    The newest check run sets the required check, so a gate that runs mid-review (a thread reply fires
    pull_request_review) must wait for the review's verdict: failing early leaves a stale red check, and
    passing early would hide a red verdict.
    """
    if reviewed(head):
        return True
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return False
    try:
        workflow_id = own_workflow_id()
        active = review_run_active(workflow_id, head)
    except RuntimeError as err:
        print(f"cannot look up review runs: {err}")
        return reviewed(head)
    if not active:
        return reviewed(head)
    print(f"A review run for {head[:7]} is in progress; waiting for its review.", flush=True)
    deadline = time.monotonic() + REVIEW_WAIT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(REVIEW_POLL_SECONDS)
        try:
            if reviewed(head):
                return True
            if not review_run_active(workflow_id, head):
                return reviewed(head)
        except RuntimeError as err:
            print(f"polling for the review failed, retrying: {err}", flush=True)
    return reviewed(head)


def gate():
    blocking = blocking_severities()
    head = head_sha()
    if not wait_for_review(head):
        # Never pass or skip without a review: a skipped or green gate counts as passed for rulesets and automerge.
        report(no_review_reason(head))
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
