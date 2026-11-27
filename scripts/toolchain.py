#!/usr/bin/env python3
"""Resolves a repo's toolchain for loop-ci: its stack, the runners its tests run on, and its check commands.

The declaration is `.factory/toolchain.json`; without one the stack is inferred from the repo's files. A caller's
loop-ci inputs (QUALITY_SCRIPTS, TEST_COMMAND, BUILD_COMMAND in the environment) override the declaration, and the
declaration overrides the stack's defaults. Writes the result to $GITHUB_OUTPUT (stdout when it is unset); exits 1
with an ::error line when the declaration is invalid (in --describe mode the message is plain, for the review
prompt).

Usage: toolchain.py [--describe] [repo dir]
"""
import json
import os
import re
import shlex
import sys
import uuid

DECLARATION = os.path.join(".factory", "toolchain.json")
# The loop-ci inputs' default: not set by the caller, so the declaration and the stack's defaults decide. An input
# set to "" skips that check, as it did before the resolver existed. The value matches the defaults in loop-ci.yml.
INPUT_DEFAULT = "toolchain-default"
DEFAULT_OS = ["ubuntu-latest"]
MAX_OS = 8
RUNNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# quality_scripts names package.json scripts that run only when defined; quality lists commands that always run.
PROFILES = {
    "bun": {"quality_scripts": ["format:check", "lint", "typecheck"], "test": "bun test --pass-with-no-tests",
            "build": ""},
    "go": {"quality": ["make lint"], "test": "make test", "build": "make build"},
    "assets": {"quality": ["bash scripts/optimize-svgs.sh", "git diff --exit-code", "bash scripts/check-lfs.sh"],
                "test": "", "build": ""},
    "none": {"quality": [], "test": "", "build": ""},
}
STACKS = tuple(PROFILES)
TOP_KEYS = ("stack", "os", "checks")
CHECK_KEYS = ("quality", "test", "build")


class Invalid(Exception):
    """The declaration, package.json or an input cannot be used; the message says what to change."""

    def __init__(self, message, file=None):
        super().__init__(message)
        self.file = file


def infer_stack(repo):
    if any(os.path.isfile(os.path.join(repo, name)) for name in ("bun.lock", "bun.lockb", "package.json")):
        return "bun"
    if os.path.isfile(os.path.join(repo, "go.mod")):
        return "go"
    return "none"


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as err:
        raise Invalid(f"cannot read it as JSON: {err}") from None


def command(value, where, multiline=False):
    bad = "\r" in value if isinstance(value, str) else True
    if bad or (not multiline and "\n" in value):
        shape = "a command string" if multiline else "a one-line command string"
        raise Invalid(f"{where} must be {shape}")
    return value.strip()


def load_declaration(repo):
    """The validated declaration, or {} when the repo has none."""
    path = os.path.join(repo, DECLARATION)
    if not os.path.exists(path):
        return {}
    try:
        return validate(read_json(path))
    except Invalid as err:
        raise Invalid(str(err), DECLARATION) from None


def validate(decl):
    if not isinstance(decl, dict):
        raise Invalid("the declaration must be a JSON object")
    unknown = sorted(set(decl) - set(TOP_KEYS))
    if unknown:
        raise Invalid(f"unknown keys {unknown}; allowed: {list(TOP_KEYS)}")
    if "stack" in decl and decl["stack"] not in STACKS:
        raise Invalid(f"stack must be one of {list(STACKS)}, not {decl['stack']!r}")
    if "os" in decl:
        runners = decl["os"]
        if not isinstance(runners, list) or not 1 <= len(runners) <= MAX_OS:
            raise Invalid(f"os must be a list of 1 to {MAX_OS} runner labels")
        if not all(isinstance(r, str) and RUNNER.fullmatch(r) for r in runners) or len(set(runners)) != len(runners):
            raise Invalid("os entries must be distinct runner labels such as ubuntu-latest")
    checks = decl.get("checks", {})
    if not isinstance(checks, dict):
        raise Invalid("checks must be an object")
    unknown = sorted(set(checks) - set(CHECK_KEYS))
    if unknown:
        raise Invalid(f"unknown checks {unknown}; allowed: {list(CHECK_KEYS)}")
    if "quality" in checks:
        if not isinstance(checks["quality"], list):
            raise Invalid("checks.quality must be a list of commands")
        checks["quality"] = [command(c, "each checks.quality entry") for c in checks["quality"]]
        if not all(checks["quality"]):
            raise Invalid("checks.quality entries must not be empty")
    for key in ("test", "build"):
        if key in checks:
            checks[key] = command(checks[key], f"checks.{key}")
    return decl


