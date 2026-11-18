#!/usr/bin/env python3
"""Offline tests for the six gates of tools/run_all_checks.sh.

Each case copies the gate into a fresh fixture tree, so the gate's ROOT is that
tree, and runs it on good input (exit 0) or on bad input (exit 1, or 2 where
the gate cannot evaluate). Each bad input is one change to good input, so each
case shows one defence firing. The workflow-contract and CI Python pin cases
start from this repository's own .github/workflows/quality.yml. The secrets
cases use a fake gitleaks on a PATH that holds only the tools the gate needs.
The git cases build a throwaway git repository inside the fixture tree. The
names gate's masking and its shortcuts are also tested in process, on a copy
of the gate in a fixture tree loaded with importlib; its time budget for
matching one file is tested on a fixture copy whose budget is shortened. The
fail-closed branches of its matching worker are tested in process with a fake
worker, a worker that fails at its start is tested in process for printing
nothing, and SIGTERM sent to the gate is tested for stopping the worker (where
/proc lists processes). One case checks that every file a comment of this file
names is in the repository. No network is used.

Exit: 0 every case passed, 1 a case failed.
"""
import importlib.util
import io
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tokenize
import types
from pathlib import Path, PurePosixPath

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
WORKFLOW_TEXT = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
CLEARED = ("GITHUB_ACTIONS", "OPFILES_NAMES_DENYLIST", "GIT_DIR", "GIT_WORK_TREE", "BASH_ENV")
# The two dash characters by code point, so this file holds neither for the real dashes gate to find.
EN_DASH = chr(0x2013)
EM_DASH = chr(0x2014)
RESULTS = []
SCRATCH = None
COUNTER = [0]


def record(ok, label, detail=""):
    RESULTS.append(ok)
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}" + ("" if ok else f" ({detail})"))


def base_env(**overrides):
    env = {key: value for key, value in os.environ.items() if key not in CLEARED}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # A fixture that is not itself a git repository must never be read through an outer one.
    env["GIT_CEILING_DIRECTORIES"] = str(SCRATCH)
    # An empty home, so no case reads the account's own files, such as the names gate's default
    # denylist ~/.config/protected-terms/terms.regex.
    env["HOME"] = str(SCRATCH / "home")
    env.update(overrides)
    return env


class Fixture:
    def __init__(self, *gates):
        COUNTER[0] += 1
        self.root = SCRATCH / f"fixture{COUNTER[0]}"
        (self.root / "tools").mkdir(parents=True)
        for gate in gates:
            shutil.copy2(TOOLS / gate, self.root / "tools" / gate)

    def write(self, rel, text):
        """Write text as UTF-8, or bytes as they are."""
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, env=base_env(), check=True,
                       capture_output=True, timeout=60)

    def run(self, gate, *args, env=None):
        command = [sys.executable, "-I", "-B"] if gate.endswith(".py") else ["bash"]
        command += [str(self.root / "tools" / gate), *args]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120,
                                env=env if env is not None else base_env(), cwd=self.root)
        return result.returncode, result.stdout + result.stderr


def expect(label, outcome, want, contains=(), lacks=()):
    rc, out = outcome
    problems = []
    if rc != want:
        problems.append(f"want exit {want}, got {rc}")
    problems += [f"missing {text!r}" for text in contains if text not in out]
    problems += [f"unexpected {text!r}" for text in lacks if text.lower() in out.lower()]
    record(not problems, label, "; ".join(problems) + f"; output: {out.strip()[:600]!r}")


def mutate(text, old, new):
    """Replace the one occurrence of old; a mutation that does not apply fails the case."""
    if text.count(old) != 1:
        raise AssertionError(f"mutation target found {text.count(old)} times: {old!r}")
    return text.replace(old, new)


def workflow_fixture(workflow_text, pin=None):
    fixture = Fixture("check_quality_workflow.py", "check_ci_python_pin.py", "check_secrets.sh")
    fixture.write(".github/workflows/quality.yml", workflow_text)
    version = sys.version_info
    fixture.write(".github/ci-python-version", pin or f"{version.major}.{version.minor}.{version.micro}\n")
    return fixture


def test_workflow_contract():
    print("== workflow-contract (tools/check_quality_workflow.py) ==")
    expect("this repository's workflow keeps the contract",
           workflow_fixture(WORKFLOW_TEXT).run("check_quality_workflow.py"), 0)
    sha_line = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2"
    ref_line = "          ref: ${{ github.event.pull_request.head.sha }}\n"
    cases = [
        ("a push trigger", "    branches: [main]\n", "    branches: [main]\n  push:\n    branches: [main]\n"),
        ("a workflow_dispatch trigger", "    branches: [main]\n", "    branches: [main]\n  workflow_dispatch:\n"),
        ("contents: write", "  contents: read\n", "  contents: write\n"),
        ("a second job", "        run: bash tools/run_all_checks.sh --ci\n",
         "        run: bash tools/run_all_checks.sh --ci\n  other:\n    name: Other\n    runs-on: ubuntu-24.04\n"
         "    timeout-minutes: 5\n    steps:\n      - run: 'true'\n"),
        ("a job-level if:", "    name: Quality gates\n", "    name: Quality gates\n    if: false\n"),
        ("a renamed job", "    name: Quality gates\n", "    name: Quality checks\n"),
        ("timeout-minutes 10", "    timeout-minutes: 5\n", "    timeout-minutes: 10\n"),
        ("a step-level if:", "      - name: Fast gates\n", "      - name: Fast gates\n        if: false\n"),
        ("continue-on-error on the gates step", "      - name: Fast gates\n",
         "      - name: Fast gates\n        continue-on-error: true\n"),
        ("the gates step without --ci", "run: bash tools/run_all_checks.sh --ci", "run: bash tools/run_all_checks.sh"),
        ("no gates step", "run: bash tools/run_all_checks.sh --ci", "run: echo skipped"),
        ("another gate timeout", 'OPFILES_GATE_TIMEOUT: "90"', 'OPFILES_GATE_TIMEOUT: "300"'),
        ("an extra variable on the gates step", 'OPFILES_GATE_TIMEOUT: "90"\n',
         'OPFILES_GATE_TIMEOUT: "90"\n          OPFILES_CHECK_JOBS: "1"\n'),
        ("a checkout pinned to a moving tag", sha_line, "actions/checkout@v4"),
        ("setup-python pinned to a moving tag",
         "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0", "actions/setup-python@v5"),
        ("persist-credentials true", "persist-credentials: false", "persist-credentials: true"),
        ("the head SHA moved out of the checkout step", ref_line + "          persist-credentials: false\n",
         "          persist-credentials: false\n"),
        ("no sha256sum -c before extraction",
         '          echo "${GITLEAKS_SHA256}  $dest/gitleaks.tar.gz" | sha256sum -c -\n', ""),
        ("another gitleaks version", "GITLEAKS_VERSION: 8.30.1", "GITLEAKS_VERSION: 8.30.0"),
        ("a local-quality read", "      - name: Fast gates\n",
         "      - name: Read local-quality\n        run: echo local-quality\n\n      - name: Fast gates\n"),
    ]
    for label, old, new in cases:
        text = mutate(WORKFLOW_TEXT, old, new)
        if label == "the head SHA moved out of the checkout step":
            text = mutate(text, "          python-version-file: .github/ci-python-version\n",
                          "          python-version-file: .github/ci-python-version\n" + ref_line)
        expect(f"refused: {label}", workflow_fixture(text).run("check_quality_workflow.py"), 1,
               contains=["FAIL: .github/workflows/quality.yml breaks its contract"])


def test_ci_python_pin():
    print("== ci-python-pin (tools/check_ci_python_pin.py) ==")
    version = sys.version_info
    expect("a pin this interpreter meets passes locally",
           workflow_fixture(WORKFLOW_TEXT).run("check_ci_python_pin.py"), 0)
    expect("refused: a malformed pin", workflow_fixture(WORKFLOW_TEXT, "3.14\n").run("check_ci_python_pin.py"), 1)
    expect("refused: a local interpreter below the floor",
           workflow_fixture(WORKFLOW_TEXT, f"{version.major}.{version.minor + 1}.0\n").run("check_ci_python_pin.py"), 1)
    other = f"{version.major}.{version.minor}.{version.micro + 1}\n"
    expect("refused in CI: an interpreter that is not the pin",
           workflow_fixture(WORKFLOW_TEXT, other).run("check_ci_python_pin.py", env=base_env(GITHUB_ACTIONS="true")), 1)
    literal = mutate(WORKFLOW_TEXT, "          python-version-file: .github/ci-python-version\n",
                     "          python-version-file: .github/ci-python-version\n          python-version: '3.14'\n")
    expect("refused: a literal python-version pin", workflow_fixture(literal).run("check_ci_python_pin.py"), 1)


