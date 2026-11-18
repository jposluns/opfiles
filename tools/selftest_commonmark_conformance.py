#!/usr/bin/env python3
"""CommonMark 0.31.2 conformance replay against the vendored Marko (OPF U5).

Renders every official CommonMark 0.31.2 spec example with the vendored marko and compares the output to
the spec's expected HTML, so a substituted or drifted parser that changes which examples diverge shows up
as a change in the divergence set.
This is a SEPARATE harness from the parse-only gate path: it deliberately renders HTML (via a fresh
marko.Markdown()) to compare against the spec, which the gate adapter never does. The replay loads marko
through the adapter's containment and version check; the byte integrity of the vendored Marko tree is the
manifest check of the commonmark-headings self-test, not this replay.

The spec example fixture (the CommonMark 0.31.2 examples JSON, a list of {markdown, html, example, ...}) is
an ORCHESTRATOR DEPENDENCY: it is acquired and vendored by the orchestrator at the path named below. This
harness FAILS CLOSED (never skips) if the fixture is absent, unreadable, not a regular file, changed from
its pinned bytes, not the imported fixture, malformed, or empty (check-fails-closed-on-unreadable;
guard-input-soundness).

Fixture byte pin: SPEC_FIXTURE_SHA256 and SPEC_FIXTURE_SIZE below pin the exact bytes of the fixture. They
are checked on the raw bytes BEFORE the JSON is parsed, so an edit the structural checks cannot see (a
re-serialization, an edit to a field the replay never reads, or an edit to the expected HTML of an example
that stays divergent) is a fail-closed error. The pin is anchored to the import record, also before the JSON
is parsed: the fixture's git blob id must equal the blob of its entry in PROVENANCE-inventory.json, that
entry's sha256 must equal SPEC_FIXTURE_SHA256, and the inventory must hold no deviation record for the
fixture. tools/check_provenance_deviations.py ties the entry blobs to the imported tree (source_opf_tree
and the PROVENANCE.md "Source `opf/` tree object" line), so a change that rewrites the fixture and
SPEC_FIXTURE_SHA256 together is refused here. Residual: the pin was measured from the committed fixture on
2026-11-16 and equals the as-imported SHA-256 that PROVENANCE-inventory.json records for this path; it was
NOT compared with the upstream CommonMark 0.31.2 release (no network was available), so it proves the bytes
are unchanged since the import, not that they equal upstream. The import record sits in the same tree, so a
change that also forges it (the fixture's entry, source_opf_tree, the PROVENANCE.md tree line and the
inventory pin) passes, and so does a fixture built to collide with the imported SHA-1 blob id once
SPEC_FIXTURE_SHA256 (and SPEC_FIXTURE_SIZE when the length differs), the entry's sha256, the blob and
sha256 of this file's deviation record and the inventory pin are rewritten to match; the
provenance-deviations gate discloses both and says to review any such edit as a re-import.

Usage:
    python3 -I -B opf/tools/selftest_commonmark_conformance.py
        Run the replay under the CURRENT interpreter. Exit 0 clean, 1 on a divergence outside the recorded
        baseline, 2 on a fail-closed harness error (missing or changed fixture, wrong vendored marko, etc.).
    python3 -I -B opf/tools/selftest_commonmark_conformance.py --self-test
        Run only the harness self-check (no rendering), including the fixture byte pin rows. Exit 0 clean,
        2 on a self-check regression.
    python3 -I -B opf/tools/selftest_commonmark_conformance.py --interpreters <interp> [<interp> ...]
        OPTIONAL maintainer facility (NOT gate-wired): re-spawn this same harness under each NAMED interpreter
        and aggregate. A named interpreter that is absent is a fail-closed error, not a skip. The pack is
        standardized on CPython 3.14 and the gate uses the single-interpreter form above; a cross-version
        matrix was declined by the maintainer (2026-09-10).
"""
import sys

if tuple(sys.version_info[:2]) < (3, 14):
    import os
    try:
        sys.stderr.write(
            "error: selftest_commonmark_conformance.py requires Python 3.14 or newer; this is Python %d.%d.%d (%s). "
            "Nothing was run (cannot evaluate).\n"
            % (tuple(sys.version_info[:3]) + (sys.executable or "unknown interpreter",)))
        sys.stderr.flush()
    except BaseException:
        pass
    os._exit(2)

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _commonmark_headings as ch        # noqa: E402  reuse the pinned, containment-checked marko loader

