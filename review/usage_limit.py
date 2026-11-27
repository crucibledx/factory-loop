#!/usr/bin/env python3
"""Tell a Factory usage-limit stop of the review apart from a review verdict, and re-run those reviews after the reset.

Subcommands:
  note LOG  after a failed `droid exec`: if LOG shows the usage limit, annotate the job ("Review usage limit") with
            the reset time and write it to the job summary. Exits 0 either way; the caller keeps the step red.
  retry     scheduled sweep (GH_TOKEN of an app installed on the org): re-run review jobs that stopped at the usage
            limit once their reset time has passed, while the PR is open, not a draft, and still at the same head.
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loop_review import report, request  # noqa: E402

TITLE = "Review usage limit"
# The log also holds the reviewer's output, which may quote a CLI error; the CLI's own error that ended the exec is
# the last one, so only that line is classified.
CLI_ERROR = re.compile(r"^\s*Error during droid execution:", re.IGNORECASE)
LIMIT_ERROR = re.compile(r"^\s*Error during droid execution: 402\b.*usage limit", re.IGNORECASE)
RESETS_IN = re.compile(r"resets in ((?:\s*\d+\s*(?:d|h|min|m|s)\b)+)", re.IGNORECASE)
RESETS_AT = re.compile(r"resets at (\d{4}-\d\d-\d\dT\d\d:\d\dZ)")
UNITS = {"d": 86400, "h": 3600, "min": 60, "m": 60, "s": 1}
LOOKBACK_DAYS = 8  # longer than the longest reset (the weekly limit), so a stopped run is still swept
MAX_ATTEMPTS = 10  # a limit that never resets must not re-run the job forever


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def limit_reset(log_text, now):
    """(hit, reset) for a droid exec log: hit is True on a 402 usage-limit error; reset is when it lifts, or None."""
    line = next((ln for ln in reversed(log_text.splitlines()) if CLI_ERROR.search(ln)), None)
    if line is None or not LIMIT_ERROR.search(line):
        return False, None
    found = RESETS_IN.search(line)
    if not found:
        return True, None
    seconds = sum(int(n) * UNITS[u.lower()] for n, u in re.findall(r"(\d+)\s*(d|h|min|m|s)\b", found.group(1), re.I))
    # Round up to the minute so a retry never lands just before the reset.
    reset = (now + datetime.timedelta(seconds=seconds + 59)).replace(second=0, microsecond=0)
    return True, reset


def fmt(moment):
    return moment.strftime("%Y-%m-%dT%H:%MZ")


def note(log_path):
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            log_text = fh.read()
    except OSError as err:
        print(f"cannot read {log_path}: {err}")
        return
    hit, reset = limit_reset(log_text, utcnow())
    if not hit:
        return
    when = f"The limit resets at {fmt(reset)}." if reset else "The reset time was not reported."
    message = (f"The Factory usage limit stopped the reviewer, so this commit has no review yet. This is not a review "
               f"verdict. {when} The scheduled review retry re-runs this job after the reset; re-run it by hand to "
               f"go sooner.")
    print(f"::error title={TITLE}::{message}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### {TITLE}\n\n{message}\n")


def paged(path, key):
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        data = request("GET", f"{path}{sep}per_page=100&page={page}")
        items = data[key] if key else data
        yield from items
        if len(items) < 100:
            return
        page += 1


def stopped_at_limit(repo, job_id):
    """(stopped, reset) from the job's annotations: whether `note` marked it, and the reset time it reported."""
    for annotation in paged(f"/repos/{repo}/check-runs/{job_id}/annotations", None):
        if annotation.get("title") == TITLE:
            found = RESETS_AT.search(annotation.get("message") or "")
            if not found:
                return True, None
            return True, datetime.datetime.strptime(found.group(1), "%Y-%m-%dT%H:%MZ").replace(
                tzinfo=datetime.timezone.utc)
    return False, None


def retry_run(repo, run, now):
    """Re-run the review job of run if the usage limit stopped it. Returns a log line or None."""
    jobs = paged(f"/repos/{repo}/actions/runs/{run['id']}/jobs?filter=latest", "jobs")
    review = next((j for j in jobs if j["name"].split(" / ")[-1] == "review" and j["conclusion"] == "failure"), None)
    if not review:
        return None
    stopped, reset = stopped_at_limit(repo, review["id"])
    if not stopped:
        return None
    where = f"{repo} run {run['id']} ({run['head_sha'][:7]})"
    if reset and now < reset:
        return f"{where}: waiting for the reset at {fmt(reset)}"
    if run.get("run_attempt", 1) >= MAX_ATTEMPTS:
        return f"{where}: still at the usage limit after {MAX_ATTEMPTS} attempts; re-run it by hand"
    prs = run.get("pull_requests") or []
    if not prs:
        return f"{where}: no open PR for this run; skipped"
    number = prs[0]["number"]
    pr = request("GET", f"/repos/{repo}/pulls/{number}")
    if pr["state"] != "open" or pr.get("draft") or pr["head"]["sha"] != run["head_sha"]:
        return f"{where}: PR #{number} is closed, a draft, or has a newer head; skipped"
    # Only the review job: other failed jobs of the run (auto-merge, for one) are not ours to repeat.
    request("POST", f"/repos/{repo}/actions/jobs/{review['id']}/rerun", {})
    return f"{where}: re-ran the review for PR #{number}"


def retry():
    now = utcnow()
    since = (now - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    lines, errors = [], []
    for repo in paged("/installation/repositories", "repositories"):
        if repo.get("archived"):
            continue
        name = repo["full_name"]
        try:
            runs = list(paged(f"/repos/{name}/actions/runs?event=pull_request&status=failure&created=%3E%3D{since}",
                              "workflow_runs"))
        except RuntimeError as err:
            errors.append(f"{name}: {err}")
            continue
        for run in runs:
            # One run that cannot be handled must not hide the rest of the repo's runs from every sweep.
            try:
                line = retry_run(name, run, now)
            except (RuntimeError, KeyError, TypeError, ValueError) as err:
                errors.append(f"{name} run {run.get('id')}: {err!r}")
                continue
            if line:
                lines.append(line)
    report("\n".join([f"### {TITLE} retry", ""] + [f"- {ln}" for ln in lines or ["nothing to re-run"]]
                     + [f"- error: {e}" for e in errors]))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "note":
        note(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "retry":
        retry()
    else:
        sys.exit(__doc__)
