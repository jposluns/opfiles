"""Check that CLAUDE.md and AGENTS.md at the repository root are byte-identical, and that the
root .gitignore ignores CLAUDE.local.md.

Usage:
  python3 tools/check_agents_parity.py [--root PATH]
  python3 tools/check_agents_parity.py --self-test

Both files must be regular files with identical bytes. The root is opened once and every file is
resolved beneath that directory descriptor, so no symlink is followed. Each file is opened with
O_NOFOLLOW and O_NONBLOCK, and fstat confirms a regular file before any byte is read.

The shared text names CLAUDE.local.md as the untracked machine-local file for private method,
account references and host paths, so the root .gitignore must ignore it: it needs a line
"CLAUDE.local.md" or "/CLAUDE.local.md" that no later negation re-includes. A later "!" line is
taken as a negation when its pattern, less a leading "/" or "**/", matches CLAUDE.local.md under
fnmatch.fnmatchcase, so "!*.md" and "!CLAUDE.local.*" count as well as "!CLAUDE.local.md".

Exit status:
  0  both files are regular files with identical bytes, and .gitignore ignores CLAUDE.local.md;
  1  the files differ, one or both are missing, either is a symlink or not a regular file, or
     .gitignore is missing, is a symlink or not a regular file, or does not ignore
     CLAUDE.local.md;
  2  the check cannot be evaluated: the root cannot be opened as a directory, a file cannot be
     read for a reason other than absence, an unexpected error occurs, the command line is
     invalid, or Python is older than 3.14.

The default root is the parent of this tool's directory, resolved with os.path.realpath, as in
tools/check_aiqt_vendored.py. Only the standard library is used.
"""

import sys

MIN_PYTHON = (3, 14)
TOOL = "check_agents_parity"


def python_gate(version):
    """Return 2 when the given version is older than the floor, else 0."""
    return 2 if tuple(version[:2]) < MIN_PYTHON else 0


# The floor is checked at load, as the OPF tools in tools/ check theirs, so the only test of
# __name__ is the entry block at the end of the file.
if python_gate(sys.version_info) != 0:
    import os
    try:
        sys.stderr.write(
            "%s: Python 3.14 or newer is required; this is Python %d.%d\n"
            % (TOOL, sys.version_info[0], sys.version_info[1])
        )
        sys.stderr.flush()
    except BaseException:
        pass
    os._exit(2)

import argparse  # noqa: E402
import contextlib  # noqa: E402
import errno  # noqa: E402
import fnmatch  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402

NAMES = ("CLAUDE.md", "AGENTS.md")
GITIGNORE = ".gitignore"
LOCAL_FILE = "CLAUDE.local.md"
IGNORE_RULES = (LOCAL_FILE, "/" + LOCAL_FILE)
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CANNOT = 2
ROOT_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
# O_NOFOLLOW refuses a symlink swapped in after lstat; O_NONBLOCK keeps a swapped-in FIFO from
# blocking the open. Neither changes how a regular file is read.
READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
CASE_SECONDS = 10

# The self-test replaces this to inject races and read errors; everything else uses os.open.
_open = os.open


def default_root():
    """Return the parent of this tool's directory, resolved with os.path.realpath."""
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def read_regular(root_fd, name):
    """Read one file beneath root_fd without following a symlink.

    Return a pair (state, value). The state is "ok" with the file's bytes; "missing",
    "symlink" or "not-regular" with None; or "error" with the OSError.
    """
    try:
        st = os.lstat(name, dir_fd=root_fd)
    except FileNotFoundError:
        return "missing", None
    except OSError as exc:
        return "error", exc
    if stat.S_ISLNK(st.st_mode):
        return "symlink", None
    if not stat.S_ISREG(st.st_mode):
        return "not-regular", None
    try:
        fd = _open(name, READ_FLAGS, dir_fd=root_fd)
    except FileNotFoundError:
        return "missing", None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return "symlink", None
        return "error", exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "not-regular", None
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        return "ok", b"".join(chunks)
    except OSError as exc:
        return "error", exc
    finally:
        os.close(fd)


def negates_local_file(pattern):
    """Return True when the pattern of a "!" line re-includes CLAUDE.local.md at the root."""
    if pattern.startswith("/"):
        pattern = pattern[1:]
    elif pattern.startswith("**/"):
        pattern = pattern[3:]
    return fnmatch.fnmatchcase(LOCAL_FILE, pattern)