# Named fixture path (orchestrator-vendored). The harness reads ONLY this path and fails closed if absent.
SPEC_FIXTURE = os.path.join(ch._VENDOR_DIR, "commonmark-spec-0.31.2", "spec-0.31.2-examples.json")

# The byte pin of SPEC_FIXTURE, checked on the raw bytes before parsing (see the module docstring for where
# the value comes from and what it does not prove). Any other length or SHA-256 is a fail-closed error.
SPEC_FIXTURE_SHA256 = "d431b29d97b6f73e69d547109cf5081578fac931e72afe95639ebe766c1b2a20"
SPEC_FIXTURE_SIZE = 140487
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")

# The import record the pin is anchored to (PROVENANCE-inventory.json at the OPF root, two levels above
# tools/_vendor) and the fixture's path in it.
_OPF_ROOT = os.path.dirname(os.path.dirname(ch._VENDOR_DIR))
SPEC_INVENTORY = os.path.join(_OPF_ROOT, ch.INVENTORY_NAME)
SPEC_FIXTURE_REL = os.path.relpath(SPEC_FIXTURE, _OPF_ROOT).replace(os.sep, "/")
FIFO_PROBE_SECONDS = 20                   # the FIFO self-check row's child is killed after this long

# The set of spec example numbers marko 2.2.4 is known to render differently from the 0.31.2 expected HTML.
# ORCHESTRATOR-FILLED after MEASURING the replay against the real vendored bytes. Measured on CPython 3.14.4
# (the host interpreter) against the vendored marko 2.2.4 bytes: 16 render divergences out of 652 examples,
# none heading-related. The OPF changelog adapter (opf/tools/_commonmark_headings.py) uses marko's PARSER only,
# never its renderer, so none of these divergences touches OPF heading extraction; they are recorded here to
# keep the conformance replay honest rather than presenting an unmeasured 100%-pass claim as fact. This
# baseline is verified on CPython 3.14 ONLY: the host and the quality CI workflow that gates U5 both run it on
# 3.14, and a cross-version 3.12+3.14 matrix was declined by the maintainer (2026-09-10) as backward. The
# replay fails closed when the observed divergence SET (which examples diverge) is not exactly this set, so a
# re-vendoring or a 3.14 change that moves any example into or out of divergence is caught; a change to an
# already-divergent example's OUTPUT that leaves it divergent is a disclosed residual the set comparison does
# not see. marko is pure-Python with no version-gated rendering
# path; should a specific older interpreter ever matter, the --interpreters facility can re-measure it.
# Divergence classes: tabs (9), paragraphs
# (226), list items (280-284, 294, 296), lists (307, 315, 319-321, 323), hard line breaks (645).
KNOWN_DIVERGENT_EXAMPLES = frozenset({9, 226, 280, 281, 282, 283, 284, 294, 296, 307, 315, 319, 320, 321, 323, 645})

# A sanity floor so a truncated fixture cannot pass as a clean run. ORCHESTRATOR-PINNED to the exact example
# count of the committed 0.31.2 fixture; None here means "require at least one and print the count to pin".
EXPECTED_EXAMPLE_COUNT = 652  # CommonMark 0.31.2 spec.json example count (measured from the vendored fixture)


def _fixture_bytes_problem(data, expected_sha256=SPEC_FIXTURE_SHA256, expected_size=SPEC_FIXTURE_SIZE):
    """None when `data` (bytes) has exactly the pinned length and SHA-256, else a one-line description of
    the mismatch. The length is compared first only to give a clearer message; the SHA-256 decides."""
    if len(data) != expected_size:
        return "{} bytes, the pin is {} bytes".format(len(data), expected_size)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        return "sha256 {}, the pin is {}".format(actual, expected_sha256)
    return None


