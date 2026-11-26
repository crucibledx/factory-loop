#!/usr/bin/env python3
"""Offline tests for review/usage_limit.py: spotting a usage-limit stop, marking it, and re-running it after reset."""
import datetime
import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "review"))
import usage_limit as ul  # noqa: E402

failures = []
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 26, 14, 6, 25, tzinfo=UTC)
# The line droid exec printed in crucibledx/slack-bridge run 45835615608.
LOG = ('Error during droid execution: 402 {"detail":"You\'ve reached your 5-hour Droid Core usage limit '
       '(resets in 4h 37min).\\nReload Extra Usage credits or wait for your limits to reset.","status":402,'
       '"title":"Payment Required","displayToUser":true}\n')


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


at = lambda h, m: datetime.datetime(2026, 11, 26, h, m, tzinfo=UTC)  # noqa: E731
check("the real 402 log is a usage-limit stop, reset rounded up to the minute",
      ul.limit_reset(LOG, NOW) == (True, at(18, 44)))
ERR = "Error during droid execution: 402 "
check("minutes only", ul.limit_reset(ERR + "Droid Core usage limit (resets in 37min)", NOW) == (True, at(14, 44)))
check("days and hours", ul.limit_reset(ERR + "weekly usage limit, resets in 1d 2h", NOW)
      == (True, datetime.datetime(2026, 11, 27, 16, 7, tzinfo=UTC)))
check("a limit without a reset time is still a stop", ul.limit_reset(ERR + "usage limit reached", NOW) == (True, None))
check("other failures are not a usage-limit stop",
      ul.limit_reset("Error: 500 internal error\nusage limit docs: https://x/402s\n", NOW)[0] is False
      and ul.limit_reset("Error: model not found", NOW) == (False, None))
check("the reviewer quoting a 402 usage-limit error is not a stop",
      ul.limit_reset("P2: the step should catch '402 ... usage limit (resets in 4h)'\n"
                     "  > " + LOG + "Error during droid execution: 500 server error\n", NOW) == (False, None))

ul.utcnow = lambda: NOW
with tempfile.TemporaryDirectory() as tmp:
    log_path, summary = f"{tmp}/droid.log", f"{tmp}/summary.md"
    os.environ["GITHUB_STEP_SUMMARY"] = summary
    open(log_path, "w").write("starting review\n" + LOG)
    out = io.StringIO()
    with redirect_stdout(out):
        ul.note(log_path)
    annotation = next((ln for ln in out.getvalue().splitlines() if ln.startswith("::error ")), "")
    check("note annotates the job as a usage-limit stop with the reset time",
          annotation.startswith(f"::error title={ul.TITLE}::") and "resets at 2026-11-26T18:44Z" in annotation
          and "not a review verdict" in annotation)
    check("note writes the same to the job summary", "resets at 2026-11-26T18:44Z" in open(summary).read())
    MESSAGE = annotation.split("::", 2)[2]

    open(log_path, "w").write("Error: model not found\n")
    os.remove(summary)
    out = io.StringIO()
    with redirect_stdout(out):
        ul.note(log_path)
    check("note stays silent for other failures", out.getvalue() == "" and not os.path.exists(summary))
    out = io.StringIO()
    with redirect_stdout(out):
        code = exit_code(lambda: ul.note(f"{tmp}/missing.log"))
    check("note never fails the step itself", code == 0 and "cannot read" in out.getvalue())
    del os.environ["GITHUB_STEP_SUMMARY"]

HEAD, NEW = "a" * 40, "b" * 40
LIMIT = [{"title": ul.TITLE, "message": MESSAGE}]
PAST_LIMIT = [{"title": ul.TITLE, "message": MESSAGE.replace("18:44Z", "13:00Z")}]
NO_RESET = [{"title": ul.TITLE, "message": "The reset time was not reported."}]
GATE_FAIL = [{"title": "", "message": "Process completed with exit code 1."}]


def run(rid, attempt=1, pr=1, sha=HEAD):
    return {"id": rid, "run_attempt": attempt, "head_sha": sha, "pull_requests": [{"number": pr}] if pr else []}


# run id -> (review job conclusion, annotations)
JOBS = {1: ("failure", PAST_LIMIT), 2: ("failure", LIMIT), 3: ("failure", GATE_FAIL), 4: ("failure", PAST_LIMIT),
        5: ("failure", PAST_LIMIT), 6: ("failure", NO_RESET), 7: ("failure", PAST_LIMIT), 8: ("success", []),
        9: ("failure", PAST_LIMIT)}
PRS = {1: {"state": "open", "head": {"sha": HEAD}}, 4: {"state": "open", "head": {"sha": NEW}},
       7: {"state": "open", "draft": True, "head": {"sha": HEAD}}, 9: {"state": "closed", "head": {"sha": HEAD}}}
RUNS = {"o/live": [run(1), run(2), run(3), run(4, pr=4), run(5, attempt=ul.MAX_ATTEMPTS), run(6), run(7, pr=7),
                   run(8), run(9, pr=9), run(10, pr=None)],
        "o/broken": None}
JOBS[10] = ("failure", PAST_LIMIT)
JOBS[11] = ("failure", PAST_LIMIT)
# run 11 fails to load before older runs 1 and 6 are reached
RUNS["o/live"].insert(0, run(11))
calls = []


