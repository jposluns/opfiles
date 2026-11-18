#!/usr/bin/env python3
"""Build the public OPFiles tree from the committed HEAD of this repository.

Usage:
  python3 tools/public_export/export_public.py --output DIR [--manifest FILE] [--root PATH]

The maintainer ruled that every file goes to the public repository
(https://github.com/jposluns/opfiles), so the export is the whole tracked tree of HEAD: every
tracked file, with no exclusion set (CLAUDE.md, AGENTS.md, .claude/, .aiqt/, the PROVENANCE
records, RELEASING.md, the workflow and tools/public_export/ itself all ship). The gate
tools/check_public_export.py rebuilds this export and checks it against HEAD, so this tool and
the gate must stay in step.

The export reads only committed content: the file list, each path's git mode and each blob id
come from git ls-tree -r HEAD, and every byte from git cat-file. The index and the work tree are
never read (git ls-files lists the index, so it is not used), so the output is a function of the
HEAD commit alone and two builds from the same commit write identical trees and manifests.

Modes are preserved: a 100644 entry is written with mode 0644 and a 100755 entry with mode 0755.
A symlink (120000) or a submodule (160000) anywhere in the committed tree is refused with exit 2,
as is any other mode: the public tree holds regular files only. A path that is not valid UTF-8,
is not a normalized relative path, or holds a control character or tab is refused too, so every
manifest line is well formed.

The manifest is one line per exported file, "<path>\\t<mode>\\t<sha256>\\n" (the git mode and the
SHA-256 of the file's bytes), sorted by path. It is written to --manifest (default: the output
directory's path with ".manifest" appended) and must lie outside the output directory, so the
built tree holds exactly the exported files.

The output directory must not exist yet, or be an empty directory.

git runs with PATH and HOME from the caller and no other variable of the caller's environment,
reads neither its system nor its global configuration, ignores replace refs and does not fetch a
missing object in a partial clone, as tools/check_line_width.py runs it.

Exit: 0 the tree and the manifest were written; 2 anything else (nothing was fully built).
"""
import argparse
import hashlib
import os
import subprocess
import sys