def ignores_local_file(data):
    """Return True when an ignore rule names CLAUDE.local.md and no later negation matches it."""
    verdict = False
    for raw in data.decode("utf-8", "replace").splitlines():
        line = raw.rstrip(" ")
        if line in IGNORE_RULES:
            verdict = True
        elif line.startswith("!") and negates_local_file(line[1:]):
            verdict = False
    return verdict


def first_difference(a, b):
    """Return the offset of the first byte where a and b differ (they must differ)."""
    for offset, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return offset
    return min(len(a), len(b))


def plural(count, word):
    return "%d %s%s" % (count, word, "" if count == 1 else "s")


def check(root, emit):
    """Run the parity check on root, emitting one line per finding and a summary line."""
    try:
        root_fd = os.open(root, ROOT_FLAGS)
    except OSError as exc:
        emit("%s: the root cannot be opened as a directory (%s)"
             % (root or "(empty path)", exc.strerror or exc))
        emit("agents-parity: CANNOT EVALUATE (the root cannot be opened as a directory)")
        return EXIT_CANNOT
    try:
        return evaluate(root_fd, emit)
    finally:
        os.close(root_fd)


def evaluate(root_fd, emit):
    results = {name: read_regular(root_fd, name) for name in NAMES + (GITIGNORE,)}
    errors = [name for name in NAMES + (GITIGNORE,) if results[name][0] == "error"]
    if errors:
        for name in errors:
            exc = results[name][1]
            emit("%s: cannot be read (%s)" % (name, exc.strerror or exc))
        emit("agents-parity: CANNOT EVALUATE (a file cannot be read)")
        return EXIT_CANNOT
    findings = []
    for name in NAMES:
        state = results[name][0]
        if state == "missing":
            findings.append("%s: missing" % name)
        elif state == "symlink":
            findings.append("%s: is a symlink; it must be a regular file" % name)
        elif state == "not-regular":
            findings.append("%s: is not a regular file" % name)
    if not findings:
        claude = results["CLAUDE.md"][1]
        agents = results["AGENTS.md"][1]
        if claude != agents:
            findings.append(
                "CLAUDE.md and AGENTS.md differ: first differing byte at offset %d; "
                "CLAUDE.md is %d bytes, AGENTS.md is %d bytes"
                % (first_difference(claude, agents), len(claude), len(agents))
            )
    state, data = results[GITIGNORE]
    if state == "missing":
        findings.append("%s: missing; it must ignore CLAUDE.local.md" % GITIGNORE)
    elif state == "symlink":
        findings.append("%s: is a symlink; it must be a regular file" % GITIGNORE)
    elif state == "not-regular":
        findings.append("%s: is not a regular file" % GITIGNORE)
    elif not ignores_local_file(data):
        findings.append("%s: does not ignore CLAUDE.local.md" % GITIGNORE)
    for line in findings:
        emit(line)
    if findings:
        emit("agents-parity: FAIL (%s)" % plural(len(findings), "finding"))
        return EXIT_FAIL
    emit(
        "agents-parity: PASS (CLAUDE.md and AGENTS.md are identical, %d bytes; "
        ".gitignore ignores CLAUDE.local.md)" % len(results["CLAUDE.md"][1])
    )
    return EXIT_PASS


def _write(root, name, data):
    with open(os.path.join(root, name), "wb") as fh:
        fh.write(data)


def _ignore(root, data=b"CLAUDE.local.md\n"):
    if data is not None:
        _write(root, GITIGNORE, data)


def _pair(claude, agents, ignore=b"CLAUDE.local.md\n"):
    def build(root):
        if claude is not None:
            _write(root, "CLAUDE.md", claude)
        if agents is not None:
            _write(root, "AGENTS.md", agents)
        _ignore(root, ignore)
        return root

    return build


def _with_symlink(link_name, target_name, target_data):
    def build(root):
        if target_data is not None:
            _write(root, target_name, target_data)
        os.symlink(target_name, os.path.join(root, link_name))
        _ignore(root)
        return root

    return build


def _agents_directory(root):
    _write(root, "CLAUDE.md", b"text\n")
    os.mkdir(os.path.join(root, "AGENTS.md"))
    _ignore(root)
    return root


