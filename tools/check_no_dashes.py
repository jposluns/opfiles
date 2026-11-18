#!/usr/bin/env python3
"""Dashes gate: no en dash or em dash anywhere in the repository.

The writing style forbids both characters; hyphens, commas, colons,
semicolons and parentheses are the substitutes. Every file that decodes as
UTF-8 is scanned, whatever its suffix. This file names the two characters by
their code points, so it needs no exemption.

In a git checkout the gate scans the tracked files and the untracked files
that .gitignore does not exclude, so an ignored machine-local file is never
scanned; outside a git checkout it scans every file under the root.

Exit: 0 pass, 1 finding.
"""
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__"}
DASHES = ((chr(0x2013), "en dash"), (chr(0x2014), "em dash"))


def listed_paths():
    """Relative POSIX paths of the regular files to scan, sorted. In a git checkout: the tracked
    files and the untracked files that .gitignore does not exclude. Otherwise: every file under
    the root."""
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE")}
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, env=env, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0:
        names = {name for name in result.stdout.decode("utf-8", "surrogateescape").split("\0") if name}
    else:
        names = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")}
    return [name for name in sorted(names)
            if not any(part in SKIP_DIRS for part in PurePosixPath(name).parts) and (ROOT / name).is_file()]


def scan_text(rel, text):
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for char, label in DASHES:
            if char in line:
                findings.append(f"{rel}:{number}:{line.index(char) + 1}: {label}")
    return findings


def main():
    findings = []
    for rel in listed_paths():
        for char, label in DASHES:
            if char in rel:
                findings.append(f"{rel}: {label} in the path")
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(rel, text))
    if findings:
        print(f"FAIL: {len(findings)} en dash or em dash character(s)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("PASS: no en dash or em dash in the repository")
    return 0


if __name__ == "__main__":
    sys.exit(main())
