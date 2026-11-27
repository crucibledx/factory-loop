#!/usr/bin/env python3
"""Offline tests for scripts/toolchain.py, the setup-toolchain action, and how loop-ci.yml uses them."""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import toolchain as tc  # noqa: E402

failures = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def repo(files):
    """A temp repo with the given files; dict values are written as JSON."""
    path = tempfile.mkdtemp()
    for name, body in files.items():
        full = os.path.join(path, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(body) if isinstance(body, (dict, list)) else body)
    return path


def run(files, env=None):
    """main() on a temp repo: (exit code, stdout, parsed outputs)."""
    path = repo(files)
    out_file = os.path.join(path, "github_output")
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = tc.main(["toolchain.py", path], {**(env or {}), "GITHUB_OUTPUT": out_file})
    return code, buf.getvalue(), parse_outputs(open(out_file).read()) if os.path.exists(out_file) else {}


def parse_outputs(text):
    """$GITHUB_OUTPUT as Actions reads it: name=value lines and name<<DELIM blocks."""
    result, lines = {}, iter(text.splitlines())
    for line in lines:
        if "<<" in line and ("=" not in line or line.index("<<") < line.index("=")):
            name, delim = line.split("<<", 1)
            block = []
            for inner in lines:
                if inner == delim:
                    break
                block.append(inner)
            result[name] = "\n".join(block)
        else:
            name, value = line.split("=", 1)
            result[name] = value
    return result


PKG = {"scripts": {"lint": "eslint .", "typecheck": "tsc", "build": "tsc -b"}}
DECL = ".factory/toolchain.json"

# Inference: every current caller keeps its behavior without a declaration.
code, out, o = run({"package.json": PKG, "bun.lock": ""})
check("bun.lock and package.json infer bun with the old defaults",
      code == 0 and o["stack"] == "bun" and o["quality"] == "bun run lint\nbun run typecheck"
      and o["test"] == "bun test --pass-with-no-tests" and o["build"] == "" and o["os"] == '["ubuntu-latest"]'
      and o["multi_os"] == "false")
check("a quality script package.json doesn't define is skipped with a notice",
      "::notice::Script format:check not defined, skipped." in out)
check("package.json alone infers bun", run({"package.json": PKG})[2]["stack"] == "bun")
code, out, o = run({"go.mod": "module x\n"})
check("go.mod infers go with the make targets",
      code == 0 and o["stack"] == "go" and o["quality"] == "make lint" and o["test"] == "make test"
      and o["build"] == "make build")
code, out, o = run({"README.md": "docs"})
check("a repo with neither infers none and passes with a notice",
      code == 0 and o["stack"] == "none" and o["quality"] == "" and o["test"] == "" and o["build"] == ""
      and "::notice::Stack none: nothing to check." in out)
check("package.json wins over go.mod, as loop-ci ran Bun before",
      run({"package.json": PKG, "go.mod": "module x\n"})[2]["stack"] == "bun")

# The slack-bridge caller: its inputs give the same commands as before.
code, out, o = run({"package.json": PKG, "bun.lock": ""}, {"TEST_COMMAND": "bun test", "BUILD_COMMAND": "bun run build"})
check("caller inputs keep the commands a Bun caller set", o["test"] == "bun test" and o["build"] == "bun run build")
o = run({"package.json": PKG}, {"QUALITY_SCRIPTS": "lint missing"})[2]
check("quality_scripts picks the package scripts", o["quality"] == "bun run lint")
o = run({"package.json": {"scripts": {"lint; rm -rf x": "eslint"}}}, {"QUALITY_SCRIPTS": "lint;_rm"})[2]
check("an undefined script name never becomes a command", o["quality"] == "")
o = run({"package.json": {"scripts": {"it's": "eslint"}}}, {"QUALITY_SCRIPTS": "it's"})[2]
check("a script name is shell-quoted", o["quality"] == "bun run 'it'\"'\"'s'")

# The declaration.
ember = {"stack": "go", "os": ["ubuntu-latest", "macos-latest", "windows-latest"]}
code, out, o = run({"go.mod": "module x\n", DECL: ember})
check("a declared os list becomes the test lanes",
      code == 0 and json.loads(o["os"]) == ember["os"] and o["multi_os"] == "true")
decl = {"stack": "none", "checks": {"quality": ["sh scripts/lint.sh"], "test": "sh scripts/check.sh"}}
o = run({DECL: decl})[2]
check("stack none runs the checks it declares",
      o["stack"] == "none" and o["quality"] == "sh scripts/lint.sh" and o["test"] == "sh scripts/check.sh")
o = run({"package.json": PKG, DECL: {"checks": {"quality": ["bun run lint", "bunx knip"], "build": "bun run build"}}})[2]
check("checks.quality replaces the default package scripts with commands; the stack is still inferred",
      o["stack"] == "bun" and o["quality"] == "bun run lint\nbunx knip" and o["build"] == "bun run build")
code, out, o = run({"go.mod": "module x\n", DECL: {"checks": {"test": "", "build": ""}}})
check("checks.test and checks.build set to \"\" skip them, with a notice",
      o["test"] == "" and o["build"] == "" and o["quality"] == "make lint"
      and "::notice::No test command, tests skipped." in out)
o = run({"go.mod": "module x\n", DECL: {"checks": {"test": "go test ./..."}}}, {"TEST_COMMAND": "make e2e"})[2]
check("a caller input wins over the declaration", o["test"] == "make e2e")
o = run({DECL: {"stack": "bun"}})[2]
check("a declared bun stack without package.json has nothing to install or run",
      o["quality"] == "" and o["test"] == "")