def test_names():
    print("== names (tools/check_names.py) ==")
    denylist = SCRATCH / "denylist.txt"
    denylist.write_text("# synthetic test entry\nFixturecorp\n", encoding="utf-8")
    with_list = base_env(OPFILES_NAMES_DENYLIST=str(denylist))

    def tree():
        fixture = Fixture("check_names.py")
        fixture.write("README.md", "Plain text with no name in it.\n")
        return fixture

    expect("a clean tree passes with the denylist", tree().run("check_names.py", env=with_list), 0,
           contains=["PASS: no denylist match"])
    fixture = tree()
    fixture.write("notes.md", "Built at fixturecorp last year.\n")
    expect("refused: a denylist name in a file, and the name is not printed",
           fixture.run("check_names.py", env=with_list), 1, contains=["notes.md:1: denylist entry 1"],
           lacks=["fixturecorp"])
    fixture = tree()
    fixture.write("docs/fixturecorp-plan.md", "Plain text.\n")
    expect("refused: a denylist name in a path, its whole path component printed masked",
           fixture.run("check_names.py", env=with_list), 1,
           contains=["docs/" + "*" * len("fixturecorp-plan.md") + ": path matches denylist entry 1"],
           lacks=["fixturecorp", "plan"])
    expect("cannot evaluate: no denylist in a local run", tree().run("check_names.py"), 2)
    expect("cannot evaluate: GITHUB_ACTIONS=true does not select CI mode",
           tree().run("check_names.py", env=base_env(GITHUB_ACTIONS="true")), 2)
    fixture = tree()
    inside = fixture.write("private/denylist.txt", "Fixturecorp\n")
    # The denylist inside the repository is not read, so it cannot mask; every component is masked.
    fixture.write("docs/fixturecorp-plan.md", "Write to someone" + chr(64) + "mailfixture.net.\n")
    expect("cannot evaluate: a denylist inside the repository, every component of a printed path masked",
           fixture.run("check_names.py", env=base_env(OPFILES_NAMES_DENYLIST=str(inside))), 2,
           contains=["inside the repository", "****/" + "*" * len("fixturecorp-plan.md") + ":1: email address"],
           lacks=["fixturecorp", "plan"])
    expect("--ci runs the checks that need no denylist and says so", tree().run("check_names.py", "--ci"), 0,
           contains=["CI mode (--ci)"])
    # The address and the path are assembled here, so this file holds neither for the real gate to find.
    fixture = tree()
    fixture.write("contact.md", "Write to someone" + chr(64) + "mailfixture.net for access.\n")
    expect("refused in --ci mode: an email address", fixture.run("check_names.py", "--ci"), 1,
           contains=["contact.md:1: email address"])
    fixture = tree()
    fixture.write("paths.md", "The file lives in /" + "home/someone/notes.\n")
    expect("refused: a home-directory path", fixture.run("check_names.py", "--ci"), 1,
           contains=["paths.md:1: home-directory path"])
    # Addresses at names RFC 2606 and RFC 6761 reserve for documentation and testing cannot name a
    # real account, so they are allowed in every file; each address is assembled here, so this file
    # holds none for the real gate to find.
    fixture = tree()
    fixture.write("reserved.md", "Ask someone" + chr(64) + "example.org, someone" + chr(64)
                  + "sub.example.com, someone" + chr(64) + "EXAMPLE.NET, someone" + chr(64)
                  + "demo.test, someone" + chr(64) + "a.b.invalid, someone" + chr(64)
                  + "host.localhost, or someone" + chr(64) + "svc.example.\n")
    expect("an address at a reserved name, or a subdomain of one, is allowed in any file",
           fixture.run("check_names.py", "--ci"), 0,
           contains=["PASS: no email address or home-directory path"])
    fixture = tree()
    fixture.write("lookalike.md", "Ask someone" + chr(64) + "notexample.org or someone"
                  + chr(64) + "example.org.somewhere.net.\n")
    expect("refused: a lookalike of a reserved name is not reserved",
           fixture.run("check_names.py", "--ci"), 1,
           contains=["lookalike.md:1: email address"])
    # The email check's path exceptions: the vendored tree, the site's security contact file and
    # the three imported tools with synthetic fixture addresses; the same address anywhere else is
    # still refused, and the home-directory check has no exception.
    address = "someone" + chr(64) + "mailfixture.net"
    fixture = tree()
    for rel in ("tools/_vendor/upstream/AUTHORS", "site/.well-known/security.txt",
                "tools/_opf_check.py", "tools/_opf_views.py", "tools/check_opf_homes.py"):
        fixture.write(rel, "Contact: " + address + "\n")
    expect("the exempt paths may carry a non-reserved address",
           fixture.run("check_names.py", "--ci"), 0,
           contains=["PASS: no email address or home-directory path"])
    fixture = tree()
    fixture.write("site/.well-known/other.txt", "Contact: " + address + "\n")
    expect("refused: a non-reserved address beside the exempt security contact file",
           fixture.run("check_names.py", "--ci"), 1,
           contains=["site/.well-known/other.txt:1: email address"])
    fixture = tree()
    fixture.write("tools/_vendorx/AUTHORS", "Contact: " + address + "\n")
    expect("refused: the tools/_vendor/ prefix does not cover a sibling such as tools/_vendorx/",
           fixture.run("check_names.py", "--ci"), 1,
           contains=["tools/_vendorx/AUTHORS:1: email address"])
    fixture = tree()
    fixture.write("tools/_opf_check.py", "# The file lives in /" + "home/someone/notes.\n")
    expect("refused: a home-directory path in an email-exempt file",
           fixture.run("check_names.py", "--ci"), 1,
           contains=["tools/_opf_check.py:1: home-directory path"])
    expect("refused: an unknown argument", tree().run("check_names.py", "--bogus"), 2)
    fixture = tree()
    fixture.write(".gitignore", "local-notes.md\n")
    fixture.write("local-notes.md", "Built at fixturecorp.\n")
    fixture.git("init", "-q")
    fixture.git("add", "README.md", ".gitignore", "tools/check_names.py")
    expect("an ignored file is not read in a git checkout", fixture.run("check_names.py", env=with_list), 0)
    fixture.write("untracked.md", "Built at fixturecorp.\n")
    expect("refused: an untracked file that is not ignored", fixture.run("check_names.py", env=with_list), 1,
           contains=["untracked.md:1: denylist entry 1"])


# Synthetic protected-terms entries, one POSIX ERE per line, in the format of the fleet pre-push hook.
ERE_DENYLIST = (
    "# synthetic ERE entries for the names gate tests\n"
    "fixturecorp[[:digit:]]{2}([^[:alnum:]]|$)\n"
    "(samplecorp|demoorg)-ops\n"
    "[/:][A-Za-z0-9][A-Za-z0-9_.-]*_(private|ref)([^A-Za-z0-9_]|$)\n"
    "^zeta-only$\n"
)
# Built by concatenation, so this file does not itself match the real denylist.
OWNER_PRIVATE = "owner" + "/" + "x_private"
# 300 stacked fixed-count repetitions: the translation nests 299 groups deep, past the gate's bound of 200.
STACKED_ENTRY = "zqsecret" + "{1}" * 300