def _root_is_file(root):
    _write(root, "not-a-directory", b"x\n")
    return os.path.join(root, "not-a-directory")


def _root_absent(root):
    return os.path.join(root, "absent")


def _raise_eacces(path, flags, *args, **kwargs):
    raise PermissionError(errno.EACCES, "Permission denied", path)


def _swap_at_open(name, swap, restore):
    """Return an opener that runs swap() just before opening name and restore() just after.

    It stands in for _open, so a fixture can change the tree between the lstat and the open,
    as a racing writer would.
    """
    def opener(path, flags, mode=0o777, *, dir_fd=None):
        hit = os.path.basename(path) == name
        if hit:
            swap()
        try:
            return os.open(path, flags, mode, dir_fd=dir_fd)
        finally:
            if hit:
                restore()

    return opener


_SAME = b"# Instructions\n\nSame bytes.\n"


def _race_agents(kind):
    """Replace AGENTS.md with a FIFO or a symlink to identical bytes between lstat and open."""
    def build(root):
        _pair(_SAME, _SAME)(root)
        target = os.path.join(root, "AGENTS.md")
        aside = root + "-aside.md"
        outside = root + "-outside.md"
        _write(os.path.dirname(outside), os.path.basename(outside), _SAME)

        def swap():
            os.rename(target, aside)
            if kind == "fifo":
                os.mkfifo(target)
            else:
                os.symlink(outside, target)

        def restore():
            os.unlink(target)
            os.rename(aside, target)

        return root, _swap_at_open("AGENTS.md", swap, restore)

    return build


def _race_root(root):
    """Make the root path a symlink to a different AGENTS.md after the root was opened."""
    _pair(_SAME, _SAME)(root)
    aside = root + "-aside"
    outside = root + "-outside"
    os.mkdir(outside)
    _write(outside, "AGENTS.md", b"# Different\n")

    def swap():
        os.rename(root, aside)
        os.symlink(outside, root)

    def restore():
        os.unlink(root)
        os.rename(aside, root)

    return root, _swap_at_open("AGENTS.md", swap, restore)


def _with_deadline(seconds, func):
    """Run func, raising TimeoutError if it has not returned within seconds."""
    main_thread = threading.current_thread() is threading.main_thread()
    if not hasattr(signal, "setitimer") or not main_thread:
        return func()

    def expired(signum, frame):
        raise TimeoutError("did not finish within %d seconds" % seconds)

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return func()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _main_with_failing_check(root):
    """Run main() while check() raises, and return (exit, output)."""
    global check
    saved = check

    def broken(path, emit):
        raise RuntimeError("injected failure")

    check = broken
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = main(["--root", root])
    finally:
        check = saved
    return code, out.getvalue()


def _symlinked_tools(base):
    """Build a repository whose tools/ directory is reached through a symlink elsewhere."""
    root = os.path.join(base, "repo")
    os.makedirs(os.path.join(root, "tools"))
    _pair(_SAME, _SAME)(root)
    with open(os.path.realpath(__file__), "rb") as fh:
        _write(os.path.join(root, "tools"), "check_agents_parity.py", fh.read())
    os.mkdir(os.path.join(base, "elsewhere"))
    link = os.path.join(base, "elsewhere", "tools")
    os.symlink(os.path.join(root, "tools"), link)
    return os.path.join(link, "check_agents_parity.py")


def self_test():
    """Run the self-test and return its exit status: 0 pass, 1 a failed case, 2 cannot evaluate.

    An unexpected error is reported as main() reports one and returns 2, so the entry block can
    exit with this value directly.
    """
    try:
        return run_self_test()
    except Exception as exc:
        print(
            "agents-parity: CANNOT EVALUATE (unexpected error: %s: %s)" % (type(exc).__name__, exc),
            file=sys.stderr,
        )
        return EXIT_CANNOT