def package_scripts(repo):
    """The scripts package.json defines, or None when there is no package.json."""
    path = os.path.join(repo, "package.json")
    if not os.path.isfile(path):
        return None
    try:
        data = read_json(path)
    except Invalid as err:
        raise Invalid(str(err), "package.json") from None
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return scripts if isinstance(scripts, dict) else {}


def resolve(repo, env):
    """The resolved toolchain: stack, os, quality commands, test and build commands, and notices to print."""
    decl = load_declaration(repo)
    stack = decl.get("stack") or infer_stack(repo)
    profile, checks, notices = PROFILES[stack], decl.get("checks", {}), []
    scripts = package_scripts(repo) if stack == "bun" else None
    if stack == "bun" and scripts is None:
        notices.append("No package.json, so no package scripts or default tests to run.")

    scripts_input = env.get("QUALITY_SCRIPTS", INPUT_DEFAULT)
    if scripts_input not in (INPUT_DEFAULT, "") and stack != "bun":
        raise Invalid(f"quality_scripts names package.json scripts, which the {stack} stack has none of; "
                      f"set checks.quality in {DECLARATION} instead")
    if scripts_input == "":
        quality = []  # an explicit empty quality_scripts runs no quality checks, as before the resolver
    elif scripts_input != INPUT_DEFAULT or ("quality" not in checks and "quality_scripts" in profile):
        quality = []
        names = scripts_input.split() if scripts_input != INPUT_DEFAULT else profile["quality_scripts"]
        for name in names:
            if scripts and name in scripts:
                quality.append(f"bun run {shlex.quote(name)}")
            elif scripts is not None:
                notices.append(f"Script {name} not defined, skipped.")
    else:
        quality = checks.get("quality", profile.get("quality", []))

    def pick(key, env_name):
        raw = env.get(env_name, INPUT_DEFAULT)
        if raw == INPUT_DEFAULT:
            if key in checks:
                return checks[key]
            return "" if stack == "bun" and scripts is None else profile[key]
        # An input the caller sets wins, multiline commands included; set to "" it skips the check, as before.
        return command(raw, f"the {env_name.lower()} input", multiline=True)

    test, build = pick("test", "TEST_COMMAND"), pick("build", "BUILD_COMMAND")
    if not quality and not test and not build:
        notices.append(f"Stack {stack}: nothing to check.")
    elif not test:
        notices.append("No test command, tests skipped.")
    return {"stack": stack, "os": decl.get("os", DEFAULT_OS), "quality": quality, "test": test, "build": build,
            "notices": notices}


def annotation(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def outputs(resolved):
    """The resolved toolchain as $GITHUB_OUTPUT lines."""
    delim = f"EOF_{uuid.uuid4().hex}"
    return "".join([
        f"stack={resolved['stack']}\n",
        f"os={json.dumps(resolved['os'])}\n",
        f"multi_os={'true' if len(resolved['os']) > 1 else 'false'}\n",
        block("quality", "\n".join(resolved["quality"]), delim),
        block("test", resolved["test"], f"{delim}_T"),
        block("build", resolved["build"], f"{delim}_B"),
    ])


def block(name, value, delim):
    return f"{name}<<{delim}\n{value}\n{delim}\n" if value else f"{name}=\n"


def describe(resolved):
    """The resolved toolchain as a readable summary, for the review prompt."""
    lines = [f"Stack: {resolved['stack']}. Test runners: {', '.join(resolved['os'])}."]
    for name in ("quality", "test", "build"):
        value = "\n".join(resolved[name]) if name == "quality" else resolved[name]
        lines.append(f"{name}: {value if value else '(none)'}")
    return "\n".join(lines)


def main(argv, env):
    describe_mode = len(argv) > 1 and argv[1] == "--describe"
    repo = argv[2] if describe_mode and len(argv) > 2 else (argv[1] if len(argv) > 1 and not describe_mode else ".")
    try:
        resolved = resolve(repo, env)
    except Invalid as err:
        if describe_mode:
            print(str(err))
            return 1
        where = f" file={err.file}" if err.file else ""
        print(f"::error{where}::{annotation(str(err))}")
        return 1
    if describe_mode:
        print(describe(resolved))
        return 0
    for notice in resolved["notices"]:
        print(f"::notice::{annotation(notice)}")
    print(f"stack {resolved['stack']}, tests on {', '.join(resolved['os'])}")
    out = outputs(resolved)
    path = env.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv, os.environ))
