#!/usr/bin/env python3
"""Project-owned CommonMark heading recognition for the OPF changelog gate (U5).

This is the NARROW adapter over the vendored Marko 2.2.4 parser (opf/tools/_vendor/marko/). It answers exactly
one question for `_opf_changelog._changelog_entries`: which top-level (direct-child-of-Document) CommonMark
level-2 headings does a changelog carry, and where does each begin. It replaces the bespoke line scanner and
its documented incomplete fenced-code approximation that used to live in `_opf_changelog.py`, so a `## ` that
merely looks like an entry heading, one inside a fenced or indented code block, an HTML block, a block quote,
or a list, is no longer mistaken for an entry boundary, and a real top-level H2 (ATX or setext) is not missed.

Design (from the settled tri-family plan; parse-only, import-pinned, fail-closed):

  - Marko is imported ONLY from the vendored tree. At first use the adapter asserts the resolved marko module
    path is under opf/tools/_vendor/ (an absolute-path containment check, not a name check) AND that
    marko.__version__ is exactly 2.2.4, and it applies the same absolute-path check to the two submodules it
    explicitly imports (marko.block, marko.parser). The check validates each module's REPORTED file path
    (module.__file__), so an ambient install taking precedence over the root package, and an import hook that
    supplies one of those three checked modules from an external true path, are caught: a mismatch is a
    fail-closed HeadingScanError, never a silent fallback. opf/tools/_vendor is made importable deterministically
    from THIS file's own location (an explicit front-inserted absolute path derived from __file__, never the
    CWD). Coverage is BOUNDED to those three modules: the other parse-path submodules (marko.inline,
    inline_parser, patterns, element, helpers, source) are not individually origin-checked; absent an
    in-process import hook they are pinned by construction, resolved from the verified vendored package's own
    __path__ rather than sys.path. Because __file__ is self-reported and a meta-path hook runs ahead of that
    __path__ resolution, the check does NOT defend against a malicious loader that FORGES a vendored __file__,
    that supplies an unchecked submodule from an external path, or an in-process attacker who patches this
    adapter's own code or sys.modules; all are interpreter compromise, outside the adapter's threat scope.

  - A FRESH marko.parser.Parser() is instantiated per call, with NO extensions. Marko's higher-level Markdown
    object is documented not-thread-safe and its convert / renderer / GFM / named-extension paths are never
    touched; the extension-loading facility is never invoked, and no extension name or configuration is ever
    taken from changelog content.

  - CRLF and lone CR are normalized to LF ONCE; that same normalized string is what is parsed AND what the
    caller slices and digests. Marko records source-span offsets into ITS preprocessed buffer, which applies
    two further LENGTH-PRESERVING substitutions on top of LF normalization (form-feed -> LF, and NUL -> the
    replacement character); because they preserve length, the offsets are valid indices into the LF-normalized
    string this adapter returns, and slicing that string keeps the entry's original form-feed and NUL bytes
    intact (matching the freeze-digest normalization in `_opf_changelog._normalize_lf`, spec 7.2). The adapter
    asserts the document span covers the whole normalized string, so a future change to Marko's preprocessing
    that is NOT length-preserving is caught here rather than silently mis-slicing.

  - An input-size ceiling is enforced BEFORE parsing: MAX_CHANGELOG_BYTES (1 MiB), a named, documented policy
    constant. Oversized input is a distinct fail-closed HeadingScanError. This ceiling bounds MEMORY, not CPU:
    Marko's parse is worst-case superlinear (roughly quadratic) on crafted pathological input (long runs of
    brackets or spaces, or many repeated reference definitions) far below the ceiling, so a maliciously-shaped
    input within the byte limit can be slow to parse. The residual is availability, never a wrong verdict: the
    changelog this gate reads is maintainer-authored in-repo content, and a slow parse never yields a wrong
    result. An ordinary exception raised during the parse is wrapped as a fail-closed parser-exception; a
    KeyboardInterrupt propagates and a killed process (or an external timeout) ends the run with no verdict at
    all, so an interruption is at worst an unsuccessful run, never a silent pass. A caller that runs this over
    adversary-authored content should additionally bound wall-clock time (the gate step carries no timeout of
    its own).

  - Entry boundaries: only DIRECT children of the Document are examined; a Heading (ATX) or SetextHeading node
    whose level == 2 is selected. Each selected H2's raw source is taken from its source span; ATX vs setext is
    classified only after the AST has established it is a heading, and the heading payload (the text the caller
    applies its covers-token / date grammar to) is extracted from that bounded source. The caller delimits each
    entry from its H2 start offset to the next direct H2's start offset (or end of file). Every recognized
    direct H2 is returned as a boundary even when its payload is empty or malformed, so the caller can report a
    malformed entry rather than silently omit it or merge its content into the previous entry.

  - FAIL CLOSED with a DISTINCT cannot-evaluate result (an HeadingScanError carrying a .reason, never an empty
    or "no entries" list) on: a parser exception or a structurally-degenerate parse result (a document with no
    children list, or a heading node with no integer level), a missing or invalid source span, a provenance /
    version / import-origin mismatch, an unreadable vendored file, or oversized input. A cannot-evaluate is
    terminal and named; it is not collapsed into a definite verdict (guard-input-soundness;
    check-fails-closed-on-unreadable).

  - CommonMark conformance is exactly Marko 2.2.4's. The adapter recognizes headings by what MARKO parses, so
    it inherits Marko's conformance boundary: about 97.5% of the CommonMark 0.31.2 spec example suite renders
    identically (636 of 652; see opf/tools/selftest_commonmark_conformance.py), and on rare adversarial edge inputs
    Marko diverges from the spec's block/inline grammar (for instance a non-breaking space accepted where an
    ATX heading requires an ASCII space, a form feed treated as a line ending, or a malformed `<!` opening a
    spurious HTML block), so a hand-crafted line can be recognized or missed against a strict reading of the
    spec. This is acceptable for the maintainer-authored changelog this gate reads; a use over
    adversary-authored content inherits the same boundary.

  - The selected parse path performs no network, filesystem, subprocess, eval, or exec: it normalizes a string,
    constructs a Parser, parses, and slices. The vendored bytes are imported once at first use (a module import,
    not a per-parse read). Byte-integrity of the vendored tree is a SEPARATE, once-per-push concern: the
    AUTHORITATIVE per-push byte gate is the release manifest (tools/check_manifest.py re-hashes every vendored
    file against .aiqt/manifest.toml). `verify_vendor_manifest` below is an additional adapter-side check of the
    vendored tree against its own sha256sum-format manifest; it is exercised against the REAL committed tree by
    the commonmark-headings self-test, and is deliberately kept off the per-parse path.

  - The manifest is checked against two records before any row is trusted. First, the provenance record
    (tools/_vendor/marko-2.2.4.provenance.toml) holds the wheel pin, [package].version and
    [artifacts.wheel].sha256, and [artifacts.wheel].manifest_sha256, the manifest digest recorded beside the
    wheel pin: the SHA-256 of the committed manifest of the files extracted from that wheel.
    `verify_manifest_binding` requires the version to be MARKO_VERSION, the wheel sha256 to be
    MARKO_WHEEL_SHA256 (a constant in this file, so an edit of the wheel pin in the record alone is
    refused), manifest_sha256 to be 64 lowercase hex digits, and the manifest's current bytes to hash to
    manifest_sha256. So an edit to a vendored file together with its row, which the per-file check alone
    accepts, is refused with reason manifest-unbound while the provenance record is unchanged; this binding
    alone cannot refuse a change that also rewrites manifest_sha256. Second, `verify_manifest_import`
    anchors the manifest to the import record. The import dropped the opf/ prefix from the path of every
    row and changed nothing else, so the manifest with opf/ put back after the two spaces of each row is the
    manifest as imported, and its git blob id must equal the blob of the manifest's entry in
    PROVENANCE-inventory.json (reason manifest-not-imported otherwise). tools/check_provenance_deviations.py
    requires the git tree id of all the entry blobs to equal source_opf_tree and the PROVENANCE.md
    "Source `opf/` tree object" line, so that entry is tied to the imported tree, and a same-pin row change
    (a vendored file, its row and manifest_sha256 edited together) is refused. Residual: the import record
    is kept in the same tree, so this narrows the residual rather than closing it. A change that also
    forges the import record (the manifest's entry, source_opf_tree, the PROVENANCE.md tree line and the
    inventory pin) passes, and so does a manifest whose as-imported form (opf/ put back on each row) is
    built to collide with the imported SHA-1 blob id, which needs no change to the manifest's entry,
    source_opf_tree or the PROVENANCE.md tree line, because only the blob is compared. That collision path
    still rewrites manifest_sha256, refreshes the deviation records of the manifest and the provenance
    record, adds a deviation record for the edited vendored file and refreshes the PROVENANCE.md pin, all
    of which the deviations gate accepts, because that gate never computes the as-imported form. The
    deviations gate discloses the forgery and the SHA-1 collision residual of its own blob check (a file whose
    own bytes collide with its imported blob), and its docstring says to treat any such edit as a re-import
    and to review it against the source repository with git rev-parse <source_commit>:opf. The manifest and
    the provenance record already have deviation records, so a change to either must refresh the blob and
    sha256 of its existing record in the same change, and an edited vendored Marko file needs its own new
    deviation record. A deliberate Marko upgrade therefore needs a code change to `verify_manifest_import`
    that names the new expected manifest, as well as new MARKO_VERSION and MARKO_WHEEL_SHA256 values; that
    friction is intended.

This module's top level imports NO third-party code: marko is imported lazily inside `_load_marko`, so importing
this module (for `verify_vendor_manifest`, or before the vendored tree exists) never requires marko to be present.
"""
import hashlib
import json
import os
import re
import sys
import tomllib

