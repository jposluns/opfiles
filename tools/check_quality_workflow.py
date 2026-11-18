#!/usr/bin/env python3
"""Workflow contract gate for .github/workflows/quality.yml (the D-1245 job).

The file is read as text, with no YAML library, and any layout this gate does
not recognize fails. The contract:
  - the workflow name is Quality;
  - the only trigger is pull_request to main: no push, schedule or
    workflow_dispatch trigger, and no other event;
  - permissions are exactly contents: read;
  - there is exactly one job, named exactly "Quality gates", on ubuntu-24.04
    with timeout-minutes 5 and no job-level if:;
  - no step has an if:, no step has a key other than name, uses, with, env
    and run, and continue-on-error appears nowhere, so no step can turn the
    check green without running;
  - every uses: pins a full 40-hex commit SHA, so a moved tag cannot change
    the code the job runs;
  - the first step, and only that step, uses actions/checkout, and its with:
    block is exactly the pull request head SHA and persist-credentials false;
  - gitleaks is pinned to the version tools/check_secrets.sh requires, with a
    sha256 that one sha256sum -c line checks before tar extracts the archive;
  - the last step, and only that step, runs exactly
    bash tools/run_all_checks.sh --ci (the fast gates), with
    OPFILES_GATE_TIMEOUT "90" as its only environment setting;
  - nothing in the workflow reads a local-quality status: no local-quality
    publisher is deployed for this repository yet.

Exit: 0 pass, 1 contract violation, 2 a file cannot be read.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/quality.yml"
SECRETS_GATE = ROOT / "tools/check_secrets.sh"
KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ ]+(.*))?")
USES = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+@[0-9a-f]{40}")
STEP_KEYS = {"name", "uses", "with", "env", "run"}
CHECKOUT_WITH = ["ref: ${{ github.event.pull_request.head.sha }}", "persist-credentials: false"]
RUN_GATES = "bash tools/run_all_checks.sh --ci"
GATES_ENV = ['OPFILES_GATE_TIMEOUT: "90"']


def significant(lines):
    """The lines that are neither blank nor whole-line comments."""
    return [line for line in lines if line.strip() and not line.lstrip().startswith("#")]


def stripped(lines):
    """The significant lines, without their indentation."""
    return [line.strip() for line in significant(lines)]


def mapping(lines, indent):
    """Map each key at exactly `indent` spaces to (value, body lines). A
    significant line indented less, or a line at `indent` that is not a plain
    key, is refused."""
    found = {}
    key = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            if key is not None:
                found[key][1].append(line)
            continue
        width = len(line) - len(line.lstrip(" "))
        if width < indent or (width > indent and key is None):
            raise ValueError(f"unexpected indentation: {line.strip()!r}")
        if width == indent:
            match = KEY.fullmatch(line[indent:].rstrip())
            if not match:
                raise ValueError(f"not a plain mapping key: {line.strip()!r}")
            key = match[1]
            if key in found:
                raise ValueError(f"duplicate key {key}")
            value = re.sub(r"\s+#.*$", "", match[2] or "").strip()
            found[key] = (value, [])
        else:
            found[key][1].append(line)
    return found


def steps(lines):
    """One mapping per item of a job's steps: list. Each item starts with "      - "; its first key
    is moved to 8 spaces, the indentation of the item's other keys."""
    items = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            if items:
                items[-1].append(line)
            continue
        if line.startswith("      - "):
            items.append([" " * 8 + line[8:]])
        elif line.startswith(" " * 8) and items:
            items[-1].append(line)
        else:
            raise ValueError(f"not a step list item: {line.strip()!r}")
    return [mapping(item, 8) for item in items]


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def check_steps(job_id, body, errors):
    items = steps(body)
    if not items:
        errors.append(f"job {job_id} has no steps")
        return
    for number, step in enumerate(items, 1):
        label = f"job {job_id} step {number}"
        if "if" in step:
            errors.append(f"{label} must have no if:")
        unexpected = sorted(set(step) - STEP_KEYS)
        if unexpected:
            errors.append(f"{label} has keys other than name, uses, with, env and run ({', '.join(unexpected)})")
        if "uses" in step and not USES.fullmatch(step["uses"][0]):
            errors.append(f"{label} must pin uses: to a full 40-hex commit SHA (found {step['uses'][0]})")
    checkouts = [step for step in items if step.get("uses", ("", []))[0].startswith("actions/checkout@")]
    if len(checkouts) != 1 or items[0] is not checkouts[0]:
        errors.append("the first step, and only that step, must use actions/checkout")
    elif "with" not in checkouts[0] or checkouts[0]["with"][0] or stripped(checkouts[0]["with"][1]) != CHECKOUT_WITH:
        errors.append("the checkout step's with: must be exactly the pull request head SHA (ref) and "
                      "persist-credentials: false")
    gates = [step for step in items if unquote(step.get("run", ("", []))[0]) == RUN_GATES]
    if len(gates) != 1 or items[-1] is not gates[0]:
        errors.append(f"the last step, and only that step, must run exactly: {RUN_GATES}")
    elif "env" not in gates[0] or gates[0]["env"][0] or stripped(gates[0]["env"][1]) != GATES_ENV:
        errors.append(f"the gates step's env: must be exactly {GATES_ENV[0]}")
    installs = [step for step in items
                if any(line.startswith("GITLEAKS_VERSION:") for line in stripped(step.get("env", ("", []))[1]))]
    if len(installs) != 1:
        errors.append("exactly one step must install gitleaks (env: GITLEAKS_VERSION)")
    else:
        script = stripped(installs[0].get("run", ("", []))[1])
        verify = [index for index, line in enumerate(script) if "sha256sum -c" in line]
        extract = [index for index, line in enumerate(script) if line.startswith("tar ")]
        if len(verify) != 1 or not extract or min(extract) < verify[0]:
            errors.append("the gitleaks step must check the archive with one sha256sum -c line before tar extracts it")


