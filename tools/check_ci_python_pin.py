#!/usr/bin/env python3
"""CI Python pin gate.

.github/ci-python-version is the one committed source of the CI Python
version: exactly one major.minor.micro line. The project's floor is that
version's major.minor.
  - The workflow must set up Python once, from that file
    (python-version-file: .github/ci-python-version), with no literal
    python-version pin, and verify the interpreter in a "Verify CI Python" step.
  - In CI (GITHUB_ACTIONS=true) the running interpreter must equal the pin.
  - In a local run it must be at least the floor.
This is a text check of quality.yml that guards against accidental drift; it
does not decode every YAML encoding.

Exit: 0 pass, 1 finding, 2 a file cannot be read.
"""
import os
import platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/quality.yml"
PIN_FILE = ROOT / ".github/ci-python-version"


def main():
    try:
        pin_text = PIN_FILE.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"CANNOT-EVALUATE: {exc}")
        return 2
    errors = []
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)\n", pin_text)
    if not match:
        print("FAIL: .github/ci-python-version must hold exactly one major.minor.micro line")
        return 1
    pin = pin_text.rstrip("\n")
    floor = (int(match[1]), int(match[2]))
    lines = [line.strip() for line in workflow.splitlines()]
    if workflow.lower().count("actions/setup-python") != 1:
        errors.append("the workflow must name actions/setup-python exactly once")
    if lines.count("python-version-file: .github/ci-python-version") != 1:
        errors.append("the setup step must read python-version-file: .github/ci-python-version")
    if any(re.match(r"python-version\s*:", line) for line in lines):
        errors.append("the workflow must not pin a literal python-version; the file is the one source")
    if lines.count("- name: Verify CI Python") != 1:
        errors.append('the workflow must have one "Verify CI Python" step')
    running = platform.python_version()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if running != pin:
            errors.append(f"CI runs Python {running}, not the pinned {pin}")
    elif sys.version_info[:2] < floor:
        errors.append(f"local Python {running} is below the floor {floor[0]}.{floor[1]}")
    if errors:
        print("FAIL: CI Python pin")
        for error in errors:
            print(f"  {error}")
        return 1
    where = "CI" if os.environ.get("GITHUB_ACTIONS") == "true" else "local"
    print(f"PASS: CI Python pin {pin} is read from .github/ci-python-version; "
          f"{where} Python {running} meets it (floor {floor[0]}.{floor[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