def _fixture_import_problem(data, inventory_path=None, rel=SPEC_FIXTURE_REL,
                            expected_sha256=SPEC_FIXTURE_SHA256):
    """None when `data` (bytes) is the fixture the import recorded, else a one-line description. The
    inventory at `inventory_path` (SPEC_INVENTORY by default) must be UTF-8 JSON (no duplicate key, NaN or
    Infinity) with entries and deviations lists; exactly one entry must name `rel`, its sha256 must equal
    `expected_sha256` (the pin) and its blob the git blob id of `data`; and no deviation record may name
    `rel`. The blob is compared because only blob ids feed the tree id the deviations gate ties to the
    import."""
    inventory_path = SPEC_INVENTORY if inventory_path is None else inventory_path
    try:
        with open(inventory_path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        return "the import record {} is absent or unreadable: {}".format(inventory_path, exc)
    try:
        inventory = json.loads(raw.decode("utf-8"), object_pairs_hook=ch._refuse_duplicate_keys,
                               parse_constant=ch._refuse_json_constant)
    except ValueError as exc:
        return "the import record {} is not UTF-8 JSON: {}".format(inventory_path, exc)
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    deviations = inventory.get("deviations") if isinstance(inventory, dict) else None
    if not isinstance(entries, list) or not isinstance(deviations, list):
        return "the import record {} has no entries or deviations list".format(inventory_path)
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("path") == rel]
    if len(matches) != 1:
        return "the import record has {} entries for {}, expected exactly 1".format(len(matches), rel)
    entry = matches[0]
    if entry.get("sha256") != expected_sha256:
        return "the import record's sha256 for {} is {!r}, the pin is {}".format(
            rel, entry.get("sha256"), expected_sha256)
    blob = ch.git_blob_id(data)
    if entry.get("blob") != blob:
        return "git blob id {}, the import record's blob for {} is {!r}".format(blob, rel, entry.get("blob"))
    if any(isinstance(record, dict) and record.get("path") == rel for record in deviations):
        return "the import record has a deviation record for {}; the fixture must be the imported one".format(
            rel)
    return None


