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
code, out, o = run({DECL: {"stack": "assets"}})
check("the assets stack optimizes SVGs, fails on the diff and checks LFS tracking, with no test or build",
      code == 0 and o["stack"] == "assets"
      and o["quality"] == "bash scripts/optimize-svgs.sh\ngit diff --exit-code\nbash scripts/check-lfs.sh"
      and o["test"] == "" and o["build"] == "")
# The scripts have a bash shebang and bashisms; the runner's sh (dash) would fail them. Run the resolved command.
svg_repo = repo({"scripts/optimize-svgs.sh": "#!/usr/bin/env bash\nset -euo pipefail\ns=x; [[ $s == x ]]\n"})
line1 = o["quality"].splitlines()[0]
done = subprocess.run(["bash", "-eo", "pipefail", "-c", line1], cwd=svg_repo, capture_output=True, text=True)
check("the resolved optimizer command runs a bash-only script", done.returncode == 0 and line1.startswith("bash "))

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
    ("an unknown stack", {"stack": "python"}, "stack must be one of ['bun', 'go', 'assets', 'none']"),
    ("an empty os list", {"os": []}, "os must be a list of 1 to 8"),
    ("an os that isn't a list", {"os": "ubuntu-latest"}, "os must be a list"),
    ("a bad runner label", {"os": ["ubuntu latest"]}, "os entries must be distinct runner labels"),
    ("a runner label with a newline", {"os": ["ubuntu-latest\n"]}, "os entries must be distinct runner labels"),
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
code, out, o = run({"package.json": PKG}, {"TEST_COMMAND": "bun run prepare-tests\nbun test"})
check("a multi-line caller command is kept, serialized as a block",
      code == 0 and o["test"] == "bun run prepare-tests\nbun test")
o = run({"go.mod": "module x\n"}, {"TEST_COMMAND": ""})[2]
check("an explicit empty test_command skips tests even when the stack has a default", o["test"] == "")
o = run({"go.mod": "module x\n"}, {"BUILD_COMMAND": ""})[2]
check("an explicit empty build_command skips the build even when the stack has a default", o["build"] == "")
o = run({"package.json": PKG}, {"QUALITY_SCRIPTS": ""})[2]
check("an explicit empty quality_scripts runs no quality checks, as before the resolver", o["quality"] == "")
o = run({"go.mod": "module x\n", DECL: {"checks": {"test": "go test ./..."}}}, {"TEST_COMMAND": ""})[2]
check("an explicit empty input also overrides the declaration", o["test"] == "")
check("annotations escape newlines and percent signs", tc.annotation("50%\nx\r") == "50%25%0Ax%0D")