# Invalid declarations and inputs fail with a message that says what to change.
bad = [
    ("not JSON", "{", "cannot read it as JSON"),
    ("not an object", [], "must be a JSON object"),
    ("an unknown key", {"stak": "go"}, "unknown keys ['stak']"),
    ("an unknown stack", {"stack": "python"}, "stack must be one of ['bun', 'go', 'none']"),
    ("an empty os list", {"os": []}, "os must be a list of 1 to 8"),
    ("an os that isn't a list", {"os": "ubuntu-latest"}, "os must be a list"),
    ("a bad runner label", {"os": ["ubuntu latest"]}, "os entries must be distinct runner labels"),
    ("a repeated runner", {"os": ["ubuntu-latest", "ubuntu-latest"]}, "os entries must be distinct"),
    ("checks that isn't an object", {"checks": []}, "checks must be an object"),
    ("an unknown check", {"checks": {"lint": "x"}}, "unknown checks ['lint']"),
    ("checks.quality as a string", {"checks": {"quality": "make lint"}}, "checks.quality must be a list"),
    ("an empty quality command", {"checks": {"quality": [" "]}}, "must not be empty"),
    ("a multi-line command", {"checks": {"test": "make\nmake"}}, "checks.test must be a one-line command"),
    ("a non-string command", {"checks": {"build": 1}}, "checks.build must be a one-line command"),
]
for label, body, message in bad:
    code, out, o = run({DECL: body})
    check(f"{label} fails and names the declaration",
          code == 1 and o == {} and f"::error file={DECL}::" in out and message in out)
code, out, o = run({"go.mod": "module x\n"}, {"QUALITY_SCRIPTS": "lint"})
check("quality_scripts on a go repo fails and points at checks.quality",
      code == 1 and "checks.quality" in out and "::error::" in out)
code, out, o = run({"package.json": "{"})
check("an unreadable package.json fails and names it", code == 1 and "::error file=package.json::" in out)
code, out, o = run({"package.json": PKG}, {"TEST_COMMAND": "a\nb"})
check("a multi-line input fails", code == 1 and "the test_command input must be a one-line command" in out)
check("annotations escape newlines and percent signs", tc.annotation("50%\nx\r") == "50%25%0Ax%0D")

# The CLI, as the resolve job runs it.
path = repo({"go.mod": "module x\n"})
proc = subprocess.run([sys.executable, os.path.join(HERE, "toolchain.py")], cwd=path, capture_output=True, text=True,
                      env={k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"})
check("the CLI resolves the working directory and prints outputs without GITHUB_OUTPUT",
      proc.returncode == 0 and parse_outputs(proc.stdout.split("\n", 1)[1])["stack"] == "go")

# loop-ci.yml and the setup action, read as text.
workflow = open(os.path.join(ROOT, ".github", "workflows", "loop-ci.yml"), encoding="utf-8").read()
action = open(os.path.join(ROOT, ".github", "actions", "setup-toolchain", "action.yml"), encoding="utf-8").read()
jobs = dict(re.findall(r"(?ms)^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", workflow.split("\njobs:\n", 1)[1]))
check("the job ids keep the required checks: ci / quality, ci / test and ci / build",
      {"resolve", "quality", "test-lane", "test", "build"} <= set(jobs))
check("the test gate needs the lanes and always runs, so ci / test is never skipped",
      "needs: [resolve, test-lane]" in jobs["test"] and "if: always()" in jobs["test"]
      and "runs-on: ${{" not in jobs["test"])
check("the gate fails unless every lane passed, or there are no tests",
      'success) echo "Every test lane passed."' in jobs["test"] and '[ "$RESOLVE" != success ]' in jobs["test"]
      and 'if [ -n "$TEST_COMMAND" ]' in jobs["test"])
check("the lanes run on the declared runners, without cancelling each other",
      "os: ${{ fromJSON(needs.resolve.outputs.os) }}" in jobs["test-lane"]
      and "runs-on: ${{ matrix.os }}" in jobs["test-lane"] and "fail-fast: false" in jobs["test-lane"]
      and "shell: bash" in jobs["test-lane"])
check("the resolve job runs the resolver with the caller's inputs",
      "python3 .factory-loop/scripts/toolchain.py" in jobs["resolve"]
      and all(f"{k}: ${{{{ inputs.{k.lower()} }}}}" in jobs["resolve"]
              for k in ("QUALITY_SCRIPTS", "TEST_COMMAND", "BUILD_COMMAND")))
check("every job that installs uses the setup action from factory-loop at loop_ref",
      all("uses: ./.factory-loop/.github/actions/setup-toolchain" in jobs[j]
          and "ref: ${{ inputs.loop_ref }}" in jobs[j] for j in ("quality", "test-lane", "build")))
outputs = set(re.findall(r"^([a-z_]+)=", tc.outputs(tc.resolve(repo({}), {})), re.M)) | {"quality"}
check("every resolver output reaches the resolve job's outputs",
      all(f"{name}: ${{{{ steps.toolchain.outputs.{name} }}}}" in jobs["resolve"] for name in outputs))
uses = re.findall(r"uses: ([^\s]+)", workflow + action)
check("every third-party action is pinned to a commit SHA",
      all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses if not u.startswith("./")))
check("the setup action handles every stack the resolver knows",
      all(f"inputs.stack == '{s}'" in action or s == "none" for s in tc.STACKS)
      and all(f"inputs.stack != '{s}'" in action for s in tc.STACKS))

sys.exit(1 if failures else 0)