# --- policy constants ---------------------------------------------------------------------------------

MAX_CHANGELOG_BYTES = 1048576             # 1 MiB input ceiling, enforced before parsing (named policy value)
MARKO_VERSION = "2.2.4"                    # the exact vendored pin; any other resolved version fails closed
MANIFEST_NAME = "marko-2.2.4.manifest.sha256"   # sha256sum-format per-file manifest of the vendored tree
PROVENANCE_NAME = "marko-2.2.4.provenance.toml"  # provenance record: the wheel pin and the bound manifest digest
# The [artifacts.wheel].sha256 the provenance record must hold (the pinned wheel's SHA-256, as recorded there).
MARKO_WHEEL_SHA256 = "d80510506edba096ec49d4720a09645fa0bb78e7b7b88697f20032fc19730aa9"
INVENTORY_NAME = "PROVENANCE-inventory.json"     # the import record at the OPF root
IMPORT_PATH_PREFIX = b"opf/"              # the path prefix the import dropped from every manifest row

KIND_ATX = "atx"                          # a level-2 ATX heading ("## title")
KIND_SETEXT = "setext"                    # a level-2 setext heading ("title\n---")

# Distinct cannot-evaluate categories (each terminal and named, never a clean pass).
REASON_OVERSIZED = "oversized"            # input over MAX_CHANGELOG_BYTES
REASON_PARSER = "parser-exception"        # marko raised while parsing
REASON_INVALID_SPAN = "invalid-span"      # a node's source span is missing, malformed, or out of range
REASON_PROVENANCE = "provenance"          # wrong version or import origin outside the vendored tree
REASON_VENDOR_UNREADABLE = "vendor-unreadable"   # the vendored marko cannot be imported / a vendored file cannot be read
REASON_MANIFEST_DRIFT = "manifest-drift"  # a vendored file differs from, or is missing/extra against, the manifest
REASON_MANIFEST_UNBOUND = "manifest-unbound"   # the manifest's bytes are not the ones bound to the wheel pin
REASON_MANIFEST_NOT_IMPORTED = "manifest-not-imported"   # the manifest is not the one the import record holds
REASON_INVALID_INPUT = "invalid-input"    # the content handed to the adapter is not text

