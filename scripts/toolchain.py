#!/usr/bin/env python3
"""Resolves a repo's toolchain for loop-ci: its stack, the runners its tests run on, and its check commands.

The declaration is `.factory/toolchain.json`; without one the stack is inferred from the repo's files. A caller's
loop-ci inputs (QUALITY_SCRIPTS, TEST_COMMAND, BUILD_COMMAND in the environment) override the declaration, and the
declaration overrides the stack's defaults. Writes the result to $GITHUB_OUTPUT (stdout when it is unset); exits 1
with an ::error line when the declaration is invalid.

Usage: toolchain.py [repo dir]
"""
import json
import os
import re
import shlex
import sys
import uuid

DECLARATION = os.path.join(".factory", "toolchain.json")
DEFAULT_OS = ["ubuntu-latest"]
MAX_OS = 8
RUNNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# quality_scripts names package.json scripts that run only when defined; quality lists commands that always run.
PROFILES = {
    "bun": {"quality_scripts": ["format:check", "lint", "typecheck"], "test": "bun test --pass-with-no-tests",
            "build": ""},
    "go": {"quality": ["make lint"], "test": "make test", "build": "make build"},
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


def command(value, where):
    if not isinstance(value, str) or "\n" in value or "\r" in value:
        raise Invalid(f"{where} must be a one-line command string")
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

    names = env.get("QUALITY_SCRIPTS", "").split()
    if names and stack != "bun":
        raise Invalid(f"quality_scripts names package.json scripts, which the {stack} stack has none of; "
                      f"set checks.quality in {DECLARATION} instead")
    if names or ("quality" not in checks and "quality_scripts" in profile):
        quality = []
        for name in names or profile["quality_scripts"]:
            if scripts and name in scripts:
                quality.append(f"bun run {shlex.quote(name)}")
            elif scripts is not None:
                notices.append(f"Script {name} not defined, skipped.")
    else:
        quality = checks.get("quality", profile.get("quality", []))

    def pick(key, env_name):
        given = command(env.get(env_name, ""), f"the {env_name.lower()} input")
        if given:
            return given
        if key in checks:
            return checks[key]
        return "" if stack == "bun" and scripts is None else profile[key]

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
        f"quality<<{delim}\n" + "".join(f"{c}\n" for c in resolved["quality"]) + f"{delim}\n",
        f"test={resolved['test']}\n",
        f"build={resolved['build']}\n",
    ])


def main(argv, env):
    repo = argv[1] if len(argv) > 1 else "."
    try:
        resolved = resolve(repo, env)
    except Invalid as err:
        where = f" file={err.file}" if err.file else ""
        print(f"::error{where}::{annotation(str(err))}")
        return 1
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