def check(text, pinned):
    errors = []
    if "\t" in text:
        errors.append("the workflow holds a tab character")
    if "continue-on-error" in text:
        errors.append("the workflow must not use continue-on-error")
    top = mapping(text.splitlines(), 0)
    if list(top) != ["name", "on", "permissions", "jobs"]:
        errors.append("the top-level keys must be exactly name, on, permissions and jobs, in that order "
                      f"(found: {', '.join(top)})")
    if unquote(top.get("name", ("", []))[0]) != "Quality":
        errors.append("the workflow name must be Quality")
    on_value, on_body = top.get("on", ("missing", []))
    if on_value or significant(on_body) != ["  pull_request:", "    branches: [main]"]:
        errors.append("the only trigger must be pull_request to main (no push, schedule, "
                      "workflow_dispatch or other event)")
    perm_value, perm_body = top.get("permissions", ("missing", []))
    if perm_value or significant(perm_body) != ["  contents: read"]:
        errors.append("permissions must be exactly contents: read")
    jobs = mapping(top.get("jobs", ("", []))[1], 2)
    if len(jobs) != 1:
        errors.append(f"there must be exactly one job (found {len(jobs)})")
    for job_id, (job_value, job_body) in jobs.items():
        if job_value:
            errors.append(f"job {job_id} must be a block mapping")
            continue
        keys = mapping(job_body, 4)
        if "if" in keys:
            errors.append(f"job {job_id} must have no job-level if:")
        if set(keys) != {"name", "runs-on", "timeout-minutes", "steps"}:
            errors.append(f"job {job_id} keys must be exactly name, runs-on, timeout-minutes and steps "
                          f"(found: {', '.join(keys)})")
        if unquote(keys.get("name", ("", []))[0]) != "Quality gates":
            errors.append(f'job {job_id} must be named exactly "Quality gates"')
        if keys.get("runs-on", ("", []))[0] != "ubuntu-24.04":
            errors.append(f"job {job_id} must run on ubuntu-24.04")
        if keys.get("timeout-minutes", ("", []))[0] != "5":
            errors.append(f"job {job_id} must set timeout-minutes 5")
        if "steps" in keys:
            if keys["steps"][0]:
                errors.append(f"job {job_id} steps must be a block list")
            else:
                check_steps(job_id, keys["steps"][1], errors)
    lines = [line.strip() for line in text.splitlines()]
    for required in CHECKOUT_WITH:
        if lines.count(required) != 1:
            errors.append(f"the checkout must set exactly one {required.split(':')[0]}: line ({required})")
    if lines.count(f"GITLEAKS_VERSION: {pinned}") != 1:
        errors.append(f"GITLEAKS_VERSION must be {pinned}, the version tools/check_secrets.sh requires")
    if sum(1 for line in lines if re.fullmatch(r"GITLEAKS_SHA256: [0-9a-f]{64}", line)) != 1:
        errors.append("GITLEAKS_SHA256 must be one 64-hex-digit sha256")
    if "local-quality" in text.lower():
        errors.append("the workflow must not read a local-quality status; no publisher is deployed")
    return errors


def main():
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
        gate = SECRETS_GATE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"CANNOT-EVALUATE: {exc}")
        return 2
    pins = re.findall(r"^PINNED=([0-9]+\.[0-9]+\.[0-9]+)$", gate, re.MULTILINE)
    if len(pins) != 1:
        print("FAIL: tools/check_secrets.sh must set exactly one PINNED=major.minor.micro line")
        return 1
    try:
        errors = check(text, pins[0])
    except ValueError as exc:
        errors = [f"unrecognized layout: {exc}"]
    if errors:
        print(f"FAIL: {WORKFLOW.relative_to(ROOT)} breaks its contract")
        for error in errors:
            print(f"  {error}")
        return 1
    print("PASS: the Quality workflow keeps its contract (one job, \"Quality gates\", pull_request to main only, "
          "the fast gates in --ci mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
