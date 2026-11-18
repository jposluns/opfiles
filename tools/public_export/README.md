# The public export

The maintainer ruled that all files go to the public repository
(https://github.com/jposluns/opfiles), which holds this repository's tree at its root with the
same paths (spec/, tools/, enforcement/, prompt-pack/, site/, LICENSE, NOTICE, README.md and the
rest). This directory holds the machinery that builds that tree and the record its names check
reads; it ships with everything else.

## What the export is

`export_public.py` builds the public tree deterministically from the committed HEAD of this
repository: the whole tracked tree, every file tracked at HEAD, with no exclusion set. CLAUDE.md,
AGENTS.md, .claude/, .aiqt/, the PROVENANCE records, RELEASING.md, the workflow and this directory
itself all ship. It reads the file list, each git mode and every byte from git's objects (git
ls-tree -r HEAD and git cat-file), never from the index or the work tree, so two builds from the
same commit are identical. It preserves each file's mode (0644, or 0755 for a 100755 entry),
refuses symlinks and submodules, and writes a manifest beside the tree: one line per file, path,
git mode and SHA-256 of the bytes, tab separated and sorted by path.

Build it with:

    python3 -I -B tools/public_export/export_public.py --output /tmp/opfiles-public

The manifest defaults to the output path with `.manifest` appended; `--manifest FILE` names
another place, which must lie outside the output directory.

## The gate

`tools/check_public_export.py`, registered as public-export in tools/run_all_checks.sh, rebuilds
the export into a temporary directory on every run and fails unless the built tree is exactly the
whole tracked tree of HEAD, every file is byte-identical to its blob at HEAD with its git mode's
executable bit, nothing is a symlink or any other non-regular file, the manifest matches the
tree, and no tracked path holds a directory component the names scan skips (so the scan's file
census is exactly the export; it reads the scanner's one literal SKIP_DIRS assignment in
tools/check_names.py at HEAD, and cannot evaluate unless there is exactly one, a non-empty
literal set of names on one line; any other skip logic in check_names.py, such as a later
SKIP_DIRS |= or SKIP_DIRS.add or a further filter in its listed_paths, is not read and must be
mirrored in the gate). It then runs the names scan over the built tree with the same
denylist machinery as tools/check_names.py (the built tree's own copy of that gate), with
GIT_CEILING_DIRECTORIES set to its temporary directory so the scan walks the built tree itself
and can never read an enclosing repository's view of it: the public tree is held to the same
no-names rule as this repository.

`carve-out.toml` is the decision 35 record: the functional names of plan.md section 4 item 11
(the decision 32 D4 footer, the security contact, the digest anchor, repository links and the
attribution wording) that the maintainer allows in the public tree. The gate reads the record
from HEAD, the commit the verdict is about, so an uncommitted edit of it cannot change a verdict.
An entry with a lines list of [line, sha256] pairs covers findings only on those lines, whatever
their number, and pins each listed line's content (the SHA-256 of its bytes at HEAD); the gate
compares every content pin on every run that reaches the comparison, in both modes, and records
each mismatch before the names scan runs, so a run whose names scan cannot evaluate still names
it above its CANNOT EVALUATE error; a run that cannot evaluate earlier (a malformed carve-out
record or skip list, an export that does not build, or a git failure) compares nothing. No run
passes unless every content pin matches, so any edit to a listed line blocks a pass until it is
deliberately re-pinned. An entry with a matches list of [denylist entry, count] pairs makes
the gate fail unless each pinned denylist entry is reported exactly its pinned number of times in
its file and no unpinned entry is reported there at all. Exactly this is caught: a finding in a
file no entry names, a finding on an unlisted line, any change to a listed line (a name added to
a listed line fails, whatever denylist entry it matches, and so does a same-line swap between
denylist entries), a per-denylist-entry count change or an unpinned denylist entry under a
matches list (a single swap to an unpinned denylist entry, or one that changes a pinned entry's
count, fails), a path match, an email address and a home-directory path. Exactly this is not
caught. Under lines, nothing on a listed line can change without failing; a change of the
denylist itself that changes the findings on an unchanged listed line passes. Under matches, the
gate does not catch any change that keeps every pinned denylist entry's count in the file and
adds no unpinned entry, including moving a finding to another line, replacing a name with other
text matching the same entry, and reciprocal swaps between pinned entries (another match of an
entry already reported on that line keeps the count too, since the scan reports one finding per
line and denylist entry); such edits rest on review. The match count pins are compared only when
the scan reports a finding, so a scan reporting no finding at all leaves them unchecked; that
residual is accepted, since it means nothing forbidden would be published. A wrong match pin
fails the gate whenever the scan reports any finding; the first full local gate run that reports
a finding reports every mismatch, and the maintainer re-pins the record from that output. The
record's header states how the current pins were established: the content pins from the
committed bytes, the match pins as placeholders not yet observed. On the maintainer's host the
full gate run reports no names-scan finding, so the match pins are not exercised there.

The full gate needs the local denylist, so the hosted --ci run lists public-export as NOT RUN and
runs public-export-ci-subset instead: the structural checks in full, and the names checks that
need no denylist, the same split the runner makes for the names gate; no match count pin is
compared in --ci, where the denylist scan does not run, but the line content pins are. The
authoritative names run stays the full local gate run on the exact head. public-export-self-test
(`check_public_export.py --self-test`) builds its own repositories and shows each failure caught:
an extra path, a missing path, a tracked governance path an exporter wrongly leaves out, a
changed byte, a symlink, a non-regular file, a manifest mismatch, a lost executable bit, an
uncovered name, a finding on a line its entry does not list, a listed line's content change (a
name of another denylist entry added, another match of the entry already on it, a same-line swap
between denylist entries, and the same in --ci), a wrong content pin when the scan reports no
finding, a match count above and below an entry's pin, a count-neutral swap of a covered name to
another denylist entry, an unpinned denylist entry added alone under a matches list, a stale
carve-out entry, a tracked path the names scan would skip (under the default skip list and under
a skip name added to the scanner's SKIP_DIRS), and an edited listed line named by its content pin
when the names scan cannot evaluate. It also shows that an uncommitted carve-out edit does not
change the verdict; pins the documented residuals as passing cases (under lines, a denylist
change that adds a finding on an unchanged listed line; under matches, a reciprocal swap between
two pinned entries, a finding moved to another line, a name replaced by other text matching the
same entry, and another match of an entry already reported on that line; and a scan reporting no
finding, which leaves a wrong match pin unchecked); shows in process that the skip-list read and
the lines pin format fail closed; and fails unless every finding kind went red in at least one
case.

## How the public repository is updated

New commits only, never private history:

1. Build the export from a merged opfiles_private main head: a clean clone of opfiles_private at
   the merged commit, with the full local gate run green on that exact head, then
   `python3 -I -B tools/public_export/export_public.py --output <dir>` there.
2. Clone https://github.com/jposluns/opfiles and create a branch.
3. Replace the public working tree with the export output: remove every tracked file from the
   branch's working tree (never .git), copy the built tree in, and `git add -A`, so deletions and
   mode changes land too.
4. Commit on the branch and open a pull request in the public repository; merge it behind that
   repository's gates. The export carries every input those gates need (the runner, the workflow,
   the governance files, .aiqt/ and this directory), so the public repository's own --ci run can
   pass on the exported tree.

Only commits made this way are ever pushed to the public repository. Never push a branch,
a commit or any history of opfiles_private: the private history holds operational material and
a push would publish it permanently. The manifest travels with the review, so the reviewer can
hold the pull request to the built tree byte for byte.