def run_self_test():
    """Build fixtures in a temporary directory and check every pass, fail and cannot-evaluate path."""
    global _open
    same = _SAME
    # Each case: label, fixture builder, expected exit, text a line must contain (or None), and
    # an opener to inject (or None). A builder may return (root, opener) instead of root.
    cases = [
        ("identical files", _pair(same, same), EXIT_PASS, "identical", None),
        ("identical empty files", _pair(b"", b""), EXIT_PASS, "identical, 0 bytes", None),
        ("one byte differs", _pair(b"abcdef\n", b"abcXef\n"), EXIT_FAIL, "offset 3", None),
        (
            "trailing newline differs",
            _pair(b"text\n", b"text"),
            EXIT_FAIL,
            "offset 4; CLAUDE.md is 5 bytes, AGENTS.md is 4 bytes",
            None,
        ),
        ("AGENTS.md missing", _pair(same, None), EXIT_FAIL, "AGENTS.md: missing", None),
        ("CLAUDE.md missing", _pair(None, same), EXIT_FAIL, "CLAUDE.md: missing", None),
        ("both missing", _pair(None, None), EXIT_FAIL, "FAIL (2 findings)", None),
        (
            "AGENTS.md a symlink to CLAUDE.md",
            _with_symlink("AGENTS.md", "CLAUDE.md", same),
            EXIT_FAIL,
            "AGENTS.md: is a symlink",
            None,
        ),
        (
            "CLAUDE.md a symlink to AGENTS.md",
            _with_symlink("CLAUDE.md", "AGENTS.md", same),
            EXIT_FAIL,
            "CLAUDE.md: is a symlink",
            None,
        ),
        (
            "AGENTS.md a dangling symlink",
            _with_symlink("AGENTS.md", "absent.md", None),
            EXIT_FAIL,
            "AGENTS.md: is a symlink",
            None,
        ),
        ("AGENTS.md a directory", _agents_directory, EXIT_FAIL, "not a regular file", None),
        (
            ".gitignore missing",
            _pair(same, same, ignore=None),
            EXIT_FAIL,
            ".gitignore: missing",
            None,
        ),
        (
            ".gitignore without the rule",
            _pair(same, same, ignore=b"__pycache__/\n"),
            EXIT_FAIL,
            ".gitignore: does not ignore CLAUDE.local.md",
            None,
        ),
        (
            ".gitignore rule negated later",
            _pair(same, same, ignore=b"CLAUDE.local.md\n!CLAUDE.local.md\n"),
            EXIT_FAIL,
            ".gitignore: does not ignore CLAUDE.local.md",
            None,
        ),
        (
            ".gitignore rule negated later by a glob",
            _pair(same, same, ignore=b"CLAUDE.local.md\n!*.md\n"),
            EXIT_FAIL,
            ".gitignore: does not ignore CLAUDE.local.md",
            None,
        ),
        (
            ".gitignore rule negated later by an anchored glob",
            _pair(same, same, ignore=b"/CLAUDE.local.md\n!/CLAUDE.local.*\n"),
            EXIT_FAIL,
            ".gitignore: does not ignore CLAUDE.local.md",
            None,
        ),
        (
            ".gitignore anchored rule",
            _pair(same, same, ignore=b"__pycache__/\n/CLAUDE.local.md\n"),
            EXIT_PASS,
            "ignores CLAUDE.local.md",
            None,
        ),
        (
            "symlink swapped in before the open",
            _race_agents("symlink"),
            EXIT_FAIL,
            "AGENTS.md: is a symlink",
            None,
        ),
        (
            "FIFO swapped in before the open",
            _race_agents("fifo"),
            EXIT_FAIL,
            "AGENTS.md: is not a regular file",
            None,
        ),
        ("root swapped after it was opened", _race_root, EXIT_PASS, "identical", None),
        (
            "root a regular file",
            _root_is_file,
            EXIT_CANNOT,
            "cannot be opened as a directory",
            None,
        ),
        ("root absent", _root_absent, EXIT_CANNOT, "cannot be opened as a directory", None),
        ("read error", _pair(same, same), EXIT_CANNOT, "cannot be read", _raise_eacces),
    ]
    failures = 0
    total = 0

    def report(ok, label, detail):
        nonlocal failures, total
        total += 1
        if not ok:
            failures += 1
        print("%s %s: %s" % ("PASS" if ok else "FAIL", label, detail))

    def outcome(expected, got, needle, text):
        detail = "expected exit %d, got %d" % (expected, got)
        found = needle is None or needle in text
        if not found:
            detail += "; no line contains %r" % needle
        return got == expected and found, detail

    try:
        with tempfile.TemporaryDirectory(prefix="agents-parity-") as tmp:
            for index, (label, build, expected, needle, inject) in enumerate(cases):
                case_dir = os.path.join(tmp, "case%02d" % index)
                os.mkdir(case_dir)
                built = build(case_dir)
                root, opener = built if isinstance(built, tuple) else (built, inject)
                lines = []
                if opener is not None:
                    _open = opener
                try:
                    got = _with_deadline(CASE_SECONDS, lambda: check(root, lines.append))
                except Exception as exc:
                    report(False, label, "raised %s: %s" % (type(exc).__name__, exc))
                    continue
                finally:
                    _open = os.open
                ok, detail = outcome(expected, got, needle, "\n".join(lines))
                report(ok, label, detail)

            for version, expected in (((3, 13, 9), 2), ((3, 14, 0), 0), ((3, 15, 1), 0)):
                got = python_gate(version)
                label = "Python %d.%d.%d gate" % version
                report(got == expected, label, "expected exit %d, got %d" % (expected, got))

            case_dir = os.path.join(tmp, "unexpected")
            os.mkdir(case_dir)
            try:
                got, text = _main_with_failing_check(case_dir)
                ok, detail = outcome(EXIT_CANNOT, got, "unexpected error", text)
            except Exception as exc:
                ok, detail = False, "raised %s: %s" % (type(exc).__name__, exc)
            report(ok, "unexpected error exits 2", detail)

            # Run the tool as a separate process to cover argument handling and the exit status.
            tool = os.path.realpath(__file__)
            cli_cases = [
                ("command line, identical files", _pair(same, same), [], EXIT_PASS, "PASS"),
                ("command line, files differ", _pair(same, same + b"x"), [], EXIT_FAIL, "FAIL"),
                (
                    "command line, root a regular file",
                    _root_is_file,
                    [],
                    EXIT_CANNOT,
                    "CANNOT EVALUATE",
                ),
                (
                    "command line, unknown option",
                    _pair(same, same),
                    ["--unknown"],
                    EXIT_CANNOT,
                    "unrecognized arguments",
                ),
                (
                    "command line, --self-test with --root",
                    _pair(same, same),
                    ["--self-test"],
                    EXIT_CANNOT,
                    "--self-test does not take --root",
                ),
            ]
            for index, (label, build, extra, expected, needle) in enumerate(cli_cases):
                case_dir = os.path.join(tmp, "cli%02d" % index)
                os.mkdir(case_dir)
                root = build(case_dir)
                command = [sys.executable, "-I", "-B", tool, "--root", root]
                proc = subprocess.run(
                    command + extra,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=60,
                )
                text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode(
                    "utf-8", "replace"
                )
                ok, detail = outcome(expected, proc.returncode, needle, text)
                report(ok, label, detail)

            case_dir = os.path.join(tmp, "cli-symlinked-tools")
            os.mkdir(case_dir)
            linked_tool = _symlinked_tools(case_dir)
            proc = subprocess.run(
                [sys.executable, "-I", "-B", linked_tool],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=60,
            )
            text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            ok, detail = outcome(EXIT_PASS, proc.returncode, "agents-parity: PASS", text)
            report(ok, "command line, default root through a symlinked tools directory", detail)
    except (OSError, subprocess.SubprocessError) as exc:
        print("agents-parity self-test: CANNOT EVALUATE (%s)" % exc)
        return EXIT_CANNOT

    if failures:
        print("agents-parity self-test: FAIL (%d of %d cases failed)" % (failures, total))
        return EXIT_FAIL
    print("agents-parity self-test: PASS (%d of %d cases)" % (total, total))
    return EXIT_PASS


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Check that CLAUDE.md and AGENTS.md are byte-identical regular files.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root (default: the parent of this tool's directory)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="build fixtures in a temporary directory and check every exit path",
    )
    args = parser.parse_args(argv)
    if args.self_test and args.root is not None:
        parser.error("--self-test does not take --root")
    try:
        if args.self_test:
            return self_test()
        root = args.root if args.root is not None else default_root()
        return check(root, print)
    except Exception as exc:
        print(
            "agents-parity: CANNOT EVALUATE (unexpected error: %s: %s)" % (type(exc).__name__, exc),
            file=sys.stderr,
        )
        return EXIT_CANNOT


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    sys.exit(main())
