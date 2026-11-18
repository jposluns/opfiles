#!/usr/bin/env python3
"""Links gate: every repository-internal Markdown link resolves to an existing path
inside the repository.

Only relative links are checked. External URLs, mailto and tel links, and pure
anchors are out of scope: this gate answers "does the path exist", not "is the
URL live". Inline code spans are removed before links are read, so path-like
or regex text inside backticks is never taken for a link, and every remaining
link target is resolved whatever characters its file name holds. A target that
resolves outside the repository (through "..", or an absolute path) is a
finding even when it exists, because it is not an internal link.

In a git checkout the gate reads the tracked Markdown files and the untracked
ones that .gitignore does not exclude, so an ignored machine-local file is
never read; outside a git checkout it reads every Markdown file under the root.

Exit: 0 pass, 1 finding.
"""
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {".git", "__pycache__"}
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "#")


def listed_paths():
    """Relative POSIX paths of the regular files to read, sorted. In a git checkout: the tracked
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


def strip_code_spans(line):
    """Replace inline code spans with spaces. A span opens with a run of N
    backticks and closes with the next run of exactly N backticks; a backtick
    escaped with a backslash is literal. A run with no closer of the same
    length opens no span, so a real link after a lone backtick is still read."""
    runs = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            runs.append((i, j - i))
            i = j
            continue
        i += 1
    out = list(line)
    k = 0
    while k < len(runs):
        start, length = runs[k]
        m = k + 1
        while m < len(runs) and runs[m][1] != length:
            m += 1
        if m < len(runs):
            close_start, close_length = runs[m]
            for p in range(start, close_start + close_length):
                out[p] = " "
            k = m + 1
        else:
            k += 1
    return "".join(out)


def broken_links(text, base):
    """Yield (line number, target, reason) for each internal link that resolves outside the
    repository or to no existing path."""
    for number, line in enumerate(text.splitlines(), 1):
        for raw in LINK.findall(strip_code_spans(line)):
            parts = raw.split()
            target = parts[0].strip() if parts else ""
            if not target or target.startswith(EXTERNAL):
                continue
            path_part = unquote(target.split("#", 1)[0])
            if not path_part:
                continue
            resolved = (base / path_part).resolve()
            if resolved != ROOT and ROOT not in resolved.parents:
                yield number, target, "link outside the repository"
            elif not resolved.exists():
                yield number, target, "broken link"


def main():
    findings = []
    for rel in listed_paths():
        if not rel.endswith(".md"):
            continue
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            findings.append(f"{rel}: cannot read as UTF-8 ({exc.__class__.__name__})")
            continue
        for number, target, reason in broken_links(text, path.parent):
            findings.append(f"{rel}:{number}: {reason} -> {target}")
    if findings:
        print(f"FAIL: {len(findings)} broken or external-path internal link(s)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("PASS: all internal Markdown links resolve inside the repository")
    return 0


if __name__ == "__main__":
    sys.exit(main())