# opf/tools/_vendor, derived from THIS file's own absolute location (never the CWD): consistent with the repo's
# absolute-paths rule and stable across working directories, subprocesses, and sessions.
_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vendor")

_MANIFEST_LINE_RE = re.compile(r"^([0-9a-f]{64})  (.+)$")   # sha256sum default format: hex, two spaces, path
_SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
_BLOB_HEX_RE = re.compile(r"[0-9a-f]{40}")
_MANIFEST_ROW_START_RE = re.compile(rb"(?m)^([0-9a-f]{64}  )")   # a row's digest and its two spaces

_MARKO = None                             # the verified vendored marko module, cached after first successful load
_MISSING = object()                       # sentinel: an attribute genuinely absent (a degenerate parse result)


class HeadingScanError(Exception):
    """A distinct fail-closed cannot-evaluate outcome from the heading scanner. It is never an empty or
    "no entries" result: a caller catches it and reports cannot-evaluate. `reason` is one of the REASON_*
    categories so a caller can distinguish oversized input, a parser fault, an invalid span, a provenance
    mismatch, an unreadable vendored tree, or manifest drift."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason


class H2Heading:
    """One recognized top-level level-2 heading. `start` is its offset into the normalized source (the
    entry's start); `payload` is the heading's text content, with the ATX marker or setext underline
    removed and surrounding whitespace stripped (a multiline setext payload keeps its interior newline, so
    the caller's single-line title grammar can reject it); `kind` is KIND_ATX or KIND_SETEXT."""

    __slots__ = ("start", "payload", "kind")

    def __init__(self, start, payload, kind):
        self.start = start
        self.payload = payload
        self.kind = kind


class ScanResult:
    """The result of a successful scan. `normalized_text` is the LF-normalized source the caller MUST use
    for slicing and digesting (the same string the parser saw); `headings` is the tuple of H2Heading
    boundaries in document order, including any with an empty or malformed payload."""

    __slots__ = ("normalized_text", "headings")

    def __init__(self, normalized_text, headings):
        self.normalized_text = normalized_text
        self.headings = headings


# --- normalization ------------------------------------------------------------------------------------

def _normalize_lf(text):
    """LF-normalize line endings once (spec 7.2 line endings). This mirrors `_opf_changelog._normalize_lf`
    exactly, so the offsets this adapter returns index the same bytes the caller slices and digests. Marko
    additionally maps form-feed to LF and NUL to the replacement character inside its own buffer, but both
    are length-preserving, so the offsets stay valid indices into this LF-normalized string and slicing it
    keeps the entry's original form-feed and NUL bytes."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


# --- vendored-marko import, pinned and containment-checked --------------------------------------------

def _verify_module_origin(module, vendor_dir):
    """Assert `module` (the root package OR a submodule the parse path uses) is resolved from a file
    physically under `vendor_dir` (an absolute realpath containment check, not a name check). Raises
    HeadingScanError(reason=REASON_PROVENANCE) if the module exposes no file path or resolves outside the
    vendored tree, so an ambient install or an import hook that supplies THIS module from an external true
    path fails closed (a forged __file__ is out of the check's scope; see the module header)."""
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise HeadingScanError(
            "vendored module {!r} exposes no file path".format(getattr(module, "__name__", module)),
            REASON_PROVENANCE)
    resolved = os.path.realpath(module_file)
    anchor = os.path.realpath(vendor_dir) + os.sep
    if not resolved.startswith(anchor):
        raise HeadingScanError(
            "module {!r} resolved from {!r}, outside the vendored tree {!r}".format(
                getattr(module, "__name__", module), resolved, vendor_dir),
            REASON_PROVENANCE)


def _verify_marko_provenance(module, vendor_dir):
    """Assert `module` is the vendored, pinned marko: version exactly MARKO_VERSION and resolved from a file
    physically under `vendor_dir`. Raises HeadingScanError(reason=REASON_PROVENANCE) on any mismatch, so an
    ambient install taking precedence, a drifted version, or a module with no file path fails closed."""
    version = getattr(module, "__version__", None)
    if version != MARKO_VERSION:
        raise HeadingScanError(
            "vendored marko version is {!r}, expected {!r}".format(version, MARKO_VERSION),
            REASON_PROVENANCE)
    _verify_module_origin(module, vendor_dir)


def _load_marko():
    """Import the vendored marko once, verify its provenance, and cache it. Front-inserts opf/tools/_vendor on
    sys.path (only the marko package and the vendored licences live there, so no standard-library module is
    shadowed) and fails closed if the vendored tree cannot be imported or does not pass the provenance
    check. Never falls back to an ambient install."""
    global _MARKO
    if _MARKO is not None:
        return _MARKO
    if _VENDOR_DIR not in sys.path:
        sys.path.insert(0, _VENDOR_DIR)
    try:
        import marko            # noqa: E402  vendored, provenance-checked immediately below
        import marko.block      # noqa: E402,F401  block AST classes (Heading / SetextHeading)
        import marko.parser     # noqa: E402,F401  the parse-only Parser
    except Exception as exc:    # an unreadable / broken vendored tree is fail-closed, not a silent skip
        raise HeadingScanError(
            "cannot import the vendored marko parser from {}: {}".format(_VENDOR_DIR, exc),
            REASON_VENDOR_UNREADABLE) from exc
    _verify_marko_provenance(marko, _VENDOR_DIR)
    # Containment is not only the root package: the two submodules this function explicitly imports
    # (marko.block, marko.parser) are origin-checked too, so an import hook cannot supply either of them from
    # an external true path while the root marko loads from the vendored tree. The other parse-path submodules
    # (inline, inline_parser, patterns, element, helpers, source) are not individually checked; absent an
    # in-process hook they resolve normally from the verified package's own __path__, and a meta-path hook
    # overriding that resolution to supply one of them externally is the interpreter compromise that is out of
    # scope (see the module header).
    _verify_module_origin(marko.block, _VENDOR_DIR)
    _verify_module_origin(marko.parser, _VENDOR_DIR)
    _MARKO = marko
    return marko


def _new_parser(marko):
    """Construct a FRESH, extension-free parser. Factored out so a self-test can substitute a parser that
    raises or returns a degenerate document, to exercise the fail-closed paths."""
    return marko.parser.Parser()


# --- span and payload helpers -------------------------------------------------------------------------

def _valid_span(span):
    """True when `span` is a usable (start, end) offset pair: a 2-tuple of ints with 0 <= start <= end."""
    if not (isinstance(span, tuple) and len(span) == 2):
        return False
    start, end = span
    return isinstance(start, int) and isinstance(end, int) and 0 <= start <= end


def _atx_payload(marko, raw):
    """Extract an ATX heading's payload from its raw source span, using marko's OWN Heading grammar so the
    payload is defined by exactly the same rule the parser used to recognize the heading (single source of
    the grammar; the opening `#` run and any optional closing `#` run are removed, then stripped). Raises
    HeadingScanError(reason=REASON_INVALID_SPAN) if the raw source does not re-match, which would mean the
    span and the AST classification disagree."""
    match = marko.block.Heading.pattern.match(raw)
    if match is None:
        raise HeadingScanError(
            "an ATX heading source span did not re-match the heading grammar", REASON_INVALID_SPAN)
    return match.group(2).strip()


def _setext_payload(raw):
    """Extract a setext heading's payload from its raw source span, mirroring marko's SetextHeading: drop
    the trailing underline line and join the remaining lines with each line's leading whitespace stripped,
    then strip the whole. A multiline setext keeps its interior newline, so the caller's single-line title
    grammar rejects it. Raises HeadingScanError(reason=REASON_INVALID_SPAN) if the span is too short to
    contain both a text line and an underline."""
    lines = raw.splitlines(keepends=True)
    if len(lines) < 2:
        raise HeadingScanError(
            "a setext heading source span is too short to contain an underline", REASON_INVALID_SPAN)
    text_lines = lines[:-1]               # the last line is the '=' or '-' underline
    return "".join(line.lstrip() for line in text_lines).strip()


# --- the scan -----------------------------------------------------------------------------------------

def scan_entry_headings(text):
    """Parse `text` as CommonMark and return a ScanResult of its top-level level-2 heading boundaries.

    Fails closed with HeadingScanError (never an empty result) on: non-text input, oversized input (over
    MAX_CHANGELOG_BYTES), a parser exception, a missing or invalid source span, or a vendored-import /
    provenance mismatch. On success, `ScanResult.normalized_text` is the LF-normalized source the caller
    must slice and digest, and `ScanResult.headings` is every direct-child H2 in document order (ATX or
    setext), including those with an empty or malformed payload."""
    if not isinstance(text, str):
        raise HeadingScanError("changelog content is not text", REASON_INVALID_INPUT)

    size = len(text.encode("utf-8"))      # ceiling enforced BEFORE parsing (guard-input-soundness)
    if size > MAX_CHANGELOG_BYTES:
        raise HeadingScanError(
            "changelog is {} bytes, over the {}-byte ceiling".format(size, MAX_CHANGELOG_BYTES),
            REASON_OVERSIZED)

    marko = _load_marko()
    norm = _normalize_lf(text)

    try:
        parser = _new_parser(marko)
        document = parser.parse(norm)
    except HeadingScanError:
        raise                             # a fail-closed error from the parser factory propagates unchanged
    except Exception as exc:              # any other parser fault is a fail-closed cannot-evaluate
        raise HeadingScanError(
            "marko failed to parse the changelog: {}".format(exc), REASON_PARSER) from exc

    # The parser records offsets into its own preprocessed buffer; confirm that buffer is exactly as long as
    # `norm` so those offsets are valid indices into `norm` (marko's extra form-feed / NUL substitutions are
    # length-preserving, so this holds; a future non-length-preserving change is caught here, not mis-sliced).
    doc_span = getattr(document, "source_span", None)
    if not _valid_span(doc_span) or doc_span[0] != 0 or doc_span[1] != len(norm):
        raise HeadingScanError(
            "the marko document span does not cover the normalized source", REASON_INVALID_SPAN)

    heading_cls = marko.block.Heading
    setext_cls = marko.block.SetextHeading

    children = getattr(document, "children", _MISSING)
    if children is _MISSING or not isinstance(children, list):
        # a real marko Document always exposes a children LIST (empty for an empty document). Its absence,
        # or a non-list, is a structurally-degenerate parse result: a fail-closed cannot-evaluate, never an
        # empty "no headings" pass (guard-input-soundness).
        raise HeadingScanError("the marko document exposes no children list", REASON_PARSER)

    headings = []
    for child in children:
        is_atx = isinstance(child, heading_cls)
        is_setext = isinstance(child, setext_cls)
        if not (is_atx or is_setext):     # only direct-child headings are entry boundaries
            continue
        level = getattr(child, "level", _MISSING)
        if not isinstance(level, int):    # a heading node with no integer level is a malformed structure,
            # not a boundary to skip: fail closed rather than silently under-recognize a real H2.
            raise HeadingScanError("a heading node has a missing or non-integer level", REASON_PARSER)
        if level != 2:                    # a top-level H1/H3.. is not an entry boundary
            continue
        span = getattr(child, "source_span", None)
        if not _valid_span(span) or span[1] > len(norm):
            raise HeadingScanError(
                "a level-2 heading has a missing or out-of-range source span", REASON_INVALID_SPAN)
        raw = norm[span[0]:span[1]]
        if is_atx:
            payload, kind = _atx_payload(marko, raw), KIND_ATX
        else:
            payload, kind = _setext_payload(raw), KIND_SETEXT
        headings.append(H2Heading(span[0], payload, kind))

    return ScanResult(norm, tuple(headings))


# --- vendored-tree byte integrity (a standing gate concern, kept OFF the per-parse path) --------------

def _safe_join(base, rel, contain_base=None):
    """Join a manifest-declared relative path under `base`, refusing an absolute path, a parent traversal,
    or any result that escapes `contain_base` (default `base`); tool-argument / path-traversal validation.
    The committed manifest records repository-root-relative paths (so `sha256sum -c` from the repo root
    verifies them), so `base` is the repo root while `contain_base` is the vendored tree the paths must stay
    within. Returns the realpath of the target; raises HeadingScanError(reason=REASON_MANIFEST_DRIFT) on an
    unsafe path."""
    if rel.startswith("/") or rel.startswith("\\") or ".." in rel.replace("\\", "/").split("/"):
        raise HeadingScanError("unsafe manifest path {!r}".format(rel), REASON_MANIFEST_DRIFT)
    contain_real = os.path.realpath(contain_base if contain_base is not None else base)
    target = os.path.realpath(os.path.join(base, rel))
    if not (target == contain_real or target.startswith(contain_real + os.sep)):
        raise HeadingScanError("manifest path {!r} escapes the vendored tree".format(rel),
                               REASON_MANIFEST_DRIFT)
    return target


def _enumerate_vendored_files(vendor_dir, root):
    """Return the posix relative paths (under `vendor_dir`) of every file the manifest is expected to
    attest: the marko package tree and the vendored licences. Skips __pycache__ and compiled .pyc. Raises
    HeadingScanError(reason=REASON_MANIFEST_DRIFT) if the marko package subtree is absent (a check fails
    closed on input it cannot read, never "nothing to check")."""
    found = []
    marko_root = os.path.join(vendor_dir, "marko")
    if not os.path.isdir(marko_root):
        raise HeadingScanError("vendored marko package directory is absent under {}".format(vendor_dir),
                               REASON_MANIFEST_DRIFT)
    for subtree in ("marko", "licenses"):
        subtree_root = os.path.join(vendor_dir, subtree)
        if not os.path.isdir(subtree_root):
            continue                      # 'licenses' is attested when present; 'marko' absence handled above
        for dirpath, dirnames, filenames in os.walk(subtree_root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                abs_path = os.path.join(dirpath, name)
                rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
                found.append(rel)
    return found


def verify_manifest_binding(manifest_bytes, provenance_path):
    """Check the whole manifest against the manifest digest recorded beside the wheel pin in the provenance
    record at `provenance_path` (see the module docstring for what this binding alone cannot refuse).
    Requires [package].version to equal MARKO_VERSION, [artifacts.wheel].sha256 and
    [artifacts.wheel].manifest_sha256 to be 64 lowercase hex digits, the wheel sha256 to equal
    MARKO_WHEEL_SHA256, and SHA-256(`manifest_bytes`) to equal manifest_sha256. Raises HeadingScanError
    with REASON_VENDOR_UNREADABLE when the record cannot be read, REASON_PROVENANCE when it is not UTF-8
    TOML, lacks [package] or [artifacts.wheel], or a pin field is missing, malformed or not the pinned
    value, and REASON_MANIFEST_UNBOUND when the manifest's bytes differ from the recorded digest. Returns
    (version, wheel sha256, manifest sha256) on success."""
    try:
        with open(provenance_path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise HeadingScanError("cannot read the vendored-marko provenance record {}: {}".format(
            provenance_path, exc), REASON_VENDOR_UNREADABLE) from exc
    try:
        record = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HeadingScanError("the vendored-marko provenance record {} is not UTF-8 TOML: {}".format(
            provenance_path, exc), REASON_PROVENANCE) from exc
    package = record.get("package")
    artifacts = record.get("artifacts")
    wheel = artifacts.get("wheel") if isinstance(artifacts, dict) else None
    if not isinstance(package, dict) or not isinstance(wheel, dict):
        raise HeadingScanError("the provenance record {} lacks [package] or [artifacts.wheel]".format(
            provenance_path), REASON_PROVENANCE)
    version = package.get("version")
    if version != MARKO_VERSION:
        raise HeadingScanError("the provenance record pins marko version {!r}, the vendored pin is {!r}".format(
            version, MARKO_VERSION), REASON_PROVENANCE)
    pins = {}
    for key in ("sha256", "manifest_sha256"):
        value = wheel.get(key)
        if not (isinstance(value, str) and _SHA256_HEX_RE.fullmatch(value)):
            raise HeadingScanError("[artifacts.wheel].{} in {} is missing or not 64 lowercase hex digits".format(
                key, provenance_path), REASON_PROVENANCE)
        pins[key] = value
    if pins["sha256"] != MARKO_WHEEL_SHA256:
        raise HeadingScanError("the provenance record {} pins wheel sha256 {}, the vendored pin is {}".format(
            provenance_path, pins["sha256"], MARKO_WHEEL_SHA256), REASON_PROVENANCE)
    actual = hashlib.sha256(manifest_bytes).hexdigest()
    if actual != pins["manifest_sha256"]:
        raise HeadingScanError(
            "the vendored-marko manifest has sha256 {}, but the provenance record (version {}, wheel sha256 {}) "
            "records manifest sha256 {} beside the wheel pin; a manifest row cannot change unless "
            "manifest_sha256 in the provenance record is rewritten".format(
                actual, version, pins["sha256"], pins["manifest_sha256"]), REASON_MANIFEST_UNBOUND)
    return version, pins["sha256"], pins["manifest_sha256"]


def _refuse_duplicate_keys(pairs):
    """A json object_pairs_hook that refuses a repeated key, as the deviations gate's reader does."""
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("duplicate key {!r}".format(key))
        seen[key] = value
    return seen


def _refuse_json_constant(name):
    raise ValueError("the constant {} is not JSON".format(name))


def as_imported_manifest(manifest_bytes):
    """The manifest bytes as the import recorded them: IMPORT_PATH_PREFIX put back after the two spaces
    that follow the digest of every row. The import changed nothing else in the manifest."""
    return _MANIFEST_ROW_START_RE.sub(lambda match: match.group(1) + IMPORT_PATH_PREFIX, manifest_bytes)


def git_blob_id(data):
    """The git blob id (SHA-1 of the blob header and the bytes) of `data`."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_manifest_import(manifest_bytes, inventory_path, manifest_rel):
    """Anchor the whole manifest to the import record (see the module docstring for the residual).
    Requires the inventory at `inventory_path` to be UTF-8 JSON (no duplicate key, NaN or Infinity) with
    an entries list holding exactly one entry whose path is `manifest_rel`, whose blob is 40 lowercase hex
    digits, and to equal the git blob id of as_imported_manifest(`manifest_bytes`). The blob, not the
    entry's sha256, is compared because only the blob ids feed the tree id that
    tools/check_provenance_deviations.py ties to the import. Raises HeadingScanError with
    REASON_VENDOR_UNREADABLE when the inventory cannot be read, REASON_PROVENANCE when it is malformed or
    has no single usable entry for the manifest, and REASON_MANIFEST_NOT_IMPORTED when the manifest is not
    the imported one. Returns the entry's blob id on success."""
    try:
        with open(inventory_path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise HeadingScanError("cannot read the import record {}: {}".format(inventory_path, exc),
                               REASON_VENDOR_UNREADABLE) from exc
    try:
        inventory = json.loads(raw.decode("utf-8"), object_pairs_hook=_refuse_duplicate_keys,
                               parse_constant=_refuse_json_constant)
    except ValueError as exc:             # UnicodeDecodeError and json.JSONDecodeError are ValueErrors
        raise HeadingScanError("the import record {} is not UTF-8 JSON: {}".format(inventory_path, exc),
                               REASON_PROVENANCE) from exc
    entries = inventory.get("entries") if isinstance(inventory, dict) else None
    if not isinstance(entries, list):
        raise HeadingScanError("the import record {} has no entries list".format(inventory_path),
                               REASON_PROVENANCE)
    matches = [entry for entry in entries if isinstance(entry, dict) and entry.get("path") == manifest_rel]
    if len(matches) != 1:
        raise HeadingScanError("the import record {} has {} entries for {}, expected exactly 1".format(
            inventory_path, len(matches), manifest_rel), REASON_PROVENANCE)
    blob = matches[0].get("blob")
    if not (isinstance(blob, str) and _BLOB_HEX_RE.fullmatch(blob)):
        raise HeadingScanError("the import record's blob for {} is missing or not 40 lowercase hex digits".format(
            manifest_rel), REASON_PROVENANCE)
    actual = git_blob_id(as_imported_manifest(manifest_bytes))
    if actual != blob:
        raise HeadingScanError(
            "the vendored-marko manifest, with {} put back on each row, has git blob id {}, but the import "
            "record {} holds blob {} for {}; the manifest is not the imported one".format(
                IMPORT_PATH_PREFIX.decode("ascii"), actual, inventory_path, blob, manifest_rel),
            REASON_MANIFEST_NOT_IMPORTED)
    return blob


def verify_vendor_manifest(vendor_dir=None, manifest_path=None, root=None, provenance_path=None,
                           inventory_path=None):
    """Verify the vendored tree byte-for-byte against its sha256sum-format manifest, bidirectionally: every
    recorded file exists, is readable, and hashes to its recorded digest; and every vendored code / licence
    file is recorded. Before any row is read, the whole manifest is checked against the manifest digest
    recorded beside the wheel pin in the provenance record (`verify_manifest_binding`; `provenance_path`
    defaults to PROVENANCE_NAME beside the manifest's default location in `vendor_dir`) and against the
    import record (`verify_manifest_import`; `inventory_path` defaults to INVENTORY_NAME in `root`, and the
    manifest's entry is looked up by its path relative to `root`). Fails closed with
    HeadingScanError(reason=REASON_MANIFEST_DRIFT, REASON_MANIFEST_UNBOUND, REASON_MANIFEST_NOT_IMPORTED,
    REASON_PROVENANCE or REASON_VENDOR_UNREADABLE) on a missing or unreadable manifest, provenance record or
    import record, a manifest whose bytes are not the recorded ones or not the imported ones, a malformed or
    unpinned pin, a malformed import record, a manifest that is not UTF-8, a malformed or duplicate line, an
    empty manifest, a missing or unreadable listed file, a hash mismatch, or an unlisted vendored file. This
    is a once-per-push byte-integrity gate, deliberately kept off the per-parse path (which does no
    filesystem access). Returns the number of files verified on success."""
    vendor_dir = os.path.abspath(vendor_dir) if vendor_dir else _VENDOR_DIR
    # The committed manifest records OPF-ROOT-relative paths (tools/_vendor/marko/...), so `sha256sum -c` from
    # the OPF root verifies it directly; `root` is that base. It defaults to the directory two levels above
    # the vendored tree (tools/_vendor -> tools -> the OPF root), derived from the tools/ directory and never
    # from an enclosing repository's layout. A synthetic self-test whose manifest is laid out vendor-relative
    # passes root=vendor_dir.
    root = os.path.abspath(root) if root else os.path.dirname(os.path.dirname(vendor_dir))
    manifest_path = manifest_path or os.path.join(vendor_dir, MANIFEST_NAME)
    provenance_path = provenance_path or os.path.join(vendor_dir, PROVENANCE_NAME)
    inventory_path = inventory_path or os.path.join(root, INVENTORY_NAME)
    manifest_rel = os.path.relpath(os.path.abspath(manifest_path), root).replace(os.sep, "/")
    try:
        with open(manifest_path, "rb") as handle:
            manifest_bytes = handle.read()
    except OSError as exc:
        raise HeadingScanError("cannot read the vendored-marko manifest {}: {}".format(manifest_path, exc),
                               REASON_VENDOR_UNREADABLE) from exc
    verify_manifest_binding(manifest_bytes, provenance_path)
    verify_manifest_import(manifest_bytes, inventory_path, manifest_rel)
    try:
        manifest_lines = manifest_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise HeadingScanError("the vendored-marko manifest {} is not UTF-8: {}".format(manifest_path, exc),
                               REASON_MANIFEST_DRIFT) from exc

    recorded = {}
    for lineno, line in enumerate(manifest_lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _MANIFEST_LINE_RE.match(line)
        if match is None:
            raise HeadingScanError(
                "malformed manifest line {} in {}".format(lineno, manifest_path), REASON_MANIFEST_DRIFT)
        digest, rel = match.group(1), match.group(2).replace("\\", "/")
        if rel in recorded:
            raise HeadingScanError("duplicate manifest entry {!r}".format(rel), REASON_MANIFEST_DRIFT)
        recorded[rel] = digest
    if not recorded:
        raise HeadingScanError("the vendored-marko manifest lists no files", REASON_MANIFEST_DRIFT)

    for rel, digest in recorded.items():   # forward: recorded file present and matches
        target = _safe_join(root, rel, contain_base=vendor_dir)
        try:
            with open(target, "rb") as handle:
                actual = hashlib.sha256(handle.read()).hexdigest()
        except OSError as exc:
            raise HeadingScanError("manifest file {} is missing or unreadable: {}".format(rel, exc),
                                   REASON_MANIFEST_DRIFT) from exc
        if actual != digest:
            raise HeadingScanError(
                "manifest drift: {} has sha256 {}, manifest records {}".format(rel, actual, digest),
                REASON_MANIFEST_DRIFT)

    for rel in _enumerate_vendored_files(vendor_dir, root):   # reverse: vendored file recorded
        if rel not in recorded:
            raise HeadingScanError("vendored file {} is not listed in the manifest".format(rel),
                                   REASON_MANIFEST_DRIFT)

    return len(recorded)
