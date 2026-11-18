# Releasing

Release checklists for the OPF reference tooling in this repository. The OPF declaration checklist
below came from the source guardrails repository (commit 504f422d, `RELEASING.md`), with its `opf/`
paths moved to this repository's root layout; `PROVENANCE.md` records it.

## Handover addendum checklist

A change to any file that landed from the handover addendum (each `landed_path` in
`PROVENANCE-addendum.json`, this file, `tools/selftest_checks.toml` and `tools/_child_status.py`
included) updates that file's record in `PROVENANCE-addendum.json` in the same change, and the
change is reviewed against the handover (`PROVENANCE-addendum.SHA256SUMS` and the handed-over
bytes), never made as a bare refresh of `landed_sha256`. A `landed` or `already-present` record
whose file no longer equals the handed-over or imported bytes becomes `landed-adapted`, and
`PROVENANCE.md` says what changed. `python3 -I -B tools/check_provenance_addendum.py` must then
exit 0.

## OPF declaration checklist

OPF declaration checklist (OPF-SPEC section 16.1). The reference tooling's declaration file is
`tools/opf-declaration.toml`, and the shipped-file digest is carried in
`tools/_opf_declaration.py` as `SHIPPED_DECLARATION_SHA256`. Its `release` is OPF's own release
version in `VERSION` (OPF is at this repository's root, so there is no separate pack release
version file), so each change of OPF's version sets, in one change: `VERSION`; `release` in that
file; `SHIPPED_DECLARATION_BYTES` and `SHIPPED_DECLARATION_SHA256` in `_opf_declaration.py`; and
the restatement below and in `spec/OPF-QUICKSTART.md`. A change of the supported `spec_version`,
homes generation or worklog storage generation changes its value in `_opf_store.py`, the matching
field in `tools/opf-declaration.toml`, `SHIPPED_DECLARATION_BYTES` and
`SHIPPED_DECLARATION_SHA256` in `_opf_declaration.py`, and the restatement below and in
`spec/OPF-QUICKSTART.md`; it does not by itself touch `VERSION` or `release`.
`python3 -I -B tools/check_opf_declaration.py` must then exit 0. It refuses a restatement that
differs from the file and a release other than the version in `VERSION`. `RELEASE_IDENTITY` is
read from `VERSION` when the module loads, and a missing or malformed `VERSION` leaves the build
without one, so every gated verb refuses. Adoption is bound to OPF's own version: the `opf adopt`
trust gate checks the plan's release version against the release manifest's `opf-version`, never
the manifest's `release-version`, refusing a manifest that records none. The source project's
`tools/gen_manifest.py`, which writes that manifest, is not part of this repository. This release
declares:

```toml opf-declaration
release = "1.0.5"
spec_version = "1.2.0"
homes = 1
worklog = 1
```
