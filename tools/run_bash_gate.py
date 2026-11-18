"""Run one of the bash gate scripts of this directory, for tools/run_all_checks.sh.

Usage:
  python3 -I -B tools/run_bash_gate.py SCRIPT [ARGUMENT...]

Every gate of tools/run_all_checks.sh is registered as one `run_gate NAME python3 -I -B ...` line.
That is the registration shape the imported OPF registration self-tests read as the runner's roster
(tools/_opf_pack_manifest.py, tools/check_opf_init_p0.py and tools/_opf_adopt_observe.py): they run
the runner with a python3 fixture first on PATH that answers every registered gate except their own,
and they refuse any run_gate line that is not a python3 launch. A bash gate (the secrets gate and the
tests of the runner and of the two CI helpers) therefore runs through this launcher, so that inside
those fixtures it is answered like every other gate instead of running for real.

SCRIPT is the file name, with no directory part, of a regular file ending in .sh in this tool's own
directory; a symlink is refused. The launcher replaces itself with bash (found on PATH) running that
script with the remaining arguments, so the gate's output and exit status are the script's. Python
ignores SIGPIPE and SIGXFSZ (and SIGXFZ, where the platform defines it) at startup, and an exec keeps
an ignored signal ignored, so the launcher sets each of them back to its default action just before
the exec, as subprocess does with restore_signals. The script therefore runs with the default action
for those signals, whatever its parent had set for them: a writer into a closed pipe is stopped by
SIGPIPE (a pipeline status of 141) instead of getting an error.

Exit status: the script's own; 2 when the command line is invalid, SCRIPT is not such a file, bash is
not on PATH, or Python is older than 3.14. Only the standard library is used.
"""

import sys

MIN_PYTHON = (3, 14)
TOOL = "run_bash_gate"


def python_gate(version):
    """Return 2 when the given version is older than the floor, else 0."""
    return 2 if tuple(version[:2]) < MIN_PYTHON else 0


if __name__ == "__main__" and python_gate(sys.version_info) != 0:
    print(
        "%s: Python 3.14 or newer is required; this is Python %d.%d"
        % (TOOL, sys.version_info[0], sys.version_info[1]),
        file=sys.stderr,
    )
    sys.exit(2)

import os  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import stat  # noqa: E402

# The signals Python ignores at startup; SIGXFZ is defined on few platforms.
STARTUP_IGNORED = ("SIGPIPE", "SIGXFZ", "SIGXFSZ")


def restore_signals():
    """Set every signal of STARTUP_IGNORED that this platform defines back to its default action."""
    for name in STARTUP_IGNORED:
        number = getattr(signal, name, None)
        if number is not None:
            signal.signal(number, signal.SIG_DFL)


def script_path(name, directory):
    """The path of the bash gate script NAME in DIRECTORY, or None when NAME is not the plain file
    name of a regular, non-symlink file ending in .sh there."""
    if (not name.endswith(".sh") or name.startswith(".") or "/" in name or "\0" in name
            or os.sep in name):
        return None
    path = os.path.join(directory, name)
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return path if stat.S_ISREG(info.st_mode) else None


def main(argv):
    if not argv:
        print("usage: python3 -I -B tools/run_bash_gate.py SCRIPT [ARGUMENT...]", file=sys.stderr)
        return 2
    directory = os.path.dirname(os.path.realpath(__file__))
    path = script_path(argv[0], directory)
    if path is None:
        print("%s: not a bash gate script of %s: %r" % (TOOL, directory, argv[0]), file=sys.stderr)
        return 2
    bash = shutil.which("bash")
    if bash is None:
        print("%s: bash is not on PATH" % TOOL, file=sys.stderr)
        return 2
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        restore_signals()
        os.execv(bash, [bash, path, *argv[1:]])
    except OSError as exc:
        print("%s: cannot run bash: %s" % (TOOL, exc.strerror or exc), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