# The CLI, as the resolve job runs it.
path = repo({"go.mod": "module x\n"})
proc = subprocess.run([sys.executable, os.path.join(HERE, "toolchain.py")], cwd=path, capture_output=True, text=True,
                      env={k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"})
check("the CLI resolves the working directory and prints outputs without GITHUB_OUTPUT",
      proc.returncode == 0 and parse_outputs(proc.stdout.split("\n", 1)[1])["stack"] == "go")

# The --describe CLI, as loop-review renders it into the run_checks prompt.
proc = subprocess.run([sys.executable, os.path.join(HERE, "toolchain.py"), "--describe"],
                      cwd=repo({"go.mod": "module x\n"}), capture_output=True, text=True,
                      env={k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"})
check("--describe prints the resolved stack, runners and commands",
      proc.returncode == 0 and "Stack: go." in proc.stdout and "quality: make lint" in proc.stdout
      and "test: make test" in proc.stdout and "build: make build" in proc.stdout)
proc = subprocess.run([sys.executable, os.path.join(HERE, "toolchain.py"), "--describe"],
                      cwd=repo({DECL: {"stack": "python"}}), capture_output=True, text=True,
                      env={k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"})
check("--describe fails with the reason on an invalid declaration",
      proc.returncode == 1 and "stack must be one of" in proc.stdout)

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
check("the resolve inputs default to the resolver's sentinel",
      workflow.count("default: toolchain-default") == 3 and tc.INPUT_DEFAULT == "toolchain-default")
uses = re.findall(r"uses: ([^\s]+)", workflow + action)
check("every third-party action is pinned to a commit SHA",
      all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses if not u.startswith("./")))
check("the setup action handles every stack the resolver knows",
      all(f"inputs.stack == '{s}'" in action or s == "none" for s in tc.STACKS)
      and all(f"inputs.stack != '{s}'" in action for s in tc.STACKS))
assets_blocks = [b for b in action.split("\n    - ") if "inputs.stack == 'assets'" in b]
check("the assets setup is bun for bunx svgo plus a Git LFS pull, installing nothing",
      len(assets_blocks) == 2
      and any("oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6" in b for b in assets_blocks)
      and any("git lfs install" in b and "git lfs pull" in b for b in assets_blocks)
      and all("bun install" not in b for b in assets_blocks))
bun_steps = action.split("inputs.stack == 'bun'")
check("the bun setup keeps the callers' version resolution: .bun-version only when bun_version is empty",
      len(bun_steps) >= 4 and '[ -z "$BUN_VERSION" ] && [ -f .bun-version ]' in action
      and 'echo "file=.bun-version" >> "$GITHUB_OUTPUT"' in action
      and "bun-version: ${{ inputs.bun-version }}" in action
      and "bun-version-file: ${{ steps.bun-file.outputs.file }}" in action)
check("the bun install stays conditional on package.json, with an ignore-scripts mode for untrusted checkouts",
      'if [ -f package.json ]; then' in action
      and 'if [ "$IGNORE_SCRIPTS" = true ]; then bun install --frozen-lockfile --ignore-scripts;' in action
      and 'else bun install --frozen-lockfile; fi' in action
      and 'IGNORE_SCRIPTS: ${{ inputs.ignore-scripts }}' in action
      and 'ignore-scripts:' in action)
check("the install step consumes the version the step resolved, pinned and install-only",
      "version: ${{ steps.golangci-version.outputs.version }}" in action
      and "golangci/golangci-lint-action@ba0d7d2ec06a0ea1cb5fa41b2e4a3ab91d21278a" in action
      and "install-only: true" in action
      and "steps.golangci-version.outputs.version != ''" in action)

# The golangci version step's shell, run against real Makefiles.
golangci_step = action.split("- id: golangci-version", 1)[1].split("\n    - ", 1)[0]
golangci_shell = re.search(r"run: \|\n((?:        .+\n?)+)", golangci_step).group(1)
def golangci_version(makefile):
    path = repo({"Makefile": makefile})
    out_file = os.path.join(path, "github_output")
    proc = subprocess.run(["bash", "-c", golangci_shell], cwd=path, capture_output=True, text=True,
                          env={"GITHUB_OUTPUT": out_file, "PATH": os.environ["PATH"]})
    emitted = open(out_file).read() if os.path.exists(out_file) else ""
    return proc.returncode, proc.stdout + proc.stderr, emitted
code, out, emitted = golangci_version("golangci-lint-version:\n\t@echo v2.15.0\n")
check("the golangci version step reads the repo's make pin", code == 0 and "version=v2.15.0" in emitted)
code, out, emitted = golangci_version("all:\n\t@true\n")
check("without the make target it skips with a notice and no version",
      code == 0 and "::notice::" in out and "version=" not in emitted)

# The ci / test gate's shell, run with the values the workflow passes it.
gate = re.search(r"run: \|\n((?:          .+\n?)+)", jobs["test"]).group(1)
def gate_rc(resolve, lanes, test_command):
    proc = subprocess.run(["bash", "-c", gate], capture_output=True,
                          env={"RESOLVE": resolve, "LANES": lanes, "TEST_COMMAND": test_command, "PATH": "/usr/bin:/bin"})
    return proc.returncode
check("the gate passes when every lane passed", gate_rc("success", "success", "make test") == 0)
check("the gate fails when a lane failed or was cancelled",
      gate_rc("success", "failure", "make test") != 0 and gate_rc("success", "cancelled", "make test") != 0)
check("the gate fails when the resolve job failed", gate_rc("failure", "skipped", "") != 0)
check("the gate fails when lanes were skipped but a test command resolved",
      gate_rc("success", "skipped", "make test") != 0)
check("the gate passes with a notice when there are no tests", gate_rc("success", "skipped", "") == 0)

# The other workflows that set up a toolchain, read as text.
review_wf = open(os.path.join(ROOT, ".github", "workflows", "loop-review.yml"), encoding="utf-8").read()
reviewer = review_wf.split("\n  reviewer:\n", 1)[1].split("\n  review:\n", 1)[0]
check("the review's run_checks resolves and sets up the repo's toolchain, never the Bun-only steps",
      "setup-bun" not in reviewer and "python3 .factory-loop/scripts/toolchain.py" in reviewer
      and "uses: ./.factory-loop/.github/actions/setup-toolchain" in reviewer
      and 'ignore-scripts: "true"' in reviewer)
resolve_step = reviewer.split("name: Resolve the toolchain", 1)[1].split("\n      - ", 1)[0]
setup_step = reviewer.split("name: Set up the toolchain", 1)[1].split("\n      - ", 1)[0]
check("a failed toolchain install is still noted, never fatal",
      "steps.toolchain.outcome == 'failure'" in reviewer and "steps.setup.outcome == 'failure'" in reviewer
      and "continue-on-error: true" in resolve_step and "continue-on-error: true" in setup_step
      and "actionlint" in reviewer)
check("under ignore-scripts the go pin's Makefile never runs, so review setup executes no PR code",
      "if: inputs.stack == 'go' && inputs.ignore-scripts != 'true'" in action
      and "ignore-scripts: skipping the Makefile" in action)
check("no plain-scalar run value carries ::, which breaks YAML (actionlint does not lint composite actions)",
      'run: echo "::' not in action)
for name in ("loop-mention.yml", "loop-implement.yml"):
    wf = open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8").read()
    check(f"{name} sets up the resolved toolchain from factory-loop at loop_ref, not always Bun",
          "setup-bun" not in wf and "repository: crucibledx/factory-loop" in wf
          and "ref: ${{ inputs.loop_ref }}" in wf and "default: v0" in wf
          and "python3 .factory-loop/scripts/toolchain.py" in wf
          and "uses: ./.factory-loop/.github/actions/setup-toolchain" in wf)
implement = open(os.path.join(ROOT, ".github", "workflows", "loop-implement.yml"), encoding="utf-8").read()
check("setup_bun stays as a deprecated input that gates only the bun stack",
      "setup_bun:" in implement and "Deprecated." in implement
      and "steps.toolchain.outputs.stack != 'bun' || inputs.setup_bun" in implement)
ASIDE = 'run: mv .factory-loop "$RUNNER_TEMP/factory-loop"'
BACK = 'run: mv "$RUNNER_TEMP/factory-loop" .factory-loop'
ci_wf = open(os.path.join(ROOT, ".github", "workflows", "loop-ci.yml"), encoding="utf-8").read()
asides = [i for i in range(len(ci_wf)) if ci_wf.startswith(ASIDE, i)]
restores = [i for i in range(len(ci_wf)) if ci_wf.startswith(BACK, i)]
setups = [i for i in range(len(ci_wf)) if ci_wf.startswith("uses: ./.factory-loop/.github/actions/setup-toolchain", i)]
cmds = [ci_wf.index(m) for m in ('done <<< "$QUALITY"', 'bash -eo pipefail -c "$TEST_COMMAND"',
                                 'bash -eo pipefail -c "$BUILD_COMMAND"')]
check("every ci job moves .factory-loop aside after its setup and restores it after the repo's commands",
      len(asides) == 3 and len(restores) == 3 and len(setups) == 3
      and all(s < a < c < r for s, a, c, r in zip(setups, asides, cmds, restores))
      and ci_wf.count('- name: Restore the factory-loop checkout\n        if: always()') == 3)
for name in ("loop-mention.yml", "loop-implement.yml"):
    wf = open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8").read()
    check(f"{name} moves .factory-loop aside before droid-action and restores it after",
          wf.index("setup-toolchain") < wf.index(ASIDE)
          < wf.index("Factory-AI/droid-action") < wf.index(BACK))

# install.sh never installs an active declaration: a copied toolchain.json would override inference.
install = open(os.path.join(ROOT, "scripts", "install.sh"), encoding="utf-8").read()
check("install.sh never installs a toolchain.json (a declaration overrides inference)",
      "copy .factory/toolchain.json" not in install)

# The repo template's shipped examples resolve as the README documents them.
for name, want_stack, want in [
    ("toolchain.bun.example.json", "bun", {"quality": "", "test": "bun test", "build": "bun run build"}),
    ("toolchain.go.example.json", "go", {"quality": "make lint", "test": "make test", "build": "make build"}),
]:
    example = json.loads(open(os.path.join(ROOT, "templates", "repo", ".factory", name), encoding="utf-8").read())
    code, _, o = run({DECL: example})
    check(f"the template's {name} resolves to its documented {want_stack} commands",
          code == 0 and o["stack"] == want_stack and all(o[k] == v for k, v in want.items()))

sys.exit(1 if failures else 0)