def fake_request(method, path, body=None):
    calls.append((method, path))
    if path.startswith("/installation/repositories"):
        return {"repositories": [{"full_name": "o/old", "archived": True}, {"full_name": "o/broken"},
                                 {"full_name": "o/live"}]}
    repo = "/".join(path.split("/")[2:4])
    if "/actions/runs?" in path:
        if RUNS[repo] is None:
            raise RuntimeError("GET runs -> 502")
        assert "event=pull_request&status=failure&created=%3E%3D2026-11-18" in path, path
        return {"workflow_runs": RUNS[repo]}
    if path.endswith("/jobs?filter=latest"):
        rid = int(path.split("/")[-2])
        return {"jobs": [{"id": 100 + rid, "name": "automerge / automerge", "conclusion": "failure"},
                         {"id": 200 + rid, "name": "review / review", "conclusion": JOBS[rid][0]}]}
    if path.endswith("/annotations"):
        rid = int(path.split("/")[-2]) - 200
        if rid == 11:
            raise RuntimeError("GET annotations -> 404")
        return JOBS[rid][1]
    if "/pulls/" in path:
        return PRS.get(int(path.rsplit("/", 1)[1]), PRS[1])
    return {}


ul.request = fake_request
out = io.StringIO()
with redirect_stdout(out):
    code = exit_code(ul.retry)
reruns = sorted(int(p.split("/")[-2]) - 200 for m, p in calls if m == "POST")
report = out.getvalue()
check("re-runs only open, non-draft, same-head PR runs past their reset (or with no reset time)", reruns == [1, 6])
check("only the review job is re-run, not the run's other failed jobs",
      all(p.startswith("/repos/o/live/actions/jobs/2") and p.endswith("/rerun") for m, p in calls if m == "POST"))
check("a run before its reset waits", "run 2 (aaaaaaa): waiting for the reset at 2026-11-26T18:44Z" in report)
check("a review that failed for another reason is left alone", "run 3 " not in report and "run 8 " not in report)
check("a newer head, a draft, a closed PR, or no PR is skipped",
      all(any(f"run {r} " in ln and ln.endswith("skipped") for ln in report.splitlines()) for r in (4, 7, 9, 10)))
check("attempts are capped", f"after {ul.MAX_ATTEMPTS} attempts" in report)
check("archived repos are not swept", not any("/repos/o/old/" in p for _, p in calls))
check("one repo's API error is reported, the others are still swept, and the job fails",
      code == 1 and "o/broken: GET runs -> 502" in report and 1 in reruns)
check("one run's API error is reported and the repo's other runs are still swept",
      "o/live run 11: RuntimeError('GET annotations -> 404')" in report and reruns == [1, 6])

pages = {1: [{"full_name": f"o/r{i}"} for i in range(100)], 2: [{"full_name": "o/last"}]}
ul.request = lambda method, path, body=None: {"repositories": pages[int(path.rsplit("page=", 1)[1])]}
check("paged follows a full page to the next one", len(list(ul.paged("/installation/repositories", "repositories"))) == 101)

# The Review step as written in loop-review.yml, run the way Actions runs it, with a fake droid that fails at the limit.
lines = open(os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "loop-review.yml")).read().splitlines()
start = lines.index("      - name: Review")
start = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |") + 1
body = []
for ln in lines[start:]:
    if ln.strip() and not ln.startswith(" " * 10):
        break
    body.append(ln[10:])
step = "\n".join(body).replace("${{ inputs.review_model }}", "m")
with tempfile.TemporaryDirectory() as tmp:
    os.makedirs(f"{tmp}/bin")
    os.makedirs(f"{tmp}/.factory-loop")
    os.symlink(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "review")), f"{tmp}/.factory-loop/review")
    open(f"{tmp}/bin/curl", "w").write("#!/bin/sh\n")
    open(f"{tmp}/bin/droid", "w").write('#!/bin/sh\necho "$FAKE_OUT" >&2\nexit "$FAKE_STATUS"\n')
    os.chmod(f"{tmp}/bin/curl", 0o755)
    os.chmod(f"{tmp}/bin/droid", 0o755)
    open(f"{tmp}/step.sh", "w").write(step + "\necho STEP_DONE\n")
    for shell in (["bash", "-e"], ["bash", "-eo", "pipefail"]):
        results = {}
        for status, out in (("1", LOG), ("3", "Error: model not found"), ("0", "review written")):
            env = {**os.environ, "PATH": f"{tmp}/bin:" + os.environ["PATH"], "HOME": tmp, "RUNNER_TEMP": tmp,
                   "LOOP_REVIEW_DIR": tmp, "FAKE_STATUS": status, "FAKE_OUT": out}
            env.pop("GITHUB_STEP_SUMMARY", None)
            done = subprocess.run([*shell, f"{tmp}/step.sh"], cwd=tmp, env=env, capture_output=True, text=True)
            results[status] = (done.returncode, done.stdout)
        name = " ".join(shell)
        check(f"{name}: a usage-limit stop keeps droid's status and is annotated",
              results["1"][0] == 1 and f"::error title={ul.TITLE}::" in results["1"][1])
        check(f"{name}: another failure keeps droid's status without the annotation",
              results["3"][0] == 3 and "::error" not in results["3"][1])
        check(f"{name}: a clean review goes on", results["0"][0] == 0 and "STEP_DONE" in results["0"][1])

sys.exit(1 if failures else 0)