def test_names_ere():
    print("== names: POSIX ERE denylist and default path (tools/check_names.py) ==")
    ere_list = SCRATCH / "terms-ere.regex"
    ere_list.write_text(ERE_DENYLIST, encoding="utf-8")
    with_ere = base_env(OPFILES_NAMES_DENYLIST=str(ere_list))

    def tree(**files):
        fixture = Fixture("check_names.py")
        fixture.write("README.md", "Plain text with no name in it.\n")
        for rel, text in files.items():
            fixture.write(rel, text)
        return fixture

    def with_entries(name, text):
        """A denylist written as UTF-8 text, or bytes as they are."""
        path = SCRATCH / name
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return base_env(OPFILES_NAMES_DENYLIST=str(path))

    expect("a clean tree passes with the ERE denylist", tree().run("check_names.py", env=with_ere), 0,
           contains=["PASS: no denylist match (4 entries)"])
    expect("refused: bracket classes and an interval, matched case-insensitively",
           tree(**{"notes.md": "Ask FIXTURECORP42, please.\n"}).run("check_names.py", env=with_ere), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["fixturecorp42"])
    expect("a negated bracket class keeps its boundary: fixturecorp421 and fixturecorp4 pass",
           tree(**{"notes.md": "fixturecorp421 and fixturecorp4\n"}).run("check_names.py", env=with_ere), 0)
    expect("refused: each branch of an alternation",
           tree(**{"notes.md": "Demoorg-Ops\nsamplecorp-ops\ndemoorg ops\n"}).run("check_names.py", env=with_ere), 1,
           contains=["notes.md:1: denylist entry 2", "notes.md:2: denylist entry 2"], lacks=["notes.md:3:", "-ops"])
    expect("anchors hold to the line: only a line that is exactly the entry is refused",
           tree(**{"notes.md": "Zeta-Only\nsee zeta-only here\n"}).run("check_names.py", env=with_ere), 1,
           contains=["notes.md:1: denylist entry 4"], lacks=["notes.md:2:", "zeta"])
    expect("path context in contents: an owner-qualified _private path is refused, receipt_ref is not",
           tree(**{"notes.md": "Kept at " + OWNER_PRIVATE + ".\nThe receipt_ref field.\n"}).run(
               "check_names.py", env=with_ere), 1,
           contains=["notes.md:1: denylist entry 3"], lacks=["notes.md:2:", "x_private"])
    expect("path context in paths: an owner-qualified _private path is refused and masked, receipt_ref is not",
           tree(**{OWNER_PRIVATE: "Plain text.\n", "receipt_ref": "Plain text.\n"}).run(
               "check_names.py", env=with_ere), 1,
           contains=["owner/*********: path matches denylist entry 3"], lacks=["receipt_ref:", "x_private"])
    expect("matching is not limited to whole words",
           tree(**{"notes.md": "Built at fixturecorpland.\n"}).run(
               "check_names.py", env=with_entries("plain.regex", "Fixturecorp\n")), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["fixturecorp"])
    expect("cannot evaluate: an uncompilable line, named by its line number only",
           tree().run("check_names.py", env=with_entries("unbalanced.regex", "# comment\nFixturecorp\n(nevercloses\n")),
           2, contains=["CANNOT-EVALUATE", "line 3 cannot be translated"], lacks=["nevercloses"])
    expect("cannot evaluate: an escape that ERE does not define (Python's \\d)",
           tree(**{"notes.md": "foo7\n"}).run("check_names.py", env=with_entries("escape.regex", "Fixturecorp\nfoo\\d\n")),
           2, contains=["line 2 cannot be translated"], lacks=["foo"])
    expect("cannot evaluate: an unknown bracket class",
           tree().run("check_names.py", env=with_entries("class.regex", "[[:nosuch:]]x\n")), 2,
           contains=["line 1 cannot be translated"], lacks=["nosuch"])
    expect("the GNU escape \\` anchors at the start of the line",
           tree(**{"notes.md": "fixturecorp at the start\nends with fixturecorp\n"}).run(
               "check_names.py", env=with_entries("start.regex", "\\`fixturecorp\n")), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["notes.md:2:", "fixturecorp"])
    expect("the GNU escape \\' anchors at the end of the line",
           tree(**{"notes.md": "fixturecorp at the start\nends with fixturecorp\n"}).run(
               "check_names.py", env=with_entries("end.regex", "fixturecorp\\'\n")), 1,
           contains=["notes.md:2: denylist entry 1"], lacks=["notes.md:1:", "fixturecorp"])
    expect("a path component is masked whole, whichever alternative matches: (foo|foobar)",
           tree(**{"docs/foobar-notes.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("alternation.regex", "(foo|foobar)\n")), 1,
           contains=["docs/" + "*" * len("foobar-notes.md") + ": path matches denylist entry 1"],
           lacks=["foo", "bar"])
    # chr(0xE9) is a non-ASCII letter; in the C locale it is not a word character, so \b holds after it.
    expect("C locale: a non-ASCII letter is not a word character",
           tree(**{"notes.md": "fixturecorp" + chr(0xE9) + "\nfixturecorpe\n"}).run(
               "check_names.py", env=with_entries("word.regex", "\\bfixturecorp\\b\n")), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["notes.md:2:", "fixturecorp"])
    expect("cannot evaluate: a carriage return or a byte order mark in a line, named by its line number only",
           tree().run("check_names.py", env=with_entries(
               "crlf.regex", "# comment\nFixturecorp\r\n" + chr(0xFEFF) + "Samplecorp\nDemoorg\n")), 2,
           contains=["CANNOT-EVALUATE", "lines 2, 3 cannot be translated"], lacks=["fixturecorp", "samplecorp"])
    expect("the longest match from a start is masked: (docs|docs/foobar)",
           tree(**{"docs/foobar-notes.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("longest.regex", "(docs|docs/foobar)\n")), 1,
           contains=["****/" + "*" * len("foobar-notes.md") + ": path matches denylist entry 1"],
           lacks=["docs", "foobar", "notes"])
    # \B after docs/foo holds only because the next byte, b, is a word character; the end of each
    # candidate match must see the rest of the path, as grep does.
    expect("the longest match from a start is masked when it ends in an assertion: (docs|docs/foo\\B)",
           tree(**{"docs/foobar-notes.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("longest-assertion.regex", "(docs|docs/foo\\B)\n")), 1,
           contains=["****/" + "*" * len("foobar-notes.md") + ": path matches denylist entry 1"],
           lacks=["docs", "foobar", "notes"])
    # grep reads a file with a NUL byte as binary and ends a line at each NUL, so ^ holds after it.
    expect("a line with a NUL byte is refused when an entry matches a part between NUL bytes",
           tree(**{"image.bin": b"\x89PNG\x00secretco\n"}).run(
               "check_names.py", env=with_entries("nul.regex", "^secretco\n")), 1,
           contains=["image.bin:1: denylist entry 1"], lacks=["secretco"])
    # chr(0xE9) is one character but two UTF-8 bytes; grep in the C locale counts bytes, so a..b and
    # x\W\Wy match a, e acute, b and x, e acute, y, and a..b does not match a, two e acutes, b.
    e_acute = chr(0xE9)
    expect("C locale: . and \\W match one byte of a multibyte character in a line",
           tree(**{"notes.md": "a" + e_acute + "b\nx" + e_acute + "y\na" + e_acute * 2 + "b\n"}).run(
               "check_names.py", env=with_entries("bytes.regex", "a..b\nx\\W\\Wy\n")), 1,
           contains=["notes.md:1: denylist entry 1", "notes.md:2: denylist entry 2"],
           lacks=["notes.md:1: denylist entry 2", "notes.md:2: denylist entry 1", "notes.md:3:", e_acute])
    # An entry holding a character outside ASCII is matched as its UTF-8 bytes; chr(0xC9), the capital
    # of chr(0xE9), differs from it in a byte outside ASCII, so in the C locale it is not the same letter.
    expect("C locale: an entry outside ASCII is matched as bytes, and only ASCII letters match either case",
           tree(**{"notes.md": "Caf" + e_acute + " here\nCAF" + chr(0xC9) + " here\n"}).run(
               "check_names.py", env=with_entries("non-ascii.regex", "caf" + e_acute + "\n")), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["notes.md:2:", e_acute])
    byte_path = "a" + e_acute + "b-notes.md"
    expect("C locale: a path is matched as bytes and masked with one asterisk for each byte",
           tree(**{byte_path: "Plain text.\n"}).run(
               "check_names.py", env=with_entries("bytes-path.regex", "a..b\n")), 1,
           contains=["*" * len(byte_path.encode("utf-8")) + ": path matches denylist entry 1"],
           lacks=["notes", e_acute])
    # chr(0xE9) written as one Latin-1 byte is not valid UTF-8; a lone carriage return does not end a line.
    expect("a file that is not valid UTF-8 is still read, and only a newline ends a line",
           tree(**{"notes.md": b"Caf\xe9 here.\rStill line one.\nBuilt at fixturecorp.\n"}).run(
               "check_names.py", env=with_entries("latin1.regex", "Fixturecorp\n")), 1,
           contains=["notes.md:2: denylist entry 1"], lacks=["notes.md:1:", "notes.md:3:", "fixturecorp"])
    # The address is assembled here, so this file holds none for the real gate to find.
    expect("--ci: an email address in a file that is not valid UTF-8, on the line grep counts",
           tree(**{"contact.md": b"Caf\xe9\rWrite to someone" + bytes([64]) + b"mailfixture.net.\n"}).run(
               "check_names.py", "--ci"), 1,
           contains=["contact.md:1: email address"], lacks=["contact.md:2:"])
    expect("cannot evaluate: every component of a printed path is masked when a line is refused",
           tree(**{"docs/fixturecorp-plan.md": "Write to someone" + chr(64) + "mailfixture.net.\n"}).run(
               "check_names.py", env=with_entries("partial.regex", "Fixturecorp\n(nevercloses\n")), 2,
           contains=["****/" + "*" * len("fixturecorp-plan.md") + ":1: email address",
                     "line 2 cannot be translated"],
           lacks=["docs", "fixturecorp", "plan", "nevercloses"])
    expect("cannot evaluate: a term of a refused line is not printed in a path",
           tree(**{"docs/secretco-plan.md": "Write to someone" + chr(64) + "mailfixture.net.\n"}).run(
               "check_names.py", env=with_entries("refused-term.regex", "Fixturecorp\nsecretco\\d\n")), 2,
           contains=["****/" + "*" * len("secretco-plan.md") + ":1: email address",
                     "line 2 cannot be translated"],
           lacks=["secretco", "plan"])
    # A denylist that is not valid UTF-8 (a Latin-1 comment and a Latin-1 entry) is read as bytes, so
    # its entries still match and mask printed paths.
    expect("a denylist that is not valid UTF-8 is read as bytes and still masks printed paths",
           tree(**{"docs/secretco-plan.md": "Write to someone" + chr(64) + "mailfixture.net.\n",
                   "notes.md": b"See x\xffy here.\n"}).run(
               "check_names.py",
               env=with_entries("latin1-terms.regex", b"Fixturecorp\nsecretco\n# caf\xe9\nx\xffy\n")), 1,
           contains=["docs/" + "*" * len("secretco-plan.md") + ":1: email address",
                     "docs/" + "*" * len("secretco-plan.md") + ": path matches denylist entry 2",
                     "notes.md:1: denylist entry 3"],
           lacks=["secretco", "plan"])
    # A directory cannot be read as a file; the denylist could have named any term.
    unreadable = SCRATCH / "unreadable-terms"
    unreadable.mkdir()
    expect("cannot evaluate: every component of a printed path is masked when the denylist cannot be read",
           tree(**{"docs/secretco-plan.md": "Write to someone" + chr(64) + "mailfixture.net.\n"}).run(
               "check_names.py", env=base_env(OPFILES_NAMES_DENYLIST=str(unreadable))), 2,
           contains=["****/" + "*" * len("secretco-plan.md") + ":1: email address", "cannot be read"],
           lacks=["secretco", "plan"])
    # A home directory of an account that does not exist cannot be found, so the path cannot be resolved.
    expect("cannot evaluate: every component of a printed path is masked when the denylist cannot be resolved",
           tree(**{"docs/secretco-plan.md": "Write to someone" + chr(64) + "mailfixture.net.\n"}).run(
               "check_names.py",
               env=base_env(OPFILES_NAMES_DENYLIST="~no-such-user-for-this-probe/terms.regex")), 2,
           contains=["****/" + "*" * len("secretco-plan.md") + ":1: email address", "cannot be resolved"],
           lacks=["secretco", "plan"])
    expect("cannot evaluate: groups nested more than 100 deep, named by the line number only",
           tree(**{"docs/zqsecret-plan.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("deep.regex", "(" * 101 + "zqsecret" + ")" * 101 + "\n")), 2,
           contains=["CANNOT-EVALUATE", "line 1 cannot be translated"], lacks=["zqsecret", "Traceback"])
    expect("groups nested 100 deep are translated, and a path that matches is masked",
           tree(**{"docs/zqsecret-plan.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("deep-ok.regex", "(" * 100 + "zqsecret" + ")" * 100 + "\n")), 1,
           contains=["docs/" + "*" * len("zqsecret-plan.md") + ": path matches denylist entry 1"],
           lacks=["zqsecret", "Traceback"])
    # Each stacked repetition of a fixed count, such as {1}, adds a group around the atom in the
    # translation; a stacked * is refused earlier, as a repetition stacked on a repetition whose count
    # is not fixed, so it would never reach the nesting check (test_names_backtracking checks which
    # refusal this entry meets).
    expect("cannot evaluate: repetitions stacked so deep that the translation nests more than 200 deep",
           tree(**{"docs/zqsecret-plan.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("stacked.regex", STACKED_ENTRY + "\n")), 2,
           contains=["CANNOT-EVALUATE", "line 1 cannot be translated"], lacks=["zqsecret", "Traceback"])
    # grep -E -i in the C locale refuses a range whose upper-cased end sorts before its upper-cased start.
    expect("cannot evaluate: a range that grep -E -i refuses, such as [F-b] or [Z-a]",
           tree(**{"notes.md": "Plain text.\n"}).run(
               "check_names.py", env=with_entries("range.regex", "zq[F-b]\nzq[Z-a]\nzq[A-z]\n")), 2,
           contains=["CANNOT-EVALUATE", "lines 1, 2 cannot be translated"], lacks=["zq", "line 3"])
    # The default denylist: a home that holds ~/.config/protected-terms/terms.regex.
    home = SCRATCH / "home-with-terms"
    default = home / ".config" / "protected-terms" / "terms.regex"
    default.parent.mkdir(parents=True)
    default.write_text("Fixturecorp\n", encoding="utf-8")
    expect("the default denylist is read when OPFILES_NAMES_DENYLIST is unset",
           tree(**{"notes.md": "Built at fixturecorp.\n"}).run("check_names.py", env=base_env(HOME=str(home))), 1,
           contains=["notes.md:1: denylist entry 1"])
    expect("the default denylist is read when OPFILES_NAMES_DENYLIST is empty",
           tree(**{"notes.md": "Built at fixturecorp.\n"}).run(
               "check_names.py", env=base_env(HOME=str(home), OPFILES_NAMES_DENYLIST="")), 1,
           contains=["notes.md:1: denylist entry 1"], lacks=["fixturecorp"])
    expect("OPFILES_NAMES_DENYLIST, when set, replaces the default denylist",
           tree(**{"notes.md": "Built at fixturecorp.\n"}).run(
               "check_names.py", env=base_env(HOME=str(home), OPFILES_NAMES_DENYLIST=str(ere_list))), 0)
    empty_home = SCRATCH / "home"
    expect("cannot evaluate: no default denylist file, and the home directory is not printed",
           tree().run("check_names.py", env=base_env(HOME=str(empty_home))), 2,
           contains=["~/.config/protected-terms/terms.regex (OPFILES_NAMES_DENYLIST is not set or is empty) "
                     "does not exist"],
           lacks=[str(empty_home)])


def test_names_second_matcher():
    print("== names: constructs grep hands to its second matcher, and widened masking ==")

    def tree():
        fixture = Fixture("check_names.py")
        fixture.write("README.md", "Plain text with no name in it.\n")
        return fixture

    def with_entries(name, text):
        path = SCRATCH / name
        path.write_text(text, encoding="utf-8")
        return base_env(OPFILES_NAMES_DENYLIST=str(path))

    # grep decides a line with one matcher but compiles the entry for a second one as well, and hands
    # the whole match to that second matcher when the entry holds a back-reference, a collating
    # element or an equivalence class; the second matcher folds case and reads {,n} differently, so
    # the gate refuses these three rather than approximate either matcher.
    expect("cannot evaluate: a back-reference, named by its line number only",
           tree().run("check_names.py", env=with_entries("backref.regex", "zqterm\n(zq)x\\1\n")), 2,
           contains=["CANNOT-EVALUATE", "line 2 cannot be translated"], lacks=["zqterm"])
    expect("cannot evaluate: a collating element [.c.]",
           tree().run("check_names.py", env=with_entries("collating.regex", "zq[[.x.]]\n")), 2,
           contains=["line 1 cannot be translated"], lacks=["zq["])
    expect("cannot evaluate: an equivalence class [=c=]",
           tree().run("check_names.py", env=with_entries("equivalence.regex", "zq[[=x=]]\n")), 2,
           contains=["line 1 cannot be translated"], lacks=["zq["])
    expect("cannot evaluate: a collating element as a range end point",
           tree().run("check_names.py", env=with_entries("collating-range.regex", "zq[a-[.f.]]\n")), 2,
           contains=["line 1 cannot be translated"], lacks=["zq["])

    gate = load_names_gate()
    # The second matcher folds case inside a bracket expression by upper-casing both the members and
    # the searched byte, so the text grep reports can overlap bytes the deciding reading rejects; the
    # widened pattern that masked() searches holds the union of the two readings.
    entry = gate.compile_entry("[^7-y]")
    record(entry.search("z") is None,
           "the deciding reading holds: [^7-y] does not match z", "the deciding pattern matched z")
    record(entry.mask.search("z") is not None,
           "the widened pattern holds the reported reading: [^7-y] can report z",
           "the widened pattern missed z")
    shown = gate.masked("za/ok", [entry])
    record(shown == "**/ok",
           "a component only the reported reading overlaps is masked: [^7-y] on a z component",
           f"masked gave {shown!r}")
    entry = gate.compile_entry("[^A-z1-@[:upper:]]")
    shown = gate.masked("a_b/ok", [entry])
    record(shown == "***/ok",
           "a negated bracket with a class: a component only an underscore makes reportable is masked",
           f"masked gave {shown!r}")
    # A positive range is widened the same way: [z-<0x80>] can be reported on an underscore, whose
    # upper-cased value falls between the upper-cased end points.
    entry = gate.compile_entry("[z-" + chr(0x80) + "]")
    record(entry.search("x_/ok") is None,
           "the deciding reading holds: the widened range decides nothing", "the deciding pattern matched")
    shown = gate.masked("x_/ok", [entry])
    record(shown == "**/ok",
           "a positive range is widened for masking: an underscore component is masked",
           f"masked gave {shown!r}")
    entry = gate.compile_entry("(foo|foobar)x")
    record(entry.mask.pattern == entry.pattern,
           "an entry without a bracket expression keeps one reading", "the widened pattern differs")
    # The deciding reading of {,n} and of stacked intervals is unchanged.
    entry = gate.compile_entry("zq{,2}x")
    record(bool(entry.search("zx")) and bool(entry.search("zqqx")) and not entry.search("zqqqx"),
           "the GNU interval {,2} still reads as zero to two", "the interval reads wrongly")
    entry = gate.compile_entry("zq{2}{0,2}x")
    record(bool(entry.search("zx")) and bool(entry.search("zqqx")) and bool(entry.search("zqqqqx"))
           and not entry.search("zqx"),
           "stacked intervals still read as a repetition of the repetition", "the stack reads wrongly")


def load_names_gate():
    """check_names.py, copied into a fixture and loaded in this process, so its functions can be called
    directly; loading the copy keeps any bytecode out of this repository."""
    fixture = Fixture("check_names.py")
    spec = importlib.util.spec_from_file_location(f"check_names_fixture{COUNTER[0]}",
                                                  fixture.root / "tools" / "check_names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NowherePattern:
    """A pattern that matches nowhere: masked() must skip it after its search, using nothing else
    (reading the widened pattern of an entry is allowed; a plain pattern is its own)."""

    @property
    def mask(self):
        return self

    def search(self, *args):
        return None

    def match(self, *args):
        raise AssertionError("match called on a pattern that matches nowhere")

    def __getattr__(self, name):
        raise AssertionError(f"{name} read on a pattern that matches nowhere")


def per_end_masked(gate, rel, patterns):
    """The earlier masking, which tests every candidate end from every start where a pattern matches:
    the reference that masked() must never mask less than."""
    raw = gate.as_bytes(rel)
    covered = [False] * len(raw)
    for pattern in patterns:
        for start in range(len(raw) + 1):
            match = pattern.match(raw, start)
            if not match:
                continue
            end = match.end()
            for longest in range(len(raw), end, -1):
                held = re.compile(f"(?:{pattern.pattern})(?=(?s:.){{{len(raw) - longest}}}\\Z)", pattern.flags)
                if held.match(raw, start):
                    end = longest
                    break
            for position in range(start, end):
                covered[position] = True
    parts = []
    offset = 0
    for part in raw.split("/"):
        end = offset + len(part)
        parts.append("*" * len(part) if any(covered[offset:end]) else part)
        offset = end + 1
    return gate.from_bytes("/".join(parts))


# Entries and paths for the check that masked() never masks less than the earlier masking.
MASK_ENTRIES = ("(docs|docs/foobar)", "(docs|docs/foo\\B)", "(foo|foobar)", "a..b", "o/b", "s-n\\>", "[a-z]x",
                "^docs", "notes\\.md$", "\\bfoo", "(a|ab)(c|bcd)(d*)", "oo(/b)?", "r-n.*\\'", "x\\<", "/x/",
                "fixturecorp[[:digit:]]{2}([^[:alnum:]]|$)", "(b|bcd/x)", "d/x/a")
MASK_PATHS = ("docs/foobar-notes.md", "a/b", "xdocs/foo/bar", "abcd/x/abcd", "dir/fixturecorp42/x.md",
              "a" + chr(0xE9) + "b/c", "foo/bar/baz", "docs/foobar-notes.md/x")


def test_names_in_process():
    print("== names: masking and its shortcuts, in process (tools/check_names.py) ==")
    gate = load_names_gate()

    def check(label, function):
        try:
            ok, detail = function()
        except Exception as exc:  # any failure of the gate's code is a failed check, not a crashed run
            ok, detail = False, f"{exc.__class__.__name__}: {exc}"
        record(ok, label, detail)

    def nowhere_skipped():
        shown = gate.masked("a/b", [NowherePattern()])
        return shown == "a/b", f"masked gave {shown!r}"

    def masked_only_on_finding():
        calls = []
        original = gate.masked
        gate.masked = lambda rel, patterns, everything=False: calls.append(rel) or rel
        try:
            none = gate.denylist_findings([("a/b", ["x"])], [gate.compile_entry("zq")])
            some = gate.denylist_findings([("a/zq", ["x"])], [gate.compile_entry("zq")])
        finally:
            gate.masked = original
        ok = none == [] and some == ["a/zq: path matches denylist entry 1"] and calls == ["a/zq"]
        return ok, f"findings {none!r} and {some!r}, masked called for {calls!r}"

    def longest_with_assertion():
        shown = gate.masked("docs/foobar-notes.md", [gate.compile_entry("(docs|docs/foo\\B)")])
        want = "****/" + "*" * len("foobar-notes.md")
        return shown == want, f"masked gave {shown!r}"

    def never_weaker():
        weaker = []
        for entry in MASK_ENTRIES:
            patterns = [gate.compile_entry(entry)]
            for rel in MASK_PATHS:
                raw = gate.as_bytes(rel).split("/")
                now = gate.as_bytes(gate.masked(rel, patterns)).split("/")
                before = gate.as_bytes(per_end_masked(gate, rel, patterns)).split("/")
                if any(old != part and new == part for part, old, new in zip(raw, before, now)):
                    weaker.append(f"entry {MASK_ENTRIES.index(entry) + 1} on path {MASK_PATHS.index(rel) + 1}")
        return not weaker, f"masks less than the earlier masking for {', '.join(weaker)}"

    check("a pattern that matches nowhere in a path is skipped after its search", nowhere_skipped)
    check("a printed path is worked out only for a file with a finding", masked_only_on_finding)
    check("masking covers the longest match when it ends in an assertion that sees the next byte",
          longest_with_assertion)
    check("masking each component once never masks less than testing every end from every start", never_weaker)


# An entry of this shape, an alternation inside a starred group with nested intervals and quantified
# groups, once made masked() backtrack with no practical bound.
HANG_ENTRY = r"(Z*|\`(\B\||l{,2}{2}(\')y(\s+Jl{2}))|(.\W{,2}?){0,2}+K?\W)*|2"


def test_names_backtracking():
    print("== names: repeated groups that could backtrack without bound (tools/check_names.py) ==")

    def tree():
        fixture = Fixture("check_names.py")
        fixture.write("README.md", "Plain text with no name in it.\n")
        return fixture

    def with_entries(name, text):
        path = SCRATCH / name
        path.write_text(text, encoding="utf-8")
        return base_env(OPFILES_NAMES_DENYLIST=str(path))

    outcome = tree().run("check_names.py", env=with_entries("hang.regex", HANG_ENTRY + "\n"))
    expect("cannot evaluate: the entry that hung the fuzz gate (an alternation inside a starred group)",
           outcome, 2, contains=["CANNOT-EVALUATE", "line 1 cannot be translated"])

    gate = load_names_gate()

    def refused_before_matching():
        # compile_entry translates the entry before it compiles anything, and only a compiled entry is
        # ever searched; Untranslatable (not a ValueError raised from re.error) shows that the entry is
        # refused by the translation, so no pattern for it is compiled or matched against any text.
        try:
            gate.compile_entry(HANG_ENTRY)
        except gate.Untranslatable:
            return True, ""
        except Exception as exc:  # refused later than the translation, or a crash
            return False, f"compile_entry raised {exc.__class__.__name__}, not Untranslatable"
        return False, "compile_entry accepted the entry"

    ok, detail = refused_before_matching()
    record(ok, "that entry is refused by the translation, before any pattern is compiled or matched", detail)

    def refused(entry):
        try:
            gate.compile_entry(entry)
        except ValueError:
            return True
        return False

    record(refused("(a*)*"), "refused: a starred group whose body is itself repeated, (a*)*",
           "(a*)* was accepted")
    record(refused("(a+)+x"), "refused: a nested plus over a group, (a+)+x", "(a+)+x was accepted")
    record(refused("(a|ab){1,3}"), "refused: a repeated group over an alternation, (a|ab){1,3}",
           "(a|ab){1,3} was accepted")
    record(refused("(ab)*+"), "refused: a repetition stacked on a repeated group, (ab)*+",
           "(ab)*+ was accepted")
    record(refused("a*{1,}"), "refused: a repetition stacked on a repetition whose count is not fixed, a*{1,}",
           "a*{1,} was accepted")
    entry = gate.compile_entry("ab*c")
    record(bool(entry.search("xABBBc")) and not entry.search("abd"),
           "a plain quantified atom still works: ab*c", "ab*c reads wrongly")
    entry = gate.compile_entry("(ab){2}")
    record(bool(entry.search("zabab")) and not entry.search("zab"),
           "a quantified group of fixed-length literals still works: (ab){2}", "(ab){2} reads wrongly")
    entry = gate.compile_entry("(a.b){0,2}x")
    record(bool(entry.search("axbaybx")) and bool(entry.search("x")),
           "a repeated group whose body has one fixed length still works: (a.b){0,2}x",
           "(a.b){0,2}x reads wrongly")

    def over_cap():
        pattern = gate.compile_entry("zq")
        rel = "zq/" + "x" * gate.MASK_WORK_CAP
        shown = gate.masked(rel, [pattern])
        want = "**/" + "*" * gate.MASK_WORK_CAP
        return shown == want, f"masked gave {shown[:30]!r} and {len(shown)} characters"

    def under_cap():
        pattern = gate.compile_entry("zq")
        shown = gate.masked("aa/zq", [pattern])
        return shown == "aa/**", f"masked gave {shown!r}"

    capped_path = "aa/zq/" + "x" * 200

    def cap_counts_matching_entries():
        # 206 bytes times 1001 entries is above the cap, but only one entry matches the path.
        elsewhere = gate.compile_entry("zqnowhere")
        shown = gate.masked(capped_path, [elsewhere] * 1000 + [gate.compile_entry("zq")])
        want = "aa/**/" + "x" * 200
        return shown == want, f"masked gave {shown[:30]!r} and {len(shown)} characters"

    def cap_with_many_matching_entries():
        # 206 bytes times 400 entries that all match the path is above the cap.
        shown = gate.masked(capped_path, [gate.compile_entry("zq")] * 400)
        want = "**/**/" + "*" * 200
        return shown == want, f"masked gave {shown[:30]!r} and {len(shown)} characters"

    def stacked_reaches_nesting_check():
        try:
            gate.compile_entry(STACKED_ENTRY)
        except gate.Untranslatable as exc:
            return str(exc) == "repetitions nested too deeply", f"refused as {exc}"
        except Exception as exc:  # refused later than the translation, or a crash
            return False, f"compile_entry raised {exc.__class__.__name__}, not Untranslatable"
        return False, "compile_entry accepted the entry"

    def stacked_at_the_bound():
        entry = gate.compile_entry("zqsecret" + "{1}" * 201)
        return bool(entry.search("xZQSECRETx")), "the entry does not match its own term"

    for label, function in (("above the work cap every component is masked, which is safe", over_cap),
                            ("below the work cap only an overlapped component is masked", under_cap),
                            ("the work cap counts only the entries that match the path",
                             cap_counts_matching_entries),
                            ("the work cap still masks every component when enough entries match the path",
                             cap_with_many_matching_entries),
                            ("300 stacked {1} repetitions reach the nesting check, not an earlier refusal",
                             stacked_reaches_nesting_check),
                            ("201 stacked {1} repetitions, 200 groups deep, are translated and still match",
                             stacked_at_the_bound)):
        try:
            ok, detail = function()
        except Exception as exc:  # any failure of the gate's code is a failed check, not a crashed run
            ok, detail = False, f"{exc.__class__.__name__}: {exc}"
        record(ok, label, detail)


def test_names_budget():
    print("== names: the time budget of denylist matching (tools/check_names.py) ==")
    # Five unbounded repetitions in a row: an entry the gate accepts, whose search of a long run of a
    # backtracks far longer than the shortened budget below.
    slow_list = SCRATCH / "slow.regex"
    slow_list.write_text("a*a*a*a*a*zq\n", encoding="utf-8")
    with_slow = base_env(OPFILES_NAMES_DENYLIST=str(slow_list))

    def tree(budget):
        fixture = Fixture("check_names.py")
        gate = fixture.root / "tools" / "check_names.py"
        gate.write_text(mutate(gate.read_text(encoding="utf-8"), "\nMATCH_BUDGET_SECONDS = 60\n",
                               f"\nMATCH_BUDGET_SECONDS = {budget}\n"), encoding="utf-8")
        fixture.write("README.md", "Plain text with no name in it.\n")
        return fixture

    # The slow file sorts before README.md and the gate's own copy, so it is the first file the worker
    # matches: no other file is matched under the shortened budget, and the search of 3000 a characters
    # by that entry cannot finish within it, so the file the reason names does not depend on timing.
    slow = "Docs/zqslow-plan.md"
    fixture = tree(0.5)
    fixture.write(slow, "Write to someone" + chr(64) + "mailfixture.net.\n" + "a" * 3000 + "\n")
    hidden = "****/" + "*" * len("zqslow-plan.md")
    expect("cannot evaluate: matching a file past its time budget names only that file, masked",
           fixture.run("check_names.py", env=with_slow), 2,
           contains=[hidden + ":1: email address",
                     "CANNOT-EVALUATE: denylist matching of " + hidden + " did not finish within 0.5 seconds"],
           lacks=["zqslow", "plan", "docs", "a*a*", "Traceback"])
    # The full budget of 60 seconds, so a busy machine cannot push any file of this case past it.
    slow = "docs/zqslow-plan.md"
    fixture = tree(60)
    fixture.write(slow, "Write to someone" + chr(64) + "mailfixture.net.\nzq " + "a" * 20 + "\n")
    expect("within its budget the worker reports and masks as before",
           fixture.run("check_names.py", env=with_slow), 1,
           contains=["docs/" + "*" * len("zqslow-plan.md") + ":1: email address",
                     "docs/" + "*" * len("zqslow-plan.md") + ": path matches denylist entry 1",
                     "docs/" + "*" * len("zqslow-plan.md") + ":2: denylist entry 1",
                     "FAIL: 2 denylist match(es)"],
           lacks=["zqslow", "CANNOT-EVALUATE", "Traceback"])


class FakeConnection:
    """The parent's end of a fake worker connection for timed_matching: poll answers in turn from polls
    (True once they run out), recv returns replies in turn (raising a reply that is an exception, and
    EOFError once they run out), and send records each message."""

    def __init__(self, polls=(), replies=()):
        self.polls = list(polls)
        self.replies = list(replies)
        self.sent = []
        self.closed = False

    def poll(self, timeout=None):
        return self.polls.pop(0) if self.polls else True

    def recv(self):
        if not self.replies:
            raise EOFError
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def send(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


class FakeProcess:
    """A fake worker process: start raises start_error when one is given; kill and join are recorded."""

    def __init__(self, start_error=None):
        self.start_error = start_error
        self.pid = None
        self.args = None
        self.killed = False
        self.ended = False

    def start(self):
        if self.start_error is not None:
            raise self.start_error
        self.pid = -1

    def is_alive(self):
        return self.pid is not None and not self.killed and not self.ended

    def kill(self):
        self.killed = True

    def join(self, timeout=None):
        self.ended = True


class FakeContext:
    """A fake spawn context whose Pipe and Process hand out the given fakes."""

    def __init__(self, ours, process):
        self.ours = ours
        self.theirs = FakeConnection()
        self.process = process

    def Pipe(self):
        return self.ours, self.theirs

    def Process(self, target, args, daemon):
        self.process.args = args
        return self.process


def captured_output(function):
    """Run function with file descriptors 1 and 2 on a temporary file; return (its result, the bytes
    written to either), so a child process that inherits them is captured too."""
    sys.stdout.flush()
    sys.stderr.flush()
    with tempfile.TemporaryFile(dir=SCRATCH) as sink:
        saved = [os.dup(1), os.dup(2)]
        try:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            result = function()
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            for descriptor in saved:
                os.close(descriptor)
        sink.seek(0)
        return result, sink.read()


def test_names_worker():
    print("== names: the matching worker's fail-closed branches and its silence (tools/check_names.py) ==")
    gate = load_names_gate()
    real = gate.multiprocessing
    entry = gate.compile_entry("zq")
    files = [("a/zq", ["zq here"])]

    def fake_run(ours, process):
        context = FakeContext(ours, process)
        gate.multiprocessing = types.SimpleNamespace(get_context=lambda method: context)
        try:
            return gate.timed_matching(files, [entry], {"a/zq"}), context
        finally:
            gate.multiprocessing = real

    def fails_closed(label, ours, want, process=None, killed=True):
        try:
            (named, shown, reason), context = fake_run(ours, process or FakeProcess())
        except Exception as exc:  # timed_matching must never raise; a raise is a failed check
            record(False, label, f"timed_matching raised {exc.__class__.__name__}")
            return
        problems = []
        if named or shown:
            problems.append(f"findings {named!r} and paths {shown!r}")
        if reason is None or want not in reason:
            problems.append(f"reason {reason!r}")
        elif "zq" in reason:
            problems.append("the reason holds the matched text")
        if context.process.killed != killed:
            problems.append("the worker was killed" if context.process.killed else "the worker was not killed")
        if not (context.ours.closed and context.theirs.closed):
            problems.append("a connection was left open")
        record(not problems, label, "; ".join(problems))

    fails_closed("fails closed: the worker does not start within WORKER_START_SECONDS",
                 FakeConnection(polls=[False]), "did not start within 60 seconds")
    fails_closed("fails closed: the worker's first message is not that it is ready",
                 FakeConnection(replies=[("hello",)]), "did not start, so the denylist checks did not run")
    fails_closed("fails closed: the worker replies with an error, named by its class only",
                 FakeConnection(replies=[("ready",), ("error", "ValueError")]), "worker failed (ValueError)")
    fails_closed("fails closed: the worker's connection ends during a file",
                 FakeConnection(replies=[("ready",)]), "worker failed (EOFError)")
    fails_closed("fails closed: a malformed reply from the worker",
                 FakeConnection(replies=[("ready",), ("done",)]), "worker failed (IndexError)")
    fails_closed("fails closed: the worker cannot be started", FakeConnection(), "worker failed (OSError)",
                 FakeProcess(OSError("no process")), killed=False)
    fails_closed("fails closed: a file past its budget is named with every component masked",
                 FakeConnection(polls=[True, False], replies=[("ready",)]),
                 "denylist matching of */** did not finish within 60 seconds")

    def protocol():
        ours = FakeConnection(replies=[("ready",), ("done", ["a/**: path matches denylist entry 1"], "a/**")])
        (named, shown, reason), context = fake_run(ours, FakeProcess())
        ok = (reason is None and named == ["a/**: path matches denylist entry 1"] and shown == {"a/zq": "a/**"}
              and context.process.args == (context.theirs,)
              and ours.sent == [[entry], ("a/zq", ["zq here"], True)] and not context.process.killed)
        return ok, (f"reason {reason!r}, findings {named!r}, paths {shown!r}, "
                    f"{len(context.process.args)} start argument(s), {len(ours.sent)} message(s) sent")

    def silent_start_failure():
        # Registered under its fixture name, the worker's target pickles in this process, but the spawned
        # child cannot import that name, so it fails at its start, as a gate loaded under another module
        # name does; a traceback of that failure would name absolute paths.
        sys.modules[gate.__name__] = gate
        try:
            (named, shown, reason), output = captured_output(
                lambda: gate.timed_matching(files, [entry], {"a/zq"}))
        finally:
            sys.modules.pop(gate.__name__, None)
        ok = named == [] and shown == {} and reason is not None and "worker failed (" in reason and output == b""
        return ok, (f"reason {reason!r}, {len(output)} byte(s) printed"
                    + (", among them a traceback" if b"Traceback" in output else ""))

    for label, function in (("the entries reach the worker after it is ready, not as start arguments", protocol),
                            ("a worker that fails at its start prints nothing, and the gate fails closed",
                             silent_start_failure)):
        try:
            ok, detail = function()
        except Exception as exc:  # any failure of the gate's code is a failed check, not a crashed run
            ok, detail = False, f"{exc.__class__.__name__}"
        record(ok, label, detail)


def spawned_workers(parent):
    """The process IDs of the spawned multiprocessing workers whose parent is parent, read from /proc."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="latin-1")
            command = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        # The command name in stat is in parentheses and may hold spaces; the state and parent follow it.
        fields = stat.rsplit(")", 1)[-1].split()
        if len(fields) > 1 and fields[1] == str(parent) and b"spawn_main" in command:
            found.append(int(entry.name))
    return found


def test_names_sigterm():
    print("== names: SIGTERM sent to the gate stops its matching worker (tools/check_names.py) ==")
    if not Path(f"/proc/{os.getpid()}/stat").is_file():
        print("  skip  SIGTERM stops the worker: no /proc here to find the worker process")
        return
    slow_list = SCRATCH / "slow-sigterm.regex"
    slow_list.write_text("a*a*a*a*a*zq\n", encoding="utf-8")
    fixture = Fixture("check_names.py")
    fixture.write("README.md", "Plain text with no name in it.\n")
    fixture.write("Docs/zqslow-plan.md", "a" * 3000 + "\n")
    gate = subprocess.Popen([sys.executable, "-I", "-B", str(fixture.root / "tools" / "check_names.py")],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=fixture.root,
                            env=base_env(OPFILES_NAMES_DENYLIST=str(slow_list)))
    workers, left, out, read = [], [], "", False
    try:
        deadline = time.monotonic() + 60
        while not workers and gate.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
            workers = spawned_workers(gate.pid)
        if workers:
            # Let the worker reach the slow file, whose search runs far past this pause.
            time.sleep(1)
            gate.send_signal(signal.SIGTERM)
        try:
            out, _ = gate.communicate(timeout=60)
            read = True
        except subprocess.TimeoutExpired:
            pass  # a worker that outlived the gate can hold its output open; it is killed below
    finally:
        # A worker left running is killed here whatever happened above, so no search outlives this test.
        deadline = time.monotonic() + 5
        left = workers
        while left and time.monotonic() < deadline:
            time.sleep(0.05)
            left = [pid for pid in workers if Path(f"/proc/{pid}").exists()]
        for pid in left:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if gate.poll() is None:
            gate.kill()
        if not read:
            out = gate.communicate()[0] or ""
    record(bool(workers) and not left, "the worker is gone once the gate exits after SIGTERM",
           "the worker was never seen" if not workers else f"{len(left)} worker(s) outlived the gate")
    expect("SIGTERM during matching: the gate reports CANNOT-EVALUATE and exits 2", (gate.returncode, out), 2,
           contains=["CANNOT-EVALUATE: the gate received SIGTERM"], lacks=["zqslow", "Traceback"])


# A file name with one of these extensions, in a comment of this file.
COMMENT_FILE_NAME = re.compile(r"[A-Za-z0-9_./~-]+\.(?:txt|md|py|sh|toml|yml|yaml|json|regex|log)\b")


def comment_file_names(source):
    """(line number, name) for each file name COMMENT_FILE_NAME finds in a comment of the Python source,
    whole-line or trailing; text in a string is not a comment."""
    names = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            names += [(token.start[0], name) for name in COMMENT_FILE_NAME.findall(token.string)]
    return names


def known_files():
    """The files of the repository as relative POSIX paths: in a git checkout the tracked files only,
    so a machine-local file in the working tree never counts; otherwise every file under the root
    outside .git."""
    env = {key: value for key, value in os.environ.items() if key not in CLEARED}
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, env=env,
                                timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        result = None
    if result is not None and result.returncode == 0 and result.stdout:
        return {name for name in result.stdout.decode("utf-8", "surrogateescape").split("\0") if name}
    return {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(ROOT).parts}


def names_known_file(name, files):
    """Whether a name in a comment is one of files: as a path from the root or from tools/, or, for a
    bare file name, as the name of any of them. A name with a .. component is never one."""
    path = PurePosixPath(name)
    if ".." in path.parts:
        return False
    rel = path.as_posix()
    return rel in files or f"tools/{rel}" in files or (
        "/" not in rel and any(PurePosixPath(known).name == rel for known in files))


def test_comment_references():
    print("== the comments of tools/test_gates.py name only files in the repository ==")
    files = known_files()
    sample = 'text = "# kept.md"  # see trailing-name.md\n# see whole-line.txt\n'
    found = comment_file_names(sample)
    record(found == [(1, "trailing-name.md"), (2, "whole-line.txt")],
           "a trailing comment is read and text in a string is not", f"found {found!r}")
    record(names_known_file("tools/check_names.py", files) and names_known_file("check_names.py", files)
           and not names_known_file("../tools/check_names.py", files)
           and not names_known_file("tools/../tools/check_names.py", files),
           "a name with a .. component is refused, a repository file is found", "the name check is wrong")
    missing = []
    for number, name in comment_file_names(Path(__file__).read_text(encoding="utf-8")):
        if name.startswith(("~/", "/")):
            continue  # a home-directory or absolute path, not a repository file
        if not names_known_file(name, files):
            missing.append(f"line {number}")
    record(not missing, "every file a comment names is in the repository",
           f"a comment names a file the repository does not hold, at {', '.join(missing)}")


def test_dashes():
    print("== dashes (tools/check_no_dashes.py) ==")

    def tree():
        fixture = Fixture("check_no_dashes.py")
        fixture.write("README.md", "Plain text - with a hyphen.\n")
        return fixture

    expect("a clean tree passes", tree().run("check_no_dashes.py"), 0)
    fixture = tree()
    fixture.write("notes.md", "one " + EN_DASH + " two\n")
    expect("refused: an en dash in a file", fixture.run("check_no_dashes.py"), 1, contains=["notes.md:1:5: en dash"])
    fixture = tree()
    fixture.write("a" + EM_DASH + "b.txt", "plain\n")
    expect("refused: an em dash in a path", fixture.run("check_no_dashes.py"), 1, contains=["em dash in the path"])
    fixture = tree()
    fixture.write(".gitignore", "local.txt\n")
    fixture.write("local.txt", "one " + EM_DASH + " two\n")
    fixture.git("init", "-q")
    fixture.git("add", "README.md", ".gitignore")
    expect("an ignored file is not scanned in a git checkout", fixture.run("check_no_dashes.py"), 0)
    fixture.write("new.md", "one " + EM_DASH + " two\n")
    expect("refused: an untracked file that is not ignored", fixture.run("check_no_dashes.py"), 1,
           contains=["new.md:1:5: em dash"])


def test_links():
    print("== links (tools/check_links.py) ==")

    def tree(readme):
        fixture = Fixture("check_links.py")
        fixture.write("docs/a.md", "Target.\n")
        fixture.write("README.md", readme)
        return fixture

    outside = SCRATCH / "outside.md"
    outside.write_text("Outside the fixture.\n", encoding="utf-8")
    expect("an existing internal link passes", tree("See [a](docs/a.md#part).\n").run("check_links.py"), 0)
    expect("a link inside a code span is not read", tree("Text `[a](missing.md)` here.\n").run("check_links.py"), 0)
    expect("refused: a broken link", tree("See [a](docs/missing.md).\n").run("check_links.py"), 1,
           contains=["README.md:1: broken link -> docs/missing.md"])
    expect("refused: an existing target outside the repository",
           tree("See [o](../outside.md).\n").run("check_links.py"), 1,
           contains=["link outside the repository -> ../outside.md"])
    expect("refused: an absolute path outside the repository",
           tree(f"See [o]({outside}).\n").run("check_links.py"), 1, contains=["link outside the repository"])
    fixture = tree("See [a](docs/a.md).\n")
    fixture.write(".gitignore", "local-notes.md\n")
    fixture.write("local-notes.md", "See [x](missing.md).\n")
    fixture.git("init", "-q")
    fixture.git("add", "README.md", ".gitignore", "docs/a.md")
    expect("an ignored file is not read in a git checkout", fixture.run("check_links.py"), 0)


FAKE_GITLEAKS = """#!/usr/bin/env bash
if [ "${1:-}" = version ]; then printf '%s\\n' "$FAKE_VERSION"; exit 0; fi
[ "${1:-}" = dir ] || exit 64
( cd "$2" && find . -type f | sort ) >"$FAKE_RECORD"
exit "${FAKE_RC:-0}"
"""


def test_secrets():
    print("== secrets (tools/check_secrets.sh, with a fake gitleaks) ==")
    toolbin = SCRATCH / "toolbin"
    toolbin.mkdir()
    missing = []
    for tool in ("bash", "dirname", "tr", "cut", "git", "tar", "mktemp", "rm", "mkdir", "env", "find", "sort", "cat"):
        found = shutil.which(tool)
        if found:
            (toolbin / tool).symlink_to(found)
        else:
            missing.append(tool)
    if missing:
        record(False, "build the secrets gate's tool directory", f"not found: {', '.join(missing)}")
        return
    fakebin = SCRATCH / "fakebin"
    fakebin.mkdir()
    fake = fakebin / "gitleaks"
    fake.write_text(FAKE_GITLEAKS, encoding="utf-8")
    fake.chmod(0o755)
    scanned = SCRATCH / "scanned.txt"

    def env(**extra):
        values = {"PATH": f"{fakebin}:{toolbin}", "FAKE_VERSION": "v8.30.1", "FAKE_RECORD": str(scanned)}
        values.update(extra)
        return base_env(**values)

    def tree():
        fixture = Fixture("check_secrets.sh")
        fixture.write("README.md", "Plain text.\n")
        return fixture

    expect("refused: gitleaks not on PATH", tree().run("check_secrets.sh", env=env(PATH=str(toolbin))), 1,
           contains=["gitleaks is not on PATH"])
    expect("refused: another gitleaks version", tree().run("check_secrets.sh", env=env(FAKE_VERSION="8.30.0")), 1,
           contains=["reports version 8.30.0"])
    expect("refused: gitleaks reports findings", tree().run("check_secrets.sh", env=env(FAKE_RC="1")), 1,
           contains=["reported findings"])
    expect("the pinned version with no findings passes", tree().run("check_secrets.sh", env=env()), 0,
           contains=["the whole directory (not a git checkout)"])
    fixture = tree()
    fixture.write(".gitignore", "local/settings.json\n")
    fixture.write("local/settings.json", "{}\n")
    fixture.git("init", "-q")
    fixture.git("add", "README.md", ".gitignore", "tools/check_secrets.sh")
    fixture.write("new.txt", "untracked and not ignored\n")
    expect("a git checkout is scanned as its tracked and unignored files", fixture.run("check_secrets.sh", env=env()),
           0, contains=["the tracked and unignored files"])
    listed = scanned.read_text(encoding="utf-8").split() if scanned.exists() else []
    record("./README.md" in listed and "./new.txt" in listed and "./local/settings.json" not in listed,
           "  the ignored settings file is not scanned; tracked and untracked unignored files are",
           f"scanned: {listed}")


def main():
    global SCRATCH
    with tempfile.TemporaryDirectory(prefix="test-gates.") as scratch:
        SCRATCH = Path(scratch).resolve()
        (SCRATCH / "home").mkdir()
        for test in (test_workflow_contract, test_ci_python_pin, test_names, test_names_ere,
                     test_names_second_matcher, test_names_in_process, test_names_backtracking,
                     test_names_budget, test_names_worker, test_names_sigterm, test_comment_references,
                     test_dashes, test_links, test_secrets):
            try:
                test()
            except (AssertionError, OSError, subprocess.SubprocessError) as exc:
                record(False, f"{test.__name__} could not run", f"{exc.__class__.__name__}: {exc}")
    failures = RESULTS.count(False)
    print()
    if failures:
        print(f"FAIL: gate tests ({len(RESULTS)} checks, {failures} failures)")
        return 1
    print(f"PASS: gate tests ({len(RESULTS)} checks, 0 failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