def _read_fixture_bytes(path):
    """The raw bytes of the fixture at `path`, read at most SPEC_FIXTURE_SIZE + 1 bytes so an oversized
    file is seen without reading all of it. Raises RuntimeError when the path is absent, unreadable, or not
    a regular file (a FIFO is opened non-blocking so it cannot hang the gate). Self-check rows cover the
    read cap, a directory and a FIFO with no writer."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        raise RuntimeError("spec fixture {} is absent or unreadable: {}".format(path, exc))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("spec fixture {} is not a regular file".format(path))
        with os.fdopen(fd, "rb") as handle:
            fd = None
            return handle.read(SPEC_FIXTURE_SIZE + 1)
    except OSError as exc:
        raise RuntimeError("spec fixture {} is unreadable: {}".format(path, exc))
    finally:
        if fd is not None:
            os.close(fd)


def _load_examples(path=None, inventory_path=None):
    """Load and validate the spec example fixture (SPEC_FIXTURE unless `path` is given, and against the
    import record SPEC_INVENTORY unless `inventory_path` is given; only the self-check gives either). Fails
    closed (HeadingScanError-style RuntimeError) on an absent, unreadable or non-regular fixture, one whose
    bytes are not the pinned bytes or not the imported fixture (both checked before parsing), or a malformed
    or empty fixture, or one whose records lack the required keys."""
    path = SPEC_FIXTURE if path is None else path
    raw = _read_fixture_bytes(path)
    problem = _fixture_bytes_problem(raw)
    if problem is not None:
        raise RuntimeError("spec fixture {} does not match its pinned bytes ({})".format(path, problem))
    problem = _fixture_import_problem(raw, inventory_path)
    if problem is not None:
        raise RuntimeError("spec fixture {} does not match its import record ({})".format(path, problem))
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("spec fixture {} is not valid UTF-8 JSON: {}".format(path, exc))
    if not isinstance(data, list) or not data:
        raise RuntimeError("spec fixture {} is empty or not a list".format(path))
    for i, ex in enumerate(data):
        if not isinstance(ex, dict) or "markdown" not in ex or "html" not in ex:
            raise RuntimeError("spec fixture record {} is malformed (needs markdown + html keys)".format(i))
    if EXPECTED_EXAMPLE_COUNT is not None and len(data) != EXPECTED_EXAMPLE_COUNT:
        raise RuntimeError("spec fixture has {} examples, expected {}".format(len(data), EXPECTED_EXAMPLE_COUNT))
    return data


def _classify(examples, renderer):
    """Render each example and classify it. Returns (divergent, crashed, seen). A render CRASH is recorded
    SEPARATELY from an output DIFFERENCE so a crash can never be absorbed into the known-divergent baseline;
    `seen` is every evaluated example id, for the fixture-identity check. Extracted so _self_check can
    exercise the crash-never-absorbed and identity logic on synthetic input (change-carries-a-check)."""
    divergent, crashed, seen = [], [], []
    for ex in examples:
        number = ex.get("example")
        seen.append(number)
        try:
            rendered = renderer.convert(ex["markdown"])
        except Exception as exc:          # a render crash is a hard failure, NOT a recorded divergence
            crashed.append((number, "render error: {}".format(exc)))
            continue
        if rendered != ex["html"]:
            divergent.append((number, "output differs from expected"))
    return divergent, crashed, seen


def _matrix_worst(returncodes):
    """The worst (highest) severity over the interpreter legs. A NEGATIVE returncode is a signal kill, so
    abs() keeps it a failure rather than letting max() rank it below success. Empty -> 0 (no legs ran)."""
    return max((abs(rc) for rc in returncodes), default=0)


def _refused(path, needle, inventory_path=None):
    """True when _load_examples(path, inventory_path) raises RuntimeError whose message contains `needle`.
    Any other exception is False, so a row whose guard is removed and whose record then makes a later step
    raise (for example a TypeError on a missing list) is a named problem rather than a traceback."""
    try:
        _load_examples(path, inventory_path)
    except RuntimeError as exc:
        return needle in str(exc)
    except Exception:
        return False
    return False


def _fifo_problem(fifo):
    """None when _read_fixture_bytes refuses the FIFO `fifo` (no writer) as not a regular file, else a
    description. The read runs in a child interpreter killed after FIFO_PROBE_SECONDS, because without
    O_NONBLOCK the open blocks until a writer appears and would hang this self-check."""
    code = ("import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import selftest_commonmark_conformance as m\n"
            "try:\n"
            "    m._read_fixture_bytes(sys.argv[2])\n"
            "except RuntimeError as exc:\n"
            "    sys.exit(0 if 'not a regular file' in str(exc) else 3)\n"
            "sys.exit(4)\n")
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, here, fifo],
                              capture_output=True, timeout=FIFO_PROBE_SECONDS)
    except subprocess.TimeoutExpired:
        return "reading a FIFO with no writer blocked for {} s".format(FIFO_PROBE_SECONDS)
    if proc.returncode != 0:
        return "the child exited {} (0 means refused as not a regular file): {}".format(
            proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[-300:])
    return None


def _fixture_pin_problems():
    """The fixture rows of the self-check: the byte pin, the reader's regular-file check (a directory and a
    FIFO with no writer), its read cap, and the import anchor (_fixture_import_rows). Each byte pin red row
    would pass with the pin removed from _load_examples (the mutated copy still parses to 652 well-formed
    records), so it fails when the pin is dropped. Rows that need the committed fixture read it once; when
    it cannot be read that is itself a problem, so the self-check fails closed rather than skipping the
    rows. Returns a list of problems."""
    problems = []
    if not (isinstance(SPEC_FIXTURE_SHA256, str) and _SHA256_HEX_RE.fullmatch(SPEC_FIXTURE_SHA256)):
        problems.append("SPEC_FIXTURE_SHA256 is not 64 lowercase hex digits")
    if not (type(SPEC_FIXTURE_SIZE) is int and SPEC_FIXTURE_SIZE > 0):
        problems.append("SPEC_FIXTURE_SIZE is not a positive int")
    # Synthetic rows on the comparison itself: equal bytes pass, a one-byte change of the same length and
    # one appended byte are each refused.
    sample = b'[{"markdown": "a\\n", "html": "<p>a</p>\\n", "example": 1}]\n'
    sample_sha = hashlib.sha256(sample).hexdigest()
    if _fixture_bytes_problem(sample, sample_sha, len(sample)) is not None:
        problems.append("fixture/pin-equal-bytes-pass: equal bytes were refused")
    flipped = sample.replace(b"<p>a</p>", b"<p>b</p>", 1)
    if len(flipped) != len(sample) or _fixture_bytes_problem(flipped, sample_sha, len(sample)) is None:
        problems.append("fixture/pin-one-byte-change-refused: a one-byte change was accepted")
    if _fixture_bytes_problem(sample + b"\n", sample_sha, len(sample)) is None:
        problems.append("fixture/pin-appended-byte-refused: an appended byte was accepted")
    # Rows on the committed fixture through the production loader.
    try:
        committed = _read_fixture_bytes(SPEC_FIXTURE)
    except RuntimeError as exc:
        problems.append("fixture pin rows cannot run: {}".format(exc))
        return problems
    tmp = tempfile.mkdtemp(prefix="commonmark-conformance-selfcheck-")
    try:
        def put(name, data):
            target = os.path.join(tmp, name)
            with open(target, "wb") as handle:
                handle.write(data)
            return target

        try:
            loaded = _load_examples(put("clean.json", committed))
            if len(loaded) != EXPECTED_EXAMPLE_COUNT:
                problems.append("fixture/committed-copy-loads: the committed bytes loaded {} examples".format(
                    len(loaded)))
        except RuntimeError as exc:
            problems.append("fixture/committed-copy-loads: the committed bytes were refused: {}".format(exc))
        # One byte changed in a field the replay never reads: the JSON still parses to the same markdown and
        # html of every example, so only the byte pin can refuse it.
        anchor = b'"section": "Tabs"'
        if _fixture_bytes_problem(committed) is not None:
            pass                          # already a problem from the committed-copy row above
        elif anchor not in committed:
            problems.append("fixture/one-byte-section-edit-refused: anchor {!r} absent".format(anchor))
        else:
            edited = committed.replace(anchor, b'"section": "Tabz"', 1)
            same_records = [(e["markdown"], e["html"]) for e in json.loads(edited.decode("utf-8"))] == [
                (e["markdown"], e["html"]) for e in json.loads(committed.decode("utf-8"))]
            if len(edited) != len(committed) or not same_records:
                problems.append("fixture/one-byte-section-edit-refused: the probe is not a one-byte inert edit")
            elif not _refused(put("section.json", edited), "pinned bytes"):
                problems.append("fixture/one-byte-section-edit-refused: a one-byte change was accepted")
        if not _refused(put("newline.json", committed + b"\n"), "pinned bytes"):
            problems.append("fixture/appended-newline-refused: a re-serialized fixture was accepted")
        if not _refused(os.path.join(tmp, "absent.json"), "absent or unreadable"):
            problems.append("fixture/absent-refused: a missing fixture was not refused")
        os.mkdir(os.path.join(tmp, "dir.json"))
        if not _refused(os.path.join(tmp, "dir.json"), "not a regular file"):
            problems.append("fixture/directory-refused: a directory was not refused as not a regular file")
        if not hasattr(os, "mkfifo"):
            problems.append("fixture/fifo-refused: os.mkfifo is unavailable, so the row cannot run")
        else:
            fifo = os.path.join(tmp, "fifo.json")
            os.mkfifo(fifo)
            problem = _fifo_problem(fifo)
            if problem is not None:
                problems.append("fixture/fifo-refused: {}".format(problem))
        # The read cap: an oversized file yields at most SPEC_FIXTURE_SIZE + 1 bytes.
        try:
            capped = len(_read_fixture_bytes(put("oversized.json", b" " * (SPEC_FIXTURE_SIZE + 4096))))
        except RuntimeError as exc:
            capped = "refused: {}".format(exc)
        if capped != SPEC_FIXTURE_SIZE + 1:
            problems.append("fixture/read-capped: read {} of an oversized file, the cap is {} bytes".format(
                capped, SPEC_FIXTURE_SIZE + 1))
        problems.extend(_fixture_import_rows(committed, put))
    finally:
        shutil_rmtree(tmp)
    return problems


def _fixture_import_rows(committed, put):
    """The import-anchor rows of the self-check (review MINOR 2). `committed` is the committed fixture's
    bytes and `put(name, data)` writes a file in the self-check's temporary directory and returns its path.
    Returns a list of problems."""
    problems = []
    problem = _fixture_import_problem(committed)
    if problem is not None:
        problems.append(
            "fixture/import-record-matches: the committed fixture is not the imported one: {}".format(problem))
    # RED: the fixture and SPEC_FIXTURE_SHA256 rewritten together (so the byte pin passes) are refused by the
    # real import record.
    edited = committed.replace(b'"section": "Tabs"', b'"section": "Tabz"', 1)
    if edited == committed:
        problems.append("fixture/joint-edit-with-pin-refused: anchor absent")
    elif _fixture_import_problem(edited, expected_sha256=hashlib.sha256(edited).hexdigest()) is None:
        problems.append("fixture/joint-edit-with-pin-refused: a fixture rewritten with its pin was accepted")
    clean = put("import-clean.json", committed)
    good_entry = {"blob": ch.git_blob_id(committed), "mode": "100644", "path": SPEC_FIXTURE_REL,
                  "sha256": SPEC_FIXTURE_SHA256}

    def inventory(name, entries, deviations=()):
        return put(name, json.dumps({"deviations": list(deviations), "entries": entries}).encode("utf-8"))

    # Through the production loader, each with a synthetic import record: a correct record loads (also
    # when written as the raw bytes the malformed rows below are built from), and a changed entry, a
    # deviation record, a missing entry, an absent record and a record that is not JSON are each refused.
    # The rows from import-entry-twice-refused on each hold a usable entry for the fixture (or, for
    # no-entries-list, entries-not-a-list and not-an-object, nothing a later step can iterate), so only the
    # rule each is named for refuses it: with that rule removed, the record loads or a later step raises,
    # and the row fails. entries-not-a-list and deviations-a-number also fail when their list check is
    # weakened to a None check, because a number is not None and cannot be iterated.
    entry_json = json.dumps(good_entry, sort_keys=True).encode("utf-8")
    for name, inventory_path in (
            ("fixture/import-record-synthetic-loads", inventory("inv-good.json", [good_entry])),
            ("fixture/import-record-raw-control-loads",
             put("inv-raw-good.json", b'{"deviations": [], "entries": [' + entry_json + b"]}"))):
        try:
            _load_examples(clean, inventory_path)
        except RuntimeError as exc:
            problems.append("{}: refused: {}".format(name, exc))
    changed = dict(good_entry, blob="0" * 40)
    rows = (
        ("fixture/import-entry-changed-refused", inventory("inv-changed.json", [changed])),
        ("fixture/import-entry-sha256-changed-refused",
         inventory("inv-sha.json", [dict(good_entry, sha256="0" * 64)])),
        ("fixture/deviation-record-refused",
         inventory("inv-deviation.json", [good_entry], [{"path": SPEC_FIXTURE_REL}])),
        ("fixture/import-entry-missing-refused", inventory("inv-missing.json", [])),
        ("fixture/import-record-absent-refused",
         os.path.join(os.path.dirname(clean), "absent-inventory.json")),
        ("fixture/import-record-not-json-refused", put("inv-not-json.json", b'{"entries": [')),
        ("fixture/import-entry-twice-refused", inventory("inv-twice.json", [good_entry, good_entry])),
        ("fixture/import-record-no-deviations-list-refused",
         put("inv-no-deviations.json", b'{"entries": [' + entry_json + b"]}")),
        ("fixture/import-record-deviations-not-a-list-refused",
         put("inv-deviations-object.json", b'{"deviations": {}, "entries": [' + entry_json + b"]}")),
        ("fixture/import-record-deviations-a-number-refused",
         put("inv-deviations-number.json", b'{"deviations": 5, "entries": [' + entry_json + b"]}")),
        ("fixture/import-record-no-entries-list-refused", put("inv-no-entries.json", b'{"deviations": []}')),
        ("fixture/import-record-entries-not-a-list-refused",
         put("inv-entries-number.json", b'{"deviations": [], "entries": 5}')),
        ("fixture/import-record-not-an-object-refused", put("inv-list.json", b"[]")),
        ("fixture/import-record-duplicate-key-refused",
         put("inv-duplicate.json", b'{"deviations": [], "entries": [], "entries": [' + entry_json + b"]}")),
        ("fixture/import-record-nan-refused",
         put("inv-nan.json", b'{"deviations": [], "entries": [' + entry_json + b'], "x": NaN}')),
        ("fixture/import-record-not-utf8-refused",
         put("inv-not-utf8.json", b'{"deviations": [], "entries": [' + entry_json + b'], "x": "\xff"}')),
    )
    for name, inventory_path in rows:
        if not _refused(clean, "import record", inventory_path):
            problems.append("{}: the fixture was not refused".format(name))
    return problems


def shutil_rmtree(path):
    """Remove a self-check temporary directory (stdlib shutil.rmtree, errors ignored)."""
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def _self_check():
    """Exercise the classification and matrix-aggregation logic the gate's verdict rests on, so a regression
    of the crash-never-absorbed, fixture-identity, or signal-killed-leg hardening, or of the fixture byte pin
    (_fixture_pin_problems), fails THIS gate rather than passing silently (change-carries-a-check). Returns 0
    on success, 2 on a logic regression."""
    class _R:
        def convert(self, md):
            if md == "BOOM":
                raise RuntimeError("injected render fault")
            return md
    r = _R()
    problems = []
    div, crashed, _seen = _classify(
        [{"example": 9, "markdown": "BOOM", "html": "x"},
         {"example": 10, "markdown": "a", "html": "a"}], r)
    if not crashed or crashed[0][0] != 9:
        problems.append("a render crash was not recorded as a crash")
    if div:
        problems.append("a crash was absorbed as an output divergence")
    _, _, seen_dup = _classify(
        [{"example": 1, "markdown": "a", "html": "a"},
         {"example": 1, "markdown": "a", "html": "a"}], r)
    if sorted((n for n in set(seen_dup) if seen_dup.count(n) > 1), key=lambda n: (n is None, n)) != [1]:
        problems.append("a duplicate example id was not detected")
    _, _, seen_nul = _classify([{"example": None, "markdown": "a", "html": "a"}], r)
    if seen_nul.count(None) != 1:
        problems.append("a null example id was not detected")
    if _matrix_worst([-9, 0]) != 9:
        problems.append("a signal-killed matrix leg (returncode -9) did not rank as a failure")
    if _matrix_worst([0, 0]) != 0:
        problems.append("a clean matrix run did not rank as success")
    # production-verdict guard: with the baseline reproduced (so unexpected/missing are empty), each of a
    # duplicate id, a null id, a render crash, and a MIXED null+duplicate (which also exercises the None-safe
    # sort key) drives the verdict to REJECT (exit 1) in isolation, and a wholly clean classification is
    # ACCEPTED (exit 0); removing the identity/crash guard, or the None-safe sort key, from _verdict fails here.
    baseline_div = [(n, "x") for n in KNOWN_DIVERGENT_EXAMPLES]
    clean_seen = list(KNOWN_DIVERGENT_EXAMPLES)
    if _verdict(baseline_div, [], clean_seen)[0] != 0:
        problems.append("the verdict wrongly rejected a clean classification")
    if _verdict(baseline_div, [], clean_seen + [clean_seen[0]])[0] != 1:
        problems.append("the verdict did not reject a duplicate example id")
    if _verdict(baseline_div, [], clean_seen + [None])[0] != 1:
        problems.append("the verdict did not reject a null example id")
    if _verdict(baseline_div, [(9999, "boom")], clean_seen)[0] != 1:
        problems.append("the verdict did not reject a render crash")
    try:
        if _verdict(baseline_div, [], clean_seen + [clean_seen[0], None, None])[0] != 1:
            problems.append("the verdict did not reject a mixed null+duplicate classification")
    except Exception as exc:
        problems.append("the verdict raised on a mixed null+duplicate classification: {}".format(exc))
    problems.extend(_fixture_pin_problems())
    for p in problems:
        print("CONFORMANCE SELF-CHECK FAIL: {}".format(p), file=sys.stderr)
    return 2 if problems else 0


def _verdict(divergent, crashed, seen):
    """The gate verdict over one classification. Returns (exit_code, observed, unexpected, missing,
    duplicates, null_ids); exit_code is 1 when any crash, unexpected or stale divergence, duplicate id, or
    null id is present, else 0. Extracted so _self_check can prove the PRODUCTION rejection (not only the
    classification) fails when the identity or crash guard, or the None-safe sort key, is removed."""
    observed = frozenset(n for n, _why in divergent)
    unexpected = observed - KNOWN_DIVERGENT_EXAMPLES
    missing = KNOWN_DIVERGENT_EXAMPLES - observed
    duplicates = sorted((n for n in set(seen) if seen.count(n) > 1), key=lambda n: (n is None, n))
    null_ids = seen.count(None)
    code = 1 if (crashed or duplicates or null_ids or unexpected or missing) else 0
    return code, observed, unexpected, missing, duplicates, null_ids


def _run_single():
    """Run the replay under the current interpreter. Returns an exit code (0/1/2)."""
    try:
        marko = ch._load_marko()          # containment + version 2.2.4 check on the vendored bytes
        examples = _load_examples()
    except (ch.HeadingScanError, RuntimeError) as exc:
        print("CONFORMANCE SELF-TEST ERROR ({}): {}; fail-closed".format(
            sys.version.split()[0], exc), file=sys.stderr)
        return 2

    renderer = marko.Markdown()           # default HTMLRenderer, no extensions; single-threaded use here
    divergent, crashed, seen = _classify(examples, renderer)
    code, observed, unexpected, missing, duplicates, null_ids = _verdict(divergent, crashed, seen)

    print("CONFORMANCE ({}): {} examples, {} divergent, baseline {}".format(
        sys.version.split()[0], len(examples), len(observed), len(KNOWN_DIVERGENT_EXAMPLES)))
    if EXPECTED_EXAMPLE_COUNT is None:
        print("  NOTE: pin EXPECTED_EXAMPLE_COUNT to {} once the fixture is committed".format(len(examples)))
    if crashed:
        for number, why in sorted(crashed, key=lambda d: (d[0] is None, d[0])):
            print("  RENDER CRASH example {}: {}".format(number, why))
    if duplicates or null_ids:
        print("  FIXTURE IDENTITY: {} duplicate example id(s) {}, {} null id(s)".format(
            len(duplicates), duplicates, null_ids))
    if unexpected:
        for number, why in sorted((d for d in divergent if d[0] in unexpected), key=lambda d: (d[0] is None, d[0])):
            print("  UNEXPECTED DIVERGENCE example {}: {}".format(number, why))
    if missing:
        # A recorded divergence that no longer reproduces is also a mismatch: the baseline must be re-measured.
        print("  BASELINE STALE: examples no longer divergent: {}".format(sorted(missing)))
    if code:
        return 1
    print("CONFORMANCE ({}): PASS".format(sys.version.split()[0]))
    return 0


def _run_matrix(interpreters):
    """Re-spawn this harness under each named interpreter and aggregate (an OPTIONAL, not gate-wired,
    maintainer facility). A missing named interpreter is a fail-closed error, not a skip. The gate itself
    runs the single-interpreter form; the pack is standardized on CPython 3.14."""
    script = os.path.abspath(__file__)
    codes = []
    for interp in interpreters:
        exe = shutil_which(interp)
        if exe is None:
            print("CONFORMANCE MATRIX ERROR: required interpreter {!r} not found; fail-closed".format(interp),
                  file=sys.stderr)
            codes.append(2)
            continue
        proc = subprocess.run([exe, "-I", "-B", script], capture_output=False)
        codes.append(proc.returncode)
    return _matrix_worst(codes)


def shutil_which(name):
    """A minimal PATH lookup (stdlib shutil.which), factored so the intent is explicit."""
    import shutil
    return shutil.which(name)


def main(argv):
    selfcheck = _self_check()
    if selfcheck:
        return selfcheck
    if argv and argv[0] == "--self-test":
        if len(argv) > 1:
            print("CONFORMANCE ERROR: --self-test takes no further argument; fail-closed", file=sys.stderr)
            return 2
        print("CONFORMANCE SELF-CHECK: PASS")
        return 0
    if argv and argv[0] == "--interpreters":
        interpreters = argv[1:]
        if not interpreters:
            print("CONFORMANCE MATRIX ERROR: --interpreters needs at least one interpreter; fail-closed",
                  file=sys.stderr)
            return 2
        return _run_matrix(interpreters)
    if argv:
        print("CONFORMANCE ERROR: unknown argument {!r}; fail-closed".format(argv[0]), file=sys.stderr)
        return 2
    return _run_single()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