TOOL = "export_public"
# No exclusion set: the maintainer ruled that every file tracked at HEAD ships. Keep this tool in
# step with tools/check_public_export.py, which recomputes the tracked tree on its own.
# The git modes a public file may have, and the filesystem mode each is written with.
FILE_MODES = {"100644": 0o644, "100755": 0o755}
GIT = "git"
GIT_TIMEOUT = 300
# git's environment: of the caller's variables only these are kept, and GIT_ENV_SET is added, as
# in tools/check_line_width.py, so no caller setting redirects what git reads.
GIT_ENV_KEEP = ("PATH", "HOME")
GIT_ENV_SET = {"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
               "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
EXIT_OK = 0
EXIT_ERROR = 2


class CannotExport(Exception):
    """Raised when the export cannot be built; main prints it and exits 2."""


def git_env(source=None):
    """Return the environment git runs in: GIT_ENV_KEEP of source (default os.environ), and
    GIT_ENV_SET."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items() if key in GIT_ENV_KEEP}
    env.update(GIT_ENV_SET)
    return env


def run_git(root, env, args, what, data=None):
    """Run git in root and return its stdout bytes, or raise CannotExport naming what failed."""
    try:
        proc = subprocess.run([GIT, "-C", root] + list(args), input=data,
                              stdin=None if data is not None else subprocess.DEVNULL,
                              capture_output=True, env=env, timeout=GIT_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotExport("git could not be run to %s (%s)" % (what, exc)) from None
    if proc.returncode != 0:
        raise CannotExport("git failed to %s (exit %d: %s)" % (
            what, proc.returncode, proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout


def path_problem(path):
    """Return why a tracked path cannot be exported, or None when it can."""
    if not path or path.startswith("/") or "\\" in path:
        return "is not a relative POSIX path"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in path):
        return "holds a control character or tab, which the manifest format refuses"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "is not a normalized relative path"
    return None


def head_entries(root, env):
    """Return [(path, git mode, blob id)] for every exportable file at HEAD, sorted by path.

    Raise CannotExport for a symlink, a submodule, any other unsupported mode, a path that is
    not valid UTF-8 or not exportable, or a listing this parser does not understand.
    """
    out = run_git(root, env, ["ls-tree", "-z", "-r", "--full-tree", "HEAD"],
                  "list the committed tree of HEAD")
    entries = []
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _sep, raw = record.partition(b"\t")
        fields = meta.split(b" ")
        if len(fields) != 3 or not raw:
            raise CannotExport("unexpected git ls-tree record: %r" % record[:200])
        try:
            mode = fields[0].decode("ascii")
            kind = fields[1].decode("ascii")
            blob = fields[2].decode("ascii")
            path = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CannotExport("a tracked path or entry is not decodable: %s" % exc) from None
        if mode == "120000":
            raise CannotExport("%s is a symlink at HEAD; the export refuses symlinks" % path)
        if mode == "160000" or kind == "commit":
            raise CannotExport("%s is a submodule at HEAD; the export refuses submodules" % path)
        if kind != "blob" or mode not in FILE_MODES:
            raise CannotExport("%s has mode %s (%s), which the export does not support"
                               % (path, mode, kind))
        problem = path_problem(path)
        if problem is not None:
            raise CannotExport("the tracked path %r %s" % (path, problem))
        entries.append((path, mode, blob))
    if not entries:
        raise CannotExport("HEAD holds no exportable file")
    entries.sort()
    return entries


def read_blobs(root, env, blobs):
    """Return {blob id: bytes} for every blob id in blobs, through one git cat-file --batch run.

    subprocess.run writes the requests and reads the replies concurrently, so one batch of any
    size cannot deadlock on the pipes.
    """
    unique = sorted(set(blobs))
    request = "".join(blob + "\n" for blob in unique).encode("ascii")
    out = run_git(root, env, ["cat-file", "--batch"], "read the blobs of HEAD", data=request)
    contents = {}
    position = 0
    for blob in unique:
        try:
            newline = out.index(b"\n", position)
        except ValueError:
            raise CannotExport("git cat-file ended before the reply for blob %s" % blob) from None
        header = out[position:newline].decode("ascii", "replace").split(" ")
        if len(header) != 3 or header[0] != blob or header[1] != "blob":
            raise CannotExport("git cat-file did not return blob %s (got: %s)"
                               % (blob, " ".join(header)))
        try:
            size = int(header[2])
        except ValueError:
            raise CannotExport("git cat-file reported a non-numeric size for blob %s" % blob) \
                from None
        start = newline + 1
        end = start + size
        if out[end:end + 1] != b"\n":
            raise CannotExport("git cat-file's reply for blob %s is truncated" % blob)
        contents[blob] = out[start:end]
        position = end + 1
    return contents


def prepare_output(output):
    """Create output, or require it to be an existing empty directory (never a symlink)."""
    if os.path.lexists(output):
        if os.path.islink(output) or not os.path.isdir(output):
            raise CannotExport("the output path %s exists and is not a directory" % output)
        if os.listdir(output):
            raise CannotExport("the output directory %s is not empty" % output)
    else:
        try:
            os.makedirs(output)
        except OSError as exc:
            raise CannotExport("cannot create the output directory %s (%s)"
                               % (output, exc)) from None


def build(root, output, manifest_path):
    """Build the export of root's HEAD into output and write the manifest; return
    (HEAD commit, file count, executable count)."""
    env = git_env()
    head = run_git(root, env, ["rev-parse", "--verify", "HEAD^{commit}"],
                   "resolve HEAD").decode("ascii").strip()
    entries = head_entries(root, env)
    contents = read_blobs(root, env, [blob for _path, _mode, blob in entries])
    real_output = os.path.realpath(output)
    real_manifest = os.path.realpath(manifest_path)
    if real_manifest == real_output or real_manifest.startswith(real_output + os.sep):
        raise CannotExport("the manifest %s lies inside the output directory" % manifest_path)
    prepare_output(output)
    lines = []
    for path, mode, blob in entries:
        data = contents[blob]
        target = os.path.join(output, *path.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
        os.chmod(target, FILE_MODES[mode])
        lines.append("%s\t%s\t%s\n" % (path, mode, hashlib.sha256(data).hexdigest()))
    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    executables = sum(1 for _path, mode, _blob in entries if mode == "100755")
    return head, len(entries), executables


def default_root():
    """Return the repository root: two directories above this tool's own directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description="Build the public OPFiles tree from the committed HEAD.")
    parser.add_argument("--output", required=True,
                        help="directory to build the public tree in (new, or an empty directory)")
    parser.add_argument("--manifest", default=None,
                        help="manifest file to write (default: the output path plus .manifest)")
    parser.add_argument("--root", default=None,
                        help="repository root (default: two directories above this tool's own)")
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else default_root()
    manifest = args.manifest if args.manifest is not None else args.output.rstrip("/") + ".manifest"
    try:
        head, count, executables = build(root, args.output, manifest)
    except CannotExport as exc:
        print("%s: ERROR: %s" % (TOOL, exc))
        return EXIT_ERROR
    except Exception as exc:  # fail closed: a half-written tree must never read as built
        print("%s: ERROR: unexpected error: %s: %s" % (TOOL, type(exc).__name__, exc))
        return EXIT_ERROR
    print("%s: wrote %d files (%d executable) from HEAD %s to %s; manifest %s"
          % (TOOL, count, executables, head[:12], args.output, manifest))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
