# OPFiles: the operational-files standard

Formal name: AIQT Development Operational Standard. Public brand: OPFiles
(opfiles.ai). Base discovery token: `opf`. Status: this specification is a draft. The
reference tooling's status in this build is the generated status note that follows, also published
in opf/README.md, on opfiles.ai, and in opf/site/llms.txt (generated from VERB_STATUS in
opf/tools/opf.py):
Reference CLI status. Available: init, render, doctor, absorb. Partial: record (create, transition, done-with-receipt, and worklog-append; receipt-repair exits 2), adopt (plan, approve, reconcile, and status; apply and complete exit 2). In progress: upgrade, import, migrate, sync; each exits 2 in this build.
Date: 2026-10-24 (UTC).

OPFiles is a neutral, self-contained operational-files standard published under the Apache
License 2.0 (except vendored third-party material, which remains under its own terms). AIQT and AIQT Guardrails are trademarks (registration pending); AIQT is a brand,
not a legal entity, and the standard is authored and maintained by its lead maintainer. A project
conforms to OPFiles with this specification and
its own checks; the AIQT Guardrails pack is the reference enforcement suite and a consumer
of the standard, not its definition. AIQT-specific requirements are layered as one optional
profile, `[profiles.aiqt]` (section 9), and a base adopter need not adopt AIQT.

Unless a path is written from `/`, a path under `.working/` in this document is relative to the
root of the repository that tracks the store (the "store repository"), and every other path (the
pointer, `CHANGELOG.md`, `ROADMAP.md`, `VERSION`) is relative to the root of the product
repository. The two roots coincide under the default configuration (section 4.1).

## 1. Purpose and scope

OPF (operational files) standardizes how a project keeps its operational records: the backlog, the
completion receipts, the worklog, findings, decisions, blocks, handoffs, and references that a
records-first operational discipline requires (the discipline AIQT's records-first rule is one
implementation of). It defines one machine-readable store of versioned TOML under
`.working/toml/`, a set of generated human-readable views above it, and three release artifacts (a
version ledger, a durable worklog, and a curated public changelog) with the gates that keep all of
them honest.

The store is always a git repository, wherever it lives. Its location is a free, migratable
configuration resolved through a committed pointer, never an architectural commitment: it defaults
to `.working/` in the product repository and can be relocated at any time to any location a target
can name, with history and the durable worklog preserved (section 5).

OPF specifies formats, layout, naming, lifecycle, and enforcement posture, and names the standard
command vocabulary of the reference tooling (`opf init`, `opf adopt`, `opf import`, `opf
doctor`, `opf render`,
`opf migrate`, `opf sync`, `opf upgrade`, `opf absorb`, `opf record`, `opf report`). It does not
specify tooling internals; a reference implementation follows in later releases of the AIQT
Guardrails reference suite. Every mode of `opf report` is read-only and report-only
(section 10.8), so the verb adds no conformance requirement for a store. A project can conform to
this specification with hand-maintained files and its own checks.

## 2. Conformance language

MUST, MUST NOT, SHOULD, and MAY are used as in common standards practice: MUST is an absolute
requirement of conformance, SHOULD is a strong recommendation departed from only for recorded
reason, MAY is genuinely optional. Statements without these keywords are descriptive.

### 2.1 Planning vocabulary

This specification fixes one meaning, the planning sense, for each planning term below; the
evidence, resolution, delivery, and git-transport senses of "bundle" elsewhere in this
specification (sections 4.2, 5.6, 8, 11, and 14) are untouched. A generated view declared in the
view map (section 9) MUST NOT describe itself with a fixed term outside its meaning here: in
particular, a view MUST NOT call itself a roadmap unless it is the future-facing list of
section 10.7, and MUST NOT call itself a pipeline unless it renders per-lane ordered next entries
as section 10.6 defines them. The same rule binds every other generated planning surface of a
conforming store, a command surface included. The whole rule, for declared views and for every
other surface alike, is a requirement enforced by review rather than by the doctor (section 17).

- **Backlog.** The full set of open items: the clean `backlog_item` records not in an unqualified
  terminal state (section 8.5). `TODO.md` and `BACKLOG.md` are composed views over it
  (section 10.1).
- **Lane.** A long-lived workstream an adopter runs work through; "workstream" survives only as
  this gloss. Lane identity and lane operation, the keep-ahead depth included, belong to a lanes
  standard the adopter follows, if any, a separate document this specification takes as given:
  this specification fixes no lane ID scheme and defines no lane record type, and section 10.6
  requires of a lane name only that it is a non-empty single line, unique within its ledger.
- **Bundle.** A named, ordered group of backlog items delivered as one reviewed change. Bundles
  live as rows of the pipeline control ledger (section 10.6), never as records.
- **Pipeline.** Per lane, the ordered list of the next bundle or single item to work on, then the
  following ones. Entries are drawn from the backlog, the stored order in the pipeline control
  ledger is the authority, and the head entry is the lane's next (section 10.6). `PIPELINE.md` is
  its deterministic render.
- **Milestone.** A roadmap entry that a later release, and the changelog entry accounting for that
  release, discharge. Milestones live as rows of the roadmap ledger (section 10.7), never as
  records.
- **Roadmap.** The future-facing direction: the milestones and themes ahead, ordered by intent,
  never by work sequence. `ROADMAP.md` is its generated render at the product repository root
  (section 10.7).
- **Queue.** Retired as a synonym of pipeline: this specification does not use it, and a generated
  planning surface MUST NOT describe a pipeline as a queue.

Roadmap and pipeline both name generated artifacts rendered from machine sources. No definition
admits a hand-edited `ROADMAP.md` or `PIPELINE.md`: the one optional curated preamble of
section 10.7 is the only curated seam, and it is a block above the generated header, bounded by
the fixed delimiter line as section 10.7 delimits it, never an edit of the generated body.

## 3. Design principles

- **Records first.** The store is the source of truth. A decision, finding, or completion that is
  not recorded did not happen. Human-readable surfaces are derived, never authoritative.
- **Facts are durable; views are re-rollable.** Detailed records are never consumed, rewritten,
  or deleted once frozen. Summaries and views over them may be regenerated, re-rolled, and
  re-worded at any time, because the facts beneath them persist intact.
- **Machine writes, human reads.** Sources are machine-shaped TOML; deliverables are generated,
  prominent, human-readable documents. Nobody hand-edits a generated file; the one curated seam
  above a generated file is the `ROADMAP.md` preamble (section 10.7), a labelled block above the
  generated header, never an edit of the generated body.
- **Location is configuration.** The store's location is a migratable setting, not a mode or an
  architectural commitment. Wherever the store lives, the generated public deliverables
  (`CHANGELOG.md`, `ROADMAP.md`, `VERSION`, and any future public view) are byte-for-byte
  identical; only the committed pointer (`.opf.toml`) changes with the topology. Moving the store
  is a first-class, history-preserving operation.
- **Fail closed.** A gate that cannot read, parse, or resolve an input it is meant to cover reports
  failure or cannot-evaluate, never a clean pass.
- **Determinism where claimed.** Anything called a deterministic render is byte-reproducible from
  its sources. Anything curated by a human is labelled as curated and is gated on its facts, not
  its bytes.
- **Generic by construction.** The base-required schema vocabulary (the standard's own required
  field names and structure) names no particular adopter, operator, or profile; a conforming store's
  own data may name an operator via `actor.id` or a profile via a `[profiles.<name>]` table the
  adopter chose. The standard's own ownership and its reference profile are named as such, never as a
  requirement dependency (section 15).

## 4. Store resolution: roots, pointer, discovery, and naming

### 4.1 Two roots

Two roots organize every path in this standard:

- **The product repository root.** The repository the project ships from. It carries the committed
  store pointer (section 4.3) and the public deliverables (`CHANGELOG.md`, `ROADMAP.md`, and
  `VERSION`, section 5.8). In a monorepo, each project subdirectory that carries its own pointer
  is its own product root, and tooling operates on the product root it is aimed at.
- **The store repository root.** The git repository that tracks `.working/`. Under the default
  configuration this is the product repository itself, so the two roots coincide; after a
  relocation (section 5.4) the store repository is wherever the pointer's target resolves, and
  `.working/` sits at its root.

### 4.2 Layout overview

Base spec 2.0.0, with `[opf].homes = 2`, is the only base version this specification defines.
It includes adoption, the imported series and import (sections 8, 11 and 14). A writer MUST NOT
accept a format that its doctor does not grade deterministically. The reference tooling does not
yet implement base 2.0.0 (section 16.1).

```
<product repository root>/
  .opf.toml                        # committed store pointer (section 4.3)
  CHANGELOG.md                     # curated public changelog (deliverable; section 6.3)
  ROADMAP.md                       # roadmap render, optional preamble (deliverable; section 10.7)
  VERSION                          # deterministic render from version.toml (deliverable)
  .working/                        # the store; present here under the default in-repo configuration

<store repository root>/           # the product repository itself, by default
  .working/
    README.md                      # ownership and regeneration note (deliverable)
    WORKLOG.md                     # deterministic render of worklog.toml
    VERSION.md                     # optional human view of version.toml
    TODO.md  BACKLOG.md  PIPELINE.md
    DONE.md  FINDINGS.md  DECISIONS.md
    BLOCKS.md  HANDOFF.md  REFERENCES.md  CONTRIBUTIONS.md
    CARRIED.md                     # optional profile-dependent area view (section 10.8)
    DECISIONS.toml                 # machine projection (deterministic; section 10.5)
    <TYPE>-INDEX.md ...            # optional 1:1 index mirrors (section 10.1)
    toml/
      manifest.toml                # store manifest and discovery marker (section 9)
      counters.toml                # per-namespace ID high-water marks (section 8.2)
      version.toml                 # version and release ledger (section 6.1)
      pipeline.toml                # pipeline control ledger (section 10.6)
      roadmap.toml                 # roadmap ledger (section 10.7)
      worklog.toml                 # durable operational record (section 6.2)
      <type>.imported.index.toml    # imported records per enabled type (section 8.3)
      worklog.imported.toml         # imported worklog, on its own ID number line
      lease.toml                   # single-writer lease, present only while held (section 5.7)
      init.toml                    # bootstrap provenance of a coupled init (section 9), if present
      backlog_item.index.toml      # typed record files (section 8)
      done.index.toml
      finding.index.toml
      pending_decision.index.toml
      autonomous_decision.index.toml
      block.index.toml
      handoff.index.toml
      reference.index.toml
      contribution.index.toml
      maintainer_decision.index.toml
      preference_pattern.index.toml
      archive/
        2026/
          archive.toml             # enumerates rotated IDs and spans (section 12)
          done.index.toml
          worklog.toml
    archive/
      moved/<source-path>          # default Move destinations (section 14.2)
      adoption/<run-id>/           # retire preimages and archived occupying sources (section 14.2)
    imported/<kind>/<run-id>/      # durable originals, inventories, approvals and receipts (section 14)
    staging/<kind>/<run-id>/       # short-lived staging, evidence-gated reclamation (section 14.1)
    journals/<kind>/               # reserved recovery state, never a view or ordinary op target
      journal/                    # crash-durable frames
      runs/<run-id>/transaction.toml # gate-readable projections
      allocations/<run-id>.toml    # irrevocable ID reservations (section 8.2)
```

When the store has been relocated, the `.working/` tree lives at the store repository root exactly
as drawn, and the product repository keeps only the pointer and the public deliverables. The
per-record layout (section 9) additionally places one file per record under
`.working/toml/<type>/`, with each `<type>.index.toml` acting as the registry.

The imported files are registered managed leaves beside the clean-series files, using the same
enabled-type roster; `worklog` uses `worklog.imported.toml` instead of an
imported index. Their manifest, emitter, upgrade and containment registrations MUST agree.
`opf init` MUST create the imported leaves for every enabled type, create-only and empty; enabling
a further type or module later MUST create its imported leaf in the same act as its clean index.
`opf init` MUST write at zero the imported counter row
of each type that has an imported leaf (section 8.2). Enabling a further type or module MUST also
add its imported counter row in the same act as its clean index, at
zero only where no imported ancestry exists and otherwise at the largest `<n>` of that namespace's
`imported:<NS>-<n>` IDs. Both counter-row duties follow from the section 8.2 rule that requires
the imported counter rows. They are machine
records, distinct from the original-source evidence under `.working/imported/`. The first
imported-series release MUST keep these files inline in either store layout and MUST NOT provide
views over imported data; assistants read the TOML. Historical releases remain in `version.toml`
(section 14.3); there is no `version.imported.toml` or `CHANGELOG.toml`.

The reserved children `archive/`, `imported/`, `staging/`, and `journals/` are store-tree control
area, neither machine-store records nor adopter content; they relocate with the machine store.
OPF MUST NOT write state outside `.working/` except the operation-lock and coupled-init
substrate in the git common directory, and MUST NOT write any under `.aiqt/`. The record archive
MUST remain inside the discovered machine store, and the example name `toml` MUST NOT be hardcoded.

The closed kind vocabulary is `import`, `ingest`, `adoption`, `layout`, `preview`, `record`.
Import and
ingest run IDs use `imp-<YYYYMMDD>T<HHMMSS>Z-<hash16>`; adoption uses `adopt-` with that
suffix. Layout and preview reserve `layout-` and `preview-` with the same suffix. Record
reserves `record-` with the same suffix; it is a journal-only kind that names just its
journal home, `journals/record/`, never a staging or imported home. Here
`hash16` is 16 lowercase hexadecimal characters; constructors check lexical shape, not calendar
validity or filesystem safety. File operands MUST use canonical contained relative paths: no empty,
dot, or parent components, absolute/drive/backslash forms, control characters, or line separators.

Init, and any upgrade, MUST render this managed block into `.working/.gitignore` from the
topology constants:

```gitignore
# >>> opf-managed >>>
/journals/
/staging/
# <<< opf-managed <<<
```

Durable `imported/` and `archive/` evidence MUST stay tracked. Installation MUST inspect effective
ignore rules and the index first; tracked staging or journals MUST require an explicit reviewed
untracking change, never silent index mutation. The block travels with the store and joins the
indexed-ignore candidate set. At homes 2 an implementation MUST register `.working/.gitignore` by
its exact path as a managed control file that containment recognizes as OPF control area;
containment never reads it for drift, and the doctor does not yet grade drift of its managed block.
Gitignore is not access control: `git add -f` can stage ignored
state. Journals are machine-local even after completion; a clone without them cannot recover those
transactions, and requested recovery MUST fail closed on a missing journal. Containment and doctor
exclude journals and make no recovery claim, with one exception: the doctor reads the reservations
under `journals/<kind>/allocations/` read-only, and only for the section 8.2 counter checks; any
other journal content, a rogue file included, is outside their coverage.

A store whose adoption home `.working/imported/adoption/` exists has started an adoption and
receives the adoption grading: each admitted run's recorded paths are registered, the
non-occupying retire, move and migrate rows of its plan (and only those) are its frozen
sources, and a frozen source whose live bytes still match its plan digest is graded as bounded
adoption state while a drifted or vanished source is a containment failure at `required`
(section 11).
At homes 2 the doctor does not yet grade that adoption home: it reports a store holding it as
cannot-evaluate until adoption grading lands there.
The doctor MUST decide that a run is admitted, and that its retirement is recorded, from the
committed adoption evidence alone, the bundle under `.working/imported/adoption/<run-id>/` and
the run archive, which travel with every clone, and MUST NOT read the machine-local journal, so
a clone without journals grades a run's admission and recorded retirement exactly as the original
store does. That parity covers adoption admission and recorded retirement alone: the doctor's read
of the section 8.2 reservations under `journals/<kind>/allocations/` makes a clone's counter
grading differ from the original store's, a residual section 17 discloses. That evidence check verifies
internal consistency: the sealed inventories, plan and approval bound to the run id of the
directory they sit in, and the listed bundle, archive and Move-root bytes at their recorded
digests (a Move-root row counts only as a move destination the run's own plan records).
The apply side MUST write each adoption inventory's `[adoption]` identity table,
whose keys are exactly `run_id`, `phase` and `plan_digest` as the bundle layout below defines,
when it derives the inventory, and the doctor MUST refuse an adoption inventory whose identity is
missing or malformed, names another run, names a phase other than the one its file name carries,
or names a plan digest other than the run's proven plan's own (the frozen plan that re-seals its
own bytes and that its approval binds), so an inventory copied from another run or phase, an
empty retirement record included, never evaluates as this run's record.
The apply side's bundle verifier, through which `opf adopt status` reports a run, MUST hold every
adoption inventory to that bar against its bundle's own `plan.toml`: it MUST yield cannot-evaluate
for an inventory that names a phase other than the one its file name carries or a plan digest
other than that plan's, and for every inventory of a bundle whose `plan.toml` is absent,
unreadable or not canonical, names another run, or carries a `plan_digest` that does not re-seal
its own bytes, an empty base inventory included (a bundle with no inventory is its own named
finding). It MUST check that plan's inventory row against the same bytes its seal was proven from.
It does not check the approval's binding, which the doctor's admission checks.
A retirement is recorded only by a sealed retirement inventory in the shape the
retirement-phase transaction derives from its own create ops: one row per move row of the plan,
occupying or not, whose recorded Move destination (its move-file destination) lies beneath
.working/archive/moved/, naming that destination at the moved source's plan digest, and nothing
else, so the record of a plan without such a move row lists no files. Those are the bytes the
relocation writes: the frozen live source of a non-occupying move, and for an occupying move
the committed archive copy the base inventory claims at that same digest. Retire and migrate
preimages are preserved at apply and claimed by the base inventory, never re-listed by the
retirement record; that shape also binds the record to its phase, because a base inventory
copied to the retirement name lists at least the plan and the approval, which are never Move
destinations. A retirement row whose path a base inventory row also names is a path claimed
twice and MUST yield cannot-evaluate; a listed destination that does not hold its recorded bytes
live MUST yield cannot-evaluate, and before a recorded retirement a file at a plan Move
destination beneath .working/archive/moved/, occupying or not, MUST be a containment finding,
since only the retirement-phase transaction creates that path (containment never grades an
explicit destination outside the store).
The whole check detects accidents: an interrupted apply, a hand edit that is
non-canonical or that changes listed bytes, and a misplaced or stale record. It does not detect
deliberate forgery: a hand edit that re-emits a canonical, self-consistent record, and any
other crafted self-consistent bundle, is outside the accident-detection model, consistent with
the rest of OPF. An implementation MUST register the imported managed leaves, the adoption archive
`.working/archive/adoption/<run-id>/`, the Move destination `.working/archive/moved/`, and the
evidence bundles `.working/imported/<kind>/<run-id>/`, all recognized by containment as OPF
control area, and MUST add the four section 8.3 imported-series checks to the doctor roster of
every store. The section 14.1 completion checks MUST still carry their own evidence digest
verification beside C-EVIDENCE-ENUM.

Each evidence bundle `.working/imported/<kind>/<run-id>/` carries its own inventories at its
root: `inventory.toml`, plus a new `inventory-<phase>.toml` for each later phase, where `<phase>`
is a lowercase letter followed by up to 31 lowercase letters or digits. Each holds exactly
`format = "opf.evidence.inventory/v1"`, a `file` array and, in an adoption bundle only, the
`[adoption]` identity table below; the `file` rows have exactly `path` (a canonical
store-relative file path spelled from `.working/`), `size` (a nonnegative integer), and `sha256`
(64 lowercase hex digits). A row may name a member of its own bundle other than a
bundle-root inventory, a Move destination, default or explicit, under `.working/archive/moved/`, or, for an
adoption bundle, a preserved file of the same run, a retire preimage or an archived occupying
source, under `.working/archive/adoption/<run-id>/`.
An adoption bundle's inventory MUST also hold exactly one `[adoption]` identity table whose keys
are exactly `run_id`, `phase` and `plan_digest`: the bundle's own run id, the phase this
inventory records, spelled `base` for `inventory.toml` and as the file name's `<phase>` for a
later phase, whose name MUST NOT be `base`, and the run's approved plan's own `plan_digest` in
the `sha256:` form with 64 lowercase hex digits. An inventory of any other kind MUST NOT carry
that identity table. The apply side MUST write that identity when it derives the inventory.
C-EVIDENCE-ENUM MUST yield cannot-evaluate for an adoption inventory whose identity is missing or
malformed, names another run, names a phase other than the one its file name carries, or names a
plan digest other than its bundle's own sealed `plan.toml` digest, and for every inventory of an
adoption bundle whose `plan.toml` is absent, unreadable or not canonical, names another run, or
carries a `plan_digest` that does not re-seal its own bytes, so an inventory copied from another
run or phase never evaluates as this run's record. C-EVIDENCE-ENUM MUST check that `plan.toml`'s
inventory row against the same bytes its seal was proven from, so a plan swapped between two
reads never combines into a clean result.
The owning writer MUST derive each inventory from the run's transaction record or receipt and
MUST publish it exclusively with the retained bytes. An inventory MUST NOT be rewritten,
so a bundle stays immutable and an evidence commit changes only its bundle folder. An inventory is
not a journal projection and remains available in a clone without journals.
A phase inventory MAY be published in the same transaction as the base inventory to claim the
promotion receipt without creating a receipt/inventory digest cycle.

C-EVIDENCE-ENUM reconciles exact membership, directory structure, regular-file types, sizes and
digests: every payload file under `.working/imported/` and `.working/archive/`, meaning every file
other than a bundle-root inventory, is claimed by exactly one row, and every inventory is itself
schema-checked against the shape above rather than claimed. Unlisted or unclaimed entries, a bundle
without an inventory, and missing listed files MUST be findings; unreadable or malformed inputs,
including a path claimed twice, MUST yield cannot-evaluate.
A phase inventory MUST NOT substitute for a missing
`inventory.toml`: such a bundle cannot evaluate. Deleting a whole bundle (inventory and payload
together) is outside this local snapshot check; independent history is required to detect that
loss. Inventories assert membership, not authenticated actor history. The contained reader's size
ceiling still applies.

`staging/` MUST be walked and stray-graded, including empty runs; an unknown kind MUST always be a
finding. The existing staged-plan presence test also recognizes import and ingest runs in their
typed staging homes. Partial status is receipt-bound under section 11, not inferred from
staging. Doctor MUST NOT consult a journal to decide partial status and makes no claim that
a staged plan has a recoverable transaction. Ordinary transaction operands, including
those of an open transaction being recovered, MUST NOT equal, descend from, or contain `journals/`.
Capability-bound journal APIs MUST derive their destinations from kind and run
identity. An ID reservation under `allocations/` MUST be created exclusively and create-only,
made durable before it is relied on and never rewritten, so an interrupted publication leaves
no reservation or the complete one (section 8.2).
These comparisons are byte-exact: on a case-insensitive or normalizing filesystem, a differently
cased or composed spelling can alias a reserved home and is not caught. Discovery precedes the
manifest: it MUST examine `manifest.toml` in every immediate
subdirectory, including `journals/`, MUST fail closed on a reserved-name match or ambiguity, and
MUST NOT read deeper there.


### 4.3 The pointer

The store is resolved through a committed pointer plus manifest discovery, with no hardcoded path.

`.opf.toml` at the product repository root is the committed store pointer: lowercase machine
source (section 4.6), tracked in the product repository. It carries a `[store]` table whose
`target` names where the store repository lives, in the typed target syntax of section 5.5:

```toml
[store]
target = "dir:."      # the default: the store rides this repository, at .working/
```

A relocated store points wherever it now lives:

```toml
[store]
target = "git@git.example.com:acme/product-ops.git"
```

Resolution rules:

- An uncommitted, machine-local override file `.opf.local.toml` (same shape, never committed, and
  ignored by version control) MAY override or complete the pointer on one system, for targets that
  only make sense there: a local-only store's absolute path, or a private store that only the
  maintainer's systems can resolve (section 5.8). The committed pointer MUST be safe to publish;
  anything machine-local or private-only belongs in the override.
- Resolution order is the local override first, then the committed pointer. Where neither file
  exists, the default location (`.working/` at the product root) is tried; a valid manifest found
  there resolves as the store. Where no pointer exists and no default store is found, there is
  nothing to operate on and `opf init` is the remedy.
- A pointer that exists but does not resolve (the target unreachable, or no valid manifest at the
  target) is a cannot-evaluate outcome: the tool reports it and stops. It never falls back
  silently to the default location, which could resolve a different store than the one intended.
- The tracked-store requirement (section 5.1) is checked against the resolved store, wherever the
  pointer says it lives, never against an assumed location.

Relative `dir:` paths in the pointer are interpreted against the product repository root, which is
the named fixed root for this file; any other path in a pointer MUST be absolute.

### 4.4 The machine store

Machine-store TOML records live in `.working/toml/`. The directory name `.working` at the store
repository root is fixed by this standard. The machine subdirectory's standard name is `toml`;
tooling MUST NOT hardcode it, and MUST locate it by discovery. The names `imported`, `archive`,
`staging`, and `journals` are reserved at the store level for OPF control area and MUST NOT be
used as a machine subdirectory name; discovery fails closed on a machine store so named.

### 4.5 Manifest discovery

Within the resolved store repository, tooling locates the machine store by finding exactly one
immediate subdirectory of `.working/` containing a `manifest.toml` that declares
`standard = "opf"` in its `[opf]` base table, trying `toml` first. Zero matches, or more than one,
is a cannot-evaluate outcome: the tool reports it and stops; it never guesses, and never treats it
as an empty or absent store. The pointer names which repository carries the store; the manifest
discovery observes where, within it, the machine store sits. Because the machine subdirectory is
observed at each use rather than declared and trusted, renaming it is a directory move with
nothing to go stale; the pointer, which does declare a location, is validated at every resolution
and fails closed rather than trusting a stale target (section 4.3). Profiles declared under
`[profiles.<name>]` are enumerated after the base is validated; a profile a tool does not support
is ignored for enforcement and recorded as unevaluated, never treated as a base-validation failure
(section 9).

An ambiguous outcome and an input that discovery cannot read or parse are a failed discovery of an
existing store and MUST NOT be treated as an absent store that permits initialization or adoption.
A zero-match outcome over a present `.working/` MUST NOT be treated as authorizing initialization
or adoption by itself: only a section 14 first adoption authorizes initialization there, through an
investigation that distinguishes first adoption from re-adoption and records a digest-stamped
inventory, and one approved plan that gives every foreign file a disposition before `init-store`
(section 14.1). A discovered manifest that the section 9.2 validation refusals refuse for
declaring a `spec_version` below 2.0.0, whatever its `[opf].homes`, is refused as a store
(section 9.2): it MUST NOT be treated as authorizing initialization or adoption. A tree under
such a manifest MUST NOT be adopted until the operator has moved that manifest aside by hand, a
step no OPF command performs; its files are then ordinary foreign content for a section 14 first
adoption (section 14.1). Files remaining under the reserved store control children
(section 14.2) are the one exception: an adoption option MUST NOT select them, so the operator
moves them aside by hand on the same terms, a step no OPF command performs, before that first
adoption can complete. A discovered
manifest declaring a `spec_version` of 2.0.0 or above whose `[opf].homes` is missing or not the
integer 2 is refused as a store (section 9.2), never foreign content: it MUST NOT be treated as
authorizing initialization or adoption. A manifest refused only at the section 9.2 version ceiling marks a store at a later version, never foreign
content: it MUST NOT be treated as authorizing initialization or adoption, and its remedy is the
tooling upgrade alone (sections 8.2 and 9.2).

### 4.6 Casing convention and rationale

Source files are lowercase; deliverables are uppercase.

- Every file inside `.working/toml/` is lowercase: `manifest.toml`, `counters.toml`,
  `version.toml`, `pipeline.toml`, `roadmap.toml`, `worklog.toml`, `worklog.imported.toml`,
  `lease.toml`, `init.toml`, `<type>.index.toml`, `<type>.imported.index.toml`, `archive.toml`.
  The pointer `.opf.toml` and its local override are lowercase machine source on the same terms.
- Every generated deliverable at `.working/` top level, and the public deliverables at the
  product repository root (`CHANGELOG.md`, `ROADMAP.md`, `VERSION`), is uppercase.

The rationale: uppercase filenames are the recognized cross-industry norm for read-me-first
documents (README, LICENSE, CHANGELOG), they sort to the top of directory listings, and their
prominence signals "this is the surface a human reads". Lowercase signals machine-owned source that
humans change only through tooling or review, never casually. The casing itself is part of the
contract: a lowercase file MUST NOT be a deliverable, and an uppercase file MUST NOT be
hand-authored truth.

## 5. The store is a git repository: location, migration, and consistency

### 5.1 Always a git repository

A conforming store MUST be tracked in a git repository, wherever it lives. An untracked or ignored
`.working/` tree is a hard failure in scaffolding and validation, not a warning: an untracked
store has no history, no change evidence, and no durability, which defeats the purpose of keeping
records at all. There is no gitignore fallback. The check runs against the resolved store
(section 4.3): whichever repository the pointer resolves to must actually track the tree. A store
placed in a plain directory conforms only once that directory is itself a git repository (the
local-only pattern, section 5.3); "somewhere git does not reach" is not a location the standard
recognizes.

Privacy is achieved by where the tracked store lives, never by leaving it untracked. Adopters
remain free to ignore anything outside `.working/`; the tracked-store requirement covers the
store, not the rest of the tree.

### 5.2 Location is a configuration

The store's location is a free configuration, not a fixed set of modes.

The default is `.working/` in the main product repository: zero configuration, created by
`opf init`, with the development process public to everyone who can read the repository. This is
deliberate: the simplest conforming posture is also the most transparent one, and a project that
wants a private process opts into it by relocating the store, not by weakening tracking.

From the default, the store can migrate anywhere (section 5.4). The patterns in section 5.3 are
just configurations of the same machinery: nothing in the store's format, gates, IDs, or views
changes when it moves, and the product repository's generated public deliverables are identical
wherever the store lives (section 5.8).

### 5.3 Location patterns

Any location a target (section 5.5) can name conforms, provided the store is tracked
(section 5.1) and operated under the consistency contract (section 5.7). Four patterns are common
enough to name:

- **In-repo (the default).** The store rides the product repository at `.working/`. Simplest;
  suits projects whose process is already open. The store's consistency is the product
  repository's own branch-and-merge discipline.
- **Private companion repository.** The store lives at the root of a separate, private repository,
  paired with the public product repository. The development process stays private, works across
  multiple systems with full history and change evidence, and the product repository carries only
  the pointer and the generated public deliverables. Where the development records are not
  intended for publication, this is the pattern this standard suggests.
- **Local-only, self-backed.** The store lives in a local directory that is its own git
  repository, never pushed anywhere. Maximum locality, no egress; but there is no sync target, so
  durability is wholly the adopter's own backup discipline. Choosing this pattern is choosing to
  own that backup, and the choice SHOULD be recorded as a maintainer decision; the residual is
  disclosed in section 17.
- **Monorepo, per-project.** Each project subdirectory carries its own `<project-subdir>/.working`
  store and its own pointer, making each subdirectory an independent product root (section 4.1).
  Stores never share counters, manifests, or leases across projects.

### 5.4 Migration is first-class

`opf migrate --store <target>` relocates the tracked store to any location a target can name. The
operation MUST:

- run under the consistency contract and the single-writer lease (section 5.7), refusing to start
  from a stale, ahead, or divergent store;
- validate the target before any push, per section 5.6: the destination is confirmed to be the
  recorded, intended target, never inherited from ambient state, and a store is never pushed to an
  unexpected place;
- preserve the store's git history into the destination repository through a history-preserving
  extraction, and preserve the durable worklog and its archive byte for byte: a
  relocation that flattens history into a single import commit, or that loses or rewrites any
  worklog entry, is nonconformant;
- keep the generated public deliverables in the product repository: `CHANGELOG.md`, `ROADMAP.md`,
  and `VERSION` remain at (or are restored to) the product repository root, and the render targets
  are rewired so future renders keep writing them there (section 5.8);
- re-point the committed pointer, and the manifest's recorded sync target, in the same change, so
  the pointer, the manifest, and the actual remote never disagree across a landed state;
- verify the destination before retiring the source: the relocated store is cloned back and
  reconciled (ledgers, indexes, counters, and worklog digests confirmed identical) before the old
  location is removed or archived. The old in-repo `.working/` tree leaves the product repository
  only in the migration change itself, after that verification, and the removal is recorded. An
  unverified destination never justifies destroying the source: this is the
  verified-restore-path discipline applied to the store itself;
- record the relocation as a worklog entry naming both the old and the new location.

Migration is symmetric: a store can move in-repo to companion, companion to in-repo, anywhere to
anywhere, repeatedly, and each move is one recorded, verified, history-preserving operation.

### 5.5 Target syntax

The canonical form of a target, in the pointer and as the argument to `opf migrate --store`, is a
git URL or a filesystem path. Git already speaks every transport it needs to clone and sync such a
form, and the host in a remote URL already distinguishes GitHub, GitLab, Gitea, and any self-hosted
forge, so the standard defines no per-host syntax for synchronization. A dedicated sync target names
a filesystem repository only as `git:<absolute path>` (section 5.6).

Explicit typing exists only where git cannot infer what to do, which is creating a new remote and
authenticating that creation:

| Form | Example | Git infers sync? | Provider needed for |
|---|---|---|---|
| `dir:<path>` or a bare path | `dir:../product-ops-store` | git can sync to a path, but OPF does not: this form is a store location, never a sync target (section 5.6) | creating the local repository |
| `git:<url>`, `git:<absolute path>` or a bare git URL, other than a `file://` URL (refused as a sync target, section 5.6) | `git@git.example.com:acme/ops.git` | yes | nothing; the remote must already exist |
| `github:<owner/repo>` | `github:acme/product-ops` | yes, after creation | creating the remote and authenticating creation through the host API |
| `gitlab:<owner/repo>` | `gitlab:acme/product-ops` | yes, after creation | same, for GitLab |

A `dir:` target names a directory that is, or will be initialized as, its own git repository (the
local-only pattern). A typed host form resolves, after creation, to an ordinary git URL, which is
what the pointer then records; the typed form is a creation convenience, not a parallel transport.

### 5.6 The provider registry

Target handling is extensible through a provider registry with the same shape as the
`[types.<name>]` registry (section 9): one `[providers.<name>]` table per provider in the
manifest. Each provider is a handler covering some or all of three roles: `create` (make a new
store location), `auth` (authenticate creation with the host), and `sync` (clone, fetch, push).

- `local-directory` and `generic-git-remote` ship as the universal fallbacks and cover every
  target between them: any local path and any git URL on any host. A dedicated sync target (the
  manifest's `[store] sync_target`, section 9) is synced as a git remote, so it names a filesystem
  repository only as `git:<absolute path>`; a `dir:` or bare-path form is a store location for the
  pointer and `opf migrate --store`, never a sync target, and validation refuses it as one
  (section 11). Validation likewise refuses a relative `git:` path and a `file://` URL as a sync
  target, and refuses as ambiguous a `git:` absolute path, or an actual remote path compared against
  one, with leading or trailing whitespace, since whitespace is significant in a path. A `dir:`
  sync target is classified as a `dir:` form first; any other value containing `://` is a URL, for
  the sync target and the actual remote alike, because git reads `://` as a scheme separator:
  `/srv/a://repo` is never a filesystem path. Git reads such an actual remote as an unsupported
  protocol (or as a bundle file at the path it spells, which takes no push), so against a
  `git:<absolute path>` target whose path differs from that spelled path it is a mismatch; where the
  two paths are the same (`git:/srv/a:/repo` against `/srv/a://repo`) validation reports it as
  cannot-evaluate (a disclosed residual). A URL sync target or actual remote with leading or
  trailing whitespace is refused the same way, since git does not trim it. With a dedicated sync
  target, an actual remote that is present but blank (whitespace only) is refused as naming no
  remote; a relocated local-only store, which declares no sync target, reads such a remote as
  absent. An actual remote spelled as a `file://` URL is not compared against a
  `git:<absolute path>` target, even where git pushes to the same repository through it: validation
  reports it as cannot-evaluate (a disclosed residual). The pre-commit hook carries each push URL as
  validation reads it and exits 2 (cannot-evaluate) for a push URL that holds a line break, which
  its snapshot cannot carry.
- `github` and `gitlab` plug in only for their create and auth API conveniences; their sync is
  ordinary git. Further hosts join by registering a provider, never by extending the target
  grammar.
- Authentication uses the adopter's existing git credentials (SSH keys, tokens through git's own
  credential machinery). OPF stores no credentials of its own, ever.
- An unregistered provider is unavailable until it is reviewed and registered, on the same posture
  as any other tooling dependency.

Egress discipline binds every provider: a provider's create and auth calls go only to the host the
target itself names, and before any push the tooling confirms the actual push destination against
the recorded target (the pointer and the manifest's recorded sync target). A destination that
appears from anywhere else, ambient configuration, a stale remote, or retrieved content, is
surfaced and refused, never pushed to. A store is never pushed to an unexpected place.

### 5.7 The store consistency contract

Nothing stale, nothing ahead. Before any OPF operation other than the reconciliation step itself
(`init`, `adopt`, `import`, `doctor`, `render`,
`migrate`, `upgrade`, `absorb`, `record`; `opf sync` is that surfaced reconciliation step), the
store repository MUST be reconciled to a
known-consistent, up-to-date state against its sync target: the target is fetched and the local
store compared against it. `opf report` (section 10.8) is outside this contract: it reads the local
store as found, takes no lease, and reads no network, so a report run against a store that is
behind its target lists that store's state as found (section 17).

- **Equal:** the operation proceeds.
- **Behind the target:** the tooling MUST refuse to operate and MUST surface the state. The remedy
  is a fast-forward pull to current (`opf sync`), which the tooling MAY offer and perform as its own
  surfaced step, then re-run the operation; the pull is never folded silently into another
  operation.
- **Ahead of the target** (local commits not yet pushed, the lease still held by the resuming
  holder, and no divergent remote side): the tooling MUST refuse to operate until the store is
  reconciled, and reconciliation is an authorized push of the pending local commits. The holder
  MUST confirm and push them as its own surfaced step, never folded silently into another operation;
  the push is safe precisely because there is no divergent side that a push could lose. This is the
  recovery path for a store left ahead by a crash between a local write and its sync-back.
- **Divergent from the target** (unsynced commits on two systems): the tooling MUST refuse to
  operate and MUST surface the state. A divergence MUST halt for the human, always: it MUST NOT be
  auto-merged or silently resolved by picking a side, because a textual merge of the store's TOML
  records can silently mangle the very records the standard exists to protect.
- **After any operation that writes,** the store MUST be synced back to its target in the same
  session, so the store is not left intentionally ahead on one system; a crash between the local
  write and the sync is detected on the next resume as an ahead-only or a divergent state and
  MUST be reconciled by the matching path above (an authorized ahead-only push by the lease holder,
  or a human-resolved halt on divergence), never left standing.

A **single-writer lease** prevents concurrent divergent writes: before mutating the store, a run
MUST take the lease (`lease.toml`, present only while held, carrying the holder, the operation, and
an acquired-at timestamp read from the clock) and MUST make it observable at the sync target before
its writes begin, so a second system's reconciliation sees the held lease and refuses. A lease MUST
NOT be seized from a live holder; it MUST be reconciled against recorded state on resume or close,
and a leftover lease from a dead run MUST be released only through that reconciliation. Where
the concurrent-operation module is enabled, the lease MUST additionally be recorded as a
`session_lease` record. There is a residual window between taking the lease and its reaching the
target in which two systems can both begin; the divergence check above is the overlapping control
that catches that collision after the fact, and the two layers together are the guarantee (disclosed
in section 17).

This contract states two generic operational requirements inline. First, a **single-writer
lease**: a run MUST hold a lease so two runs never act on the same store state at once, MUST
reconcile it on resume or close, and MUST NOT seize it from a live holder. Second, **reconcile the
record against reality**: the store is authoritative only while it matches what is actually in use,
so divergence MUST be detected by observation at defined checkpoints and treated as a finding to
resolve, never a discrepancy to leave standing, and a store MUST NOT certify itself current merely
because nothing updated it. AIQT's concurrency-lease and reconcile-record-against-reality rules are
the reference implementation of these two requirements; the requirements themselves are the
standard's and bind any conforming adopter.

Scope of the contract by pattern:

- **A store with a dedicated sync target of its own** (a companion repository, or any relocated
  store with a remote) is bound by the full contract above: OPF tooling is the writer, and it
  pulls current, refuses on divergence, and syncs back after.
- **The default in-repo store** has no dedicated sync target; it rides the product repository,
  whose own version-control discipline (branch and merge on green) is the consistency mechanism
  across systems. There the contract reduces to the lease plus a clean-state check: the store
  paths in the working tree carry no conflict markers, no mid-merge state, and no concurrent OPF
  run, or the tooling MUST refuse.
- **A local-only store** has no sync target, so the behind/ahead axis does not exist; the lease
  still guards concurrent runs on the one system, and durability is the adopter's recorded backup
  responsibility (section 5.3).

**Parallel branches allocate against the integration base.** The lease serializes writers on one
store, but two branches of a store that rides the product repository each start from the same
committed `counters.toml`, so each can claim the same record ID. Store files therefore MUST NOT be
hand-merged: after a merge conflict on a store path, take the integration base's version of the
conflicted store files and redo the authoring operation on that base, which claims the next ID
afresh (section 8.8). The byte-reproduction precondition of `opf record` and `opf upgrade` refuses
only a store file whose bytes are not the canonical serialization of its content, such as one
carrying comments or non-canonical formatting. The canonical serialization writes U+2028 LINE
SEPARATOR and U+2029 PARAGRAPH SEPARATOR inside a string as the escapes `\u2028` and `\u2029`; a
file that differs from it only by holding either character literally inside a basic string, as files
written by earlier tooling do, still passes, reads back as the same values, and is re-spelled with
the escapes by its next write. A write that would grow a store file past the store reader's size cap
refuses instead, before anything is written, so an upgrade or record operation never rewrites a
readable store into one the reader refuses. The `DECISIONS.toml` machine projection (section 10.5)
takes the same re-spelling without a generator-version bump: a projection an earlier tool rendered
from a record holding either character differs from the current render in exactly that spelling, and
the byte-level view-drift gate reports it as drifted until one re-render re-spells it. A projection
over records holding neither character renders byte-identically, so a store without these characters
sees no drift. `opf doctor`, and the pre-commit hook that runs it, also refuses a machine-store TOML
file that is not in canonical form, at every run rather than only before a write: such a file is a
C-CONTAINMENT finding, with the same allowance for a literal U+2028 or U+2029. It leaves out a path
under a valid `[unmanaged]` declaration (the containment walk grades the declaration, never the
files under it), the legacy import staging area, which the containment walk grades, the two
planning ledgers `pipeline.toml` and `roadmap.toml`, whose canonical form sections 10.6
and 10.7 define over this section's serialization and whose departures C-PIPELINE and
C-ROADMAP report, so one defect is reported once, and a file it cannot read or parse,
which the check that reads it grades (except `init.toml`, which no other check reads, so
an unreadable one cannot be evaluated and an unparseable one is a finding). During a
partial import backed by an active import run, it also leaves out the stray paths the containment
and archive walks triage there (section 14.2): a file outside the managed set and outside the
archive tree (which, in an adopting store, the containment walk reports as a finding instead), and,
within the archive tree, a file directly under `archive/`, a file under a bucket subdirectory, or a
bucket file other than `archive.toml`, `worklog.toml` and a `<type>.index.toml`. Nor does it enter,
there, a directory beneath which it leaves out every path: outside the archive tree, a directory
that is not a managed namespace derived from the manifest (a per-record type directory, the
generation-2 worklog directory or an ancestor of a store-scope view target), and, within it, a
bucket subdirectory, so a symlink, an unreadable directory or deep nesting beneath one does not stop
the store being evaluated. A bucket's `archive.toml`, `worklog.toml` and `<type>.index.toml` are
checked at every import status. A hand edit or hand merge that leaves canonical bytes passes both the
precondition and doctor undetected, so the integration-base rule above is a separate requirement
that neither enforces. A merge that resolves without a conflict yet duplicates an ID is caught by
`opf doctor`, which checks store-wide ID uniqueness and that every ID lies within its counter (section
8.2). A collision MUST NOT be resolved by decrementing a counter or reusing an ID.

### 5.8 The public deliverables are identical across topologies

Generated public deliverables always live in the product repository: the root `CHANGELOG.md`, the
root `ROADMAP.md` (section 10.7), the root `VERSION`, and any future public view. This holds
identically whether the store is in-repo, a private companion, local-only, or anywhere else; a
reader of the product repository sees the same generated public deliverables, byte for byte,
whatever the topology. The committed pointer (`.opf.toml`) is the one part of the surface that
does change with the topology: it names where the store lives (for example `dir:.` for an in-repo
store, or a companion target), so it necessarily differs between topologies. Only the maintainer's
systems need resolve a private store; for everyone else the pointer is an inert file and the
public deliverables are the whole story.

Publication is stage-then-promote: `opf render` writes into the product repository only bytes that
have passed the store's gates, and those bytes land through the product repository's normal
review flow like any other change. Rendering from a private store into the public product
repository is the promotion step, and it never promotes anything the gates have not passed.

## 6. The release triad: version.toml, worklog.toml, and CHANGELOG.md

Three artifacts, deliberately separated so the version anchor, the detailed record, and the public
story cannot tangle: a machine ledger of releases, a durable worklog of changes, and a curated
summary for the public. The ledger anchors versioning; the worklog holds every fact; the changelog
tells the story and can always be retold because the facts persist beneath it.

### 6.1 version.toml, the version and release ledger

`.working/toml/version.toml` is the machine ledger of version numbers, release dates, and release
boundaries. It is the single source for the project's version: the root `VERSION` file is
deterministically generated from it (the latest release's version, as exact bytes) and drift-gated,
and an optional human view renders to `.working/VERSION.md`. The reference suite's release-delta
tooling (the check that computes the minimum required version bump for a change) anchors here; it
is a consumer of the ledger, not part of the base standard's definition. The ledger is not the
changelog: it carries numbers, dates, spans, and digests, and MUST NOT carry release prose.

Each `[[release]]` row records:

- `version`: the SemVer version string, unique in the ledger.
- `date`: the release date, RFC 3339 UTC, read from the clock at the release event.
- `worklog_span`: the inclusive, contiguous span of worklog entry IDs the release covers, as a
  two-element array `["WL-1", "WL-88"]`, or an empty array for a release with no worklog entries.
- `coverage_digest`: a digest over the canonical serialization of the covered worklog entries, in
  ID order, computed at release cut. The exact canonicalization is fixed by the schema release that
  follows this specification; it MUST be deterministic and cover the entries' full content.
- `imported`: optional boolean, permitted only as `true` and only on a historical release recorded
  under section 14.3. On an imported-flagged row, `date` carries the source-recorded release date
  rather than a clock read at a witnessed release cut, `worklog_span` MUST be empty, and the row
  rests on imported provenance. A witnessed release cut MUST NOT set the flag, and the flag MUST NOT
  be added to or removed from an existing row. Imported-flagged rows MUST form a prefix of the
  ledger, before any witnessed row, and a writer and a validator MUST both enforce it.

Release rows MUST be append-only and immutable once written. Spans MUST be contiguous and
non-overlapping across consecutive releases, in ID order, so the released worklog tiles exactly and
the unreleased tail is everything after the last span.

The ledger also carries the summary rows that back the public changelog. Each `[[summary]]` row
records:

- `covers`: a single released version (`"1.3.0"`), an inclusive range over contiguous released
  versions (`"1.0.0..1.2.3"`), or `"unreleased"` for the optional working section.
- `status`: `working`, `published`, or `superseded`.
- `digest`: required once `status` is `published` or `superseded`; the freeze digest of the
  corresponding `CHANGELOG.md` entry (section 7.2).
- `superseded_by`: present exactly when `status` is `superseded`; the `covers` token of the rollup
  summary that replaced this one.
- `imported`: optional boolean, permitted only as `true` and only on a summary row whose digest
  rests on imported provenance under section 14.3. A flagged row MUST have `status` `published` or
  `superseded`, MUST NOT cover `"unreleased"`, and every version it covers MUST be an
  imported-flagged `[[release]]` row, and a validator MUST refuse a flagged row that breaks any of
  these conditions. Unlike the release-row flag, the summary flag MAY be removed from an existing
  row, and its removal is a curator act. A curator MAY likewise add the flag to an existing summary
  row, as a curator act, only where every version the row covers is an imported-flagged
  `[[release]]` row.

Summary rows MUST hold digests and ranges only, never prose. Prose MUST live in exactly one place:
the root `CHANGELOG.md`.

### 6.2 worklog.toml, the durable operational record

`.working/toml/worklog.toml` is the detailed operational record: one entry per change, appended as
the work happens. It generates the deterministic view `.working/WORKLOG.md`.

The worklog is durable and mutable-until-release, never deleted. An unreleased entry MAY be
corrected in place through ordinary review; once a release freezes its span the entry is immutable;
and no entry is ever consumed, rolled away, or deleted. Every fact ever recorded stays in the
worklog (or its archive, section 12), and survives store relocation byte for byte (section 5.4).
This durability is what makes the changelog safely re-rollable: a summary can be re-worded or
re-rolled at any depth because the detail it summarizes is never lost.

Each `[[entry]]` row is a worklog record (type `worklog`, namespace `WL`, section 8) carrying its
ID, timestamp, actor, a change kind (`added`, `changed`, `fixed`, `removed`, `security`, `docs`, or
`infra`; a manifest MAY register additional kinds), a one-line summary, optional detail, and links
to the records and revisions it concerns.

Entry mutability follows the release cut. Before its span is frozen by a release, an entry MAY be
corrected through ordinary review (never deleted). At release cut, the release's `coverage_digest`
freezes the covered entries; from then on any change to them is a gate failure. An entry MUST NOT
be appended into an already-released span: spans are contiguous frozen ID intervals, so a
post-release correction is a new entry in the current unreleased tail, linking the entry it
corrects. Late attribution to a published release is thereby impossible by construction rather than
forbidden by policy.

### 6.3 CHANGELOG.md, the curated public summary

The public changelog lives at the product repository root as `CHANGELOG.md`; wherever the store
lives, the changelog's home is the product repository (section 5.8). It is machine-drafted (from the
worklog entries in range, the version ledger's `[[release]]` rows, and the `done` completion receipts
those worklog entries link) and human-curated: a summary of the worklog over declared version ranges, not a
deterministic render, and not byte-drift-gated. There is exactly one public changelog; it is
conceptually single-sourced from the store (the worklog and the version ledger, with `done` receipts
enriching the draft only), and no separate changelog source file exists.

Every machine draft MUST be deterministic: byte-reproducible from its level-below inputs
(section 6.4), the worklog entries in range, the `[[release]]` rows, and the linked `done`
receipts for a release summary, and the per-release summaries it replaces for a range summary,
under the byte rules of section 10.3 without its generated header (section 10.4); the published
entry stays curated and is never byte-drift-gated. Each release summary receives a human curation
pass before publication (section 7.3), and a range summary or a re-publication receives its own
(sections 6.4 and 7.2). Because the drafter is deterministic, dropping the curation pass later,
making the draft the deliverable and byte-drift-gating it like any deterministic view, is one
recorded maintainer decision and a specification version change, never a rebuild of the drafting
machinery.

Each entry begins with a heading of the form `## <covers>`, optionally followed by parenthesized
dates, where `<covers>` is the machine-parseable token matching a `[[summary]]` row: a version, a
range `a..b`, or `unreleased`. Entries are ordered descending by the highest version covered, with
the optional unreleased section first. The prose beneath the heading is the human-curated summary
of the worklog entries in that range.

### 6.4 The rollup model

The changelog is tiered: worklog entries roll up into per-release summaries, and per-release
summaries roll up into range summaries. Each level summarizes only the level directly below it, so
every rollup is a small, reviewable act: a release summary is drafted from its span's worklog
entries; a range summary is drafted from the per-release summaries it replaces, never from the raw
worklog wholesale.

When a range summary lands, the per-release summaries inside its range are superseded: their
`[[summary]]` rows flip to `superseded` (keeping their digests as publication history) and their
entries leave `CHANGELOG.md`, replaced by the range entry. Nothing beneath changes: the worklog
keeps every entry and the ledger keeps every release row and every superseded summary digest.

### 6.5 What consume-on-rollup does and does not touch

Consumption applies only at the changelog's granularity: a range summary supersedes the finer
summaries within it in the changelog view, exactly as a weekly summary supersedes dailies in a
digest. It never applies to the worklog. The worklog is the durable record; the changelog is a
re-rollable view over it. Deleting or thinning worklog entries during rollup is nonconformant.

## 7. Changelog gates: range coverage and freeze

The changelog is gated on its facts, not its bytes: coverage proves the story spans every release,
and freeze proves a published story changed only through a recorded re-publication.

### 7.1 Range coverage

A deterministic gate confirms, from `version.toml` and `CHANGELOG.md` alone:

- every non-superseded, non-unreleased `[[summary]]` row's `covers` token parses and refers only to
  versions present in the release ledger, with a range denoting a contiguous run in ledger order;
- those rows tile the ledger exactly: every released version falls in exactly one row's coverage,
  with no gap and no overlap;
- every such row has exactly one matching release-or-range entry heading in `CHANGELOG.md`, and
  every release-or-range entry heading matches exactly one such row; the optional `## unreleased`
  heading, when present, matches instead the `covers = "unreleased"` row (the unreleased worklog
  tail), so it is neither an unmatched heading nor a second match against a released row.

The check confirms the start and end versions of each declared range against the ledger; it is
deterministic, and it fails closed on an unreadable or unparseable input.

### 7.2 Freeze and re-publish

Freeze the detail, not the summary. The worklog is the durable record of facts, frozen once its
spans are released; the changelog is free to be re-worded, because editing a summary's prose can
never change the facts, which persist in the worklog.

- A `working` summary (unpublished, including the unreleased section) is edited with no ceremony.
- Publishing a summary computes its freeze digest (the exact bytes of its `CHANGELOG.md` entry,
  from its heading line up to but not including the next entry heading or end of file, with LF line
  endings) and records it on the `[[summary]]` row with `status = "published"`.
- The freeze gate recomputes, for every published summary, both the freeze digest against the
  current `CHANGELOG.md` entry and the underlying `coverage_digest`s of the releases it covers
  against the current worklog. A mismatch on either is a failure.

Editing an already-published entry is therefore never silent: the changed bytes break the recorded
digest, and in a released pack they change the per-file manifest and root digest, so the edit is
structurally a re-publication. The re-publish flow updates the row's digest in the same reviewed
change, and a light gate confirms the edited entry still declares the same `covers` and still rests
on the same underlying worklog entries (the coverage digests unchanged): the facts held, only the
prose moved. A change to the facts themselves is not a re-wording and must land as new worklog
entries under section 6.2.

### 7.3 The curation flow

No unreviewed machine summary ever ships. The flow is fixed: the machine drafts a deterministic
summary from the level below (sections 6.3 and 6.4); a human curates it; publication freezes its
digest; only then does it ship. Each summary receives its own curation pass before it ships: one
per release summary, and one for a range summary or a re-publication (sections 6.4 and 7.2).
Drafting is assistance, not authority; the published words are the curator's.

## 8. Record model

### 8.1 Type taxonomy and placement

| Tier | Type | Namespace |
|---|---|---|
| Baseline | backlog_item | BI |
| Baseline | done | DN |
| Baseline | worklog | WL |
| Baseline | finding | FN |
| Baseline | pending_decision | PD |
| Baseline | autonomous_decision | AD |
| Baseline | block | BL |
| Baseline | handoff | HO |
| Baseline | reference | RF |
| Baseline | contribution | CN |
| Baseline | maintainer_decision | MD |
| Baseline | preference_pattern | PP |
| Governance module | maintainer_action | MA |
| Delivery-assurance module | artifact | AR |
| Delivery-assurance module | gate_run | GR |
| Delivery-assurance module | release | RL |
| Delivery-assurance module | waiver | WV |
| Operational-policy module | mode | MO |
| Operational-policy module | tier_assessment | TA |
| Concurrent-operation module | session_lease | SL |
| Reserved, excluded | transaction | TX |
| Reserved, unassigned | (none) | CL |
| Reserved, unassigned | (none) | LF |

Notes on the roster:

- The word "changelog" is not a record type. It names the curated public deliverable (section 6.3).
  The detailed per-change type is `worklog`. The namespace `CL` is reserved unassigned so it can
  never half-collide with the freed word.
- The namespace `LF` is reserved unassigned in the same way: no record type uses it in either
  series, and unmappable imported text stays verbatim in `unparsed` (section 8.3).
- `transaction` (`TX`) is excluded from the adopter standard with its name and namespace reserved;
  it may enter later as a versioned module only if portable semantics are demonstrated.
- Modules ship default-off; each is enabled by one manifest edit.
- Imported history uses the same enabled types (section 8.2) in a separate
  series, not additional record types.
  Reserved namespaces remain reserved. Imported states describe history and confer no current
  authority (section 8.6).
- `done` is a durable completion receipt linked one-to-one to a backlog item reaching ratified
  `done`; a standalone receipt MUST be imported history with provenance.
- A `finding` records the observation and links its remediation rather than containing it.
- A `block` scopes one or more enumerated records and feeds actionability (section 8.5).
- `contribution` records an artifact, fix, or proposal this project proposes or sends to a peer project,
  with a delivery bundle once sent: the outward counterpart to `reference`, which records what comes in. It carries no
  fleet-specific semantics; those ride a registered `x-<vendor>` extension (section 8.7).
- `maintainer_decision` and `preference_pattern` are baseline types; the governance module carries
  `maintainer_action` alone.
- The delivery-assurance `release` record, where enabled, references a `version.toml` release row
  by version string; the ledger row is the fact, the record is the delivery-assurance envelope
  around it.
- `version.toml`, `counters.toml`, `pipeline.toml`, and `roadmap.toml` are control ledgers, not
  record types (sections 6.1, 8.2, 10.6, and 10.7).
- `lane`, `bundle`, and `milestone` are not record types either: lane identity and operation belong
  to a lanes standard the adopter follows, if any (section 2.1), and bundles and milestones live as
  rows of the pipeline and roadmap control ledgers (sections 10.6 and 10.7).

### 8.2 ID namespaces and counters

Clean record IDs have the form `<NS>-<n>`; imported IDs have the form `imported:<NS>-<n>`,
for example `imported:BI-7`. The complete lexical grammar is
`^(?:imported:)?[A-Z]{2}-[1-9][0-9]*$`, and the namespace MUST additionally name the
record's enabled type in section 8.1. Namespaces map one-to-one to types within each series.
`counters.toml` MUST hold independent monotonic high-water values per series and namespace, `BI`
for clean backlog items and the quoted TOML key `"imported:BI"` for imported backlog items, with
the imported series' rows required, one for each enabled type.
The same rule includes `"imported:WL"`; clean release spans MUST tile only the clean `WL` number
line. The doctor MUST require the imported counter rows, whether `opf init` wrote them at zero or
a re-adoption seeded them from its ancestral snapshot. Uniqueness,
counter high-water, contiguity and no-deletion checks MUST evaluate each series independently;
allocation MUST increment its counter under the store's lock as one atomic claim, so no gap between
choosing and reserving can double-allocate. Counters MUST NOT be reset and IDs
MUST NOT be reused, even when a record is superseded, refuted, or its work reverted. Rotation, index
rewrites, and store relocation MUST NOT touch `counters.toml`. Re-adoption MUST seed both series
from a pinned ancestral snapshot and MUST refuse a missing required namespace; it MUST NOT zero-seed
prior ancestry. Only a genuinely first adoption MAY start its counters at zero. A store manifest
declaring a `spec_version` of 2.0.0 or above whose `[opf].homes` is missing or not the integer 2
is refused as a store (section 9.2), never foreign content: that refusal MUST NOT authorize
adoption over it, and the zero-seed ban above stands (sections 4.5 and 14.1). A store refused
only at the section 9.2 version ceiling keeps its ancestry: it is never foreign content, it MUST
NOT be zero-seeded, and its remedy is the tooling upgrade alone (sections 4.5 and 9.2).

The claim additionally begins with one irrevocable reservation,
`journals/<kind>/allocations/<run-id>.toml` (sections 4.2 and 8.8), which MUST hold exactly
`format = "opf.journal.allocation/v1"`, the run's `kind`, `run_id` and `operation_id`, and a
non-empty `[claims]` table mapping each claimed counter key, a record namespace or, for a run of
the import engine (kind `import` or `ingest`, section 4.2), a quoted imported-series
`"imported:<NS>"` key, to that run's new high-water
value, an integer of at least 1 and at most `2**63 - 1` so every conforming TOML reader can parse
it. A reservation MUST NOT be rewritten, and a reservation request finding an existing entry for
the same run MUST be refused unless the entry reads back byte-identical to the exact payload the
request would publish, in which case the request MUST re-establish the entry's durability before
relying on it; a refusal is not evidence that the run holds its numbers. The next-ID derivation
applies per series key: the next ID under a counter key, the clean `<NS>` and quoted
`"imported:<NS>"` number lines independently, is one more than the maximum of the `counters.toml`
high-water and every reservation's `[claims]` value for that counter key, so recovery MUST treat
a reserved number as issued even where no published record carries it. The doctor MUST likewise
treat a reserved number as issued wherever its checks would otherwise report that number missing,
reading each reservation read-only and for that purpose alone (section 4.2); an unreadable or
malformed reservation MUST yield cannot-evaluate.

### 8.3 The record envelope

Clean records carry the envelope below; the imported envelope follows it. Types add their own
fields on top. Schemas are closed: an unknown key MUST fail validation unless it sits under a
registered vendor extension table.

| Field | Requirement | Meaning |
|---|---|---|
| `id` | required | `<NS>-<n>`, matching the type's namespace |
| `type` | required | the type name; must match the file the record lives in |
| `status` | required | per the status grammar (section 8.4) |
| `proposed_from` | optional | the unqualified state held before the current `/proposed` status, written by the authoring verb (section 8.8); legal only on a `/proposed` status, and only naming a legal predecessor state for the type |
| `title` | required | one line, human-oriented |
| `created_at` | required | RFC 3339 UTC, read from the clock at creation |
| `updated_at` | required | RFC 3339 UTC, read from the clock at the last transition |
| `actor.kind` | required | `maintainer`, `assistant`, `automation`, or `importer` |
| `actor.id` | optional | identity detail within the adopter's own vocabulary |
| `summary` | optional | short prose body |
| `links` | optional | array of `{rel, id}`; `rel` from the closed link vocabulary (section 8.6) |
| `refs` | optional | array of captured references (section 8.6) |
| `x-<vendor>` | optional | registered vendor extension tables only (section 8.7) |

The worklog entry uses a reduced envelope (`id`, `date`, `actor`, `kind`, `summary`, optional
detail, `links`, `refs`); its status is fixed (section 8.5). The worklog records facts, not
proposable decisions, so its entries MUST NOT take the `/proposed` qualifier whatever the actor: an
assistant-authored or automation-authored worklog entry is a conformant recorded fact needing no
ratification (section 8.4).

The imported envelope is closed and deterministic. It MUST carry `id`, `type`, a one-line `title`,
`status` from the type's legal state set without `/proposed`, `actor.kind = "importer"`,
`actor.id` naming the importing assistant, and an `import` provenance table. Imported worklog
rows MUST use this envelope with `type = "worklog"` and `status = "recorded"`, plus their worklog
fields. Standalone imported `done` receipts are legal history. Historical `created_at`,
`updated_at`, `date` and `decided_at` are optional; when present they MUST be valid RFC 3339 UTC
and no later than the writer's import clock instant. Import time MUST NOT stand in for event time.

An imported record MUST give a missingness row in `unrecorded = [{field, reason}]` to each field of
its type's schema that it omits, including optional type fields and each historical timestamp
above that its type's schema carries. The only exempt fields are `proposed_from`, `summary`,
`links`, `refs` and registered `x-<vendor>` tables, which the envelope table above marks optional,
each where the type's own schema does not require it; an imported record never carries
`proposed_from`, since its status never takes `/proposed`. An imported worklog row's `summary` is
therefore never exempt, since the worklog schema requires it (section 6.2). `unrecorded` MUST hold
exactly one row for each omitted field that is not exempt, and no row that repeats a field or
claims a supplied field absent. Supplied
fields MUST retain their declared value types and vocabularies; unknown keys still fail.
`field` MUST name a field in that type's schema. A missingness row whose `field` names an omitted
exempt envelope field, one of the optional envelope fields `proposed_from`, `summary`, `links`,
`refs` and registered `x-<vendor>` tables where the type's own schema does not require it, MUST be
refused. The closed reasons are `not_recorded_in_source`,
`unparsed`, `ambiguous`, `conflicting`, and `not_applicable`. The first means "never recorded
historically in the supplied source", not a claim about all history. The required imported
envelope and provenance fields MUST NOT be waived through missingness. Strict current resolution
bundles and transition obligations do not apply to historical omissions.

The `import` table MUST carry `source` (the canonical store-relative path of the preserved
original, spelled from `.working/`), `source_sha256` (64 lowercase hexadecimal digits),
`run` (the `imp-<YYYYMMDD>T<HHMMSS>Z-<hash16>` run ID), and `imported_at` (RFC 3339 UTC read
from the writer's clock). Optional `span` is an informational byte range in the original.
Optional `import.history` retains verbatim source-precision values that cannot be losslessly
normalized, such as a date-only string; a UTC midnight MUST NOT be fabricated. Optional
`import.unparsed` holds verbatim source text that cannot be mapped. The assistant MUST retain such
text rather than drop it. When present, `import.span` MUST be an array of two integers,
`import.history` an array of tables, and `import.unparsed` an array of strings. Each
`import.history` table MUST hold exactly two keys, `field` (a field named in the type's schema)
and `value` (its verbatim source value as a string). The writer performs
no byte-tiling or leftover accounting: byte-level coverage and semantic fidelity are not
machine-proven. Preserved originals remain the restoration authority.

Imported records and their worklog entries MUST be immutable after publication; corrections MUST be
a fresh import run retaining the old evidence. A conforming imported series can reach doctor VALID:
it MUST NOT enter the module-schema deferral seam. C-IMPORTED-SCHEMA checks
this envelope and missingness; C-IMPORTED-IDS checks the series grammar, counters and no-deletion;
C-IMPORTED-PROVENANCE re-reads each preserved original and verifies `source_sha256`.
C-IMPORTED-IDS owns every imported-series ID defect exclusively, its grammar, counter rows,
uniqueness, contiguity and no-deletion included: such a defect MUST be a C-IMPORTED-IDS finding and
MUST NOT be reported again by C-IMPORTED-SCHEMA or any other check.
C-CONTAINMENT recognizes the imported managed leaves, C-LINKS resolves the union of both series,
and C-IMPORTED-SEGREGATION enforces section 8.6: a firewall breach for which no other check is
named is a C-IMPORTED-SEGREGATION finding. Missing or unreadable evidence MUST fail closed.

### 8.4 The status grammar

```
status    ::= state ( "/" qualifier )?
state     ::= lowercase name from the type's declared state set
qualifier ::= "proposed"
```

- Each type declares a closed state set: one initial state, zero or more working states, and one or
  more terminal states.
- A terminal transition performed by an actor whose `kind` is `assistant` or `automation` MUST land
  with the `/proposed` qualifier (for example `done/proposed`); creating a record directly in a
  terminal factual or ACT state that awaits no ratification, such as an `autonomous_decision` or a
  `reference`, is not such a transition and carries no qualifier. Only a maintainer transition
  MAY remove the qualifier (ratification) or return the record to a working state (rejection, with a
  recorded reason). A `/proposed` status is not terminal: gates and completion claims MUST treat the
  record as unfinished, and views MUST surface it as awaiting ratification. The `/proposed`
  qualifier attaches to any transition an assistant or automation makes that awaits a maintainer's
  ratification: the assistant or automation terminal transitions above (for example `done/proposed`
  or `fixed/proposed`), and the gated non-terminal states, which are proposals rather than grants
  even though they are not terminal. A type declares its gated states: `block` gates `active` (a
  proposed block, `active/proposed`), `contribution` gates `sent` (an assistant-sent contribution,
  `sent/proposed`, awaiting a maintainer's ratification that it was genuinely sent), and
  `preference_pattern` gates `active` (an assistant-distilled pattern, `active/proposed`, awaiting
  ratification). This is one mechanism, not a set of per-type special cases: entering a gated state
  as an assistant or automation MUST take `/proposed`, and only a maintainer MAY ratify it to the
  unqualified state. A recorded factual entry that proposes nothing and awaits no ratification is
  exempt: the worklog, whose entries record facts rather than propose a transition, MUST NOT take
  `/proposed`, so an assistant-authored or automation-authored worklog entry (status `recorded`) is
  a conformant recorded fact rather than an unratified proposal.
- Standing authorization for `contribution` `sent`: `sent` gating is on by default, but an adopter
  MAY declare a standing authorization for a named recipient that deactivates per-send gating for
  that recipient, letting an assistant or automation land the unqualified `sent` grant to it without
  a per-send ratification. A valid declaration for the contribution's declared recipient relieves
  the gating; an absent or malformed declaration MUST fail closed, so gating stays on. The
  declaration is an adopter configuration surface; a store that declares none keeps every `sent`
  gated.
- No resurrection: a record in an unqualified terminal state MUST NOT re-enter a working state. A
  revived concern MUST be a new record linking the old one.
- Supersession is a link, not a state edit: the superseding record MUST link `supersedes`, and where
  the type records it, the superseded record's terminal state MUST reflect it. Where the superseded
  record is immutable, including every imported record, its recorded state MUST stand and the link
  alone records the supersession.
- The worklog is a special case of these rules, with terminality keyed to release rather than to a
  state transition (section 6.2). It declares the single state `recorded`: while an entry sits in
  the unreleased tail its `recorded` status is pre-terminal and mutable-until-release, and once a
  release freezes its span the entry's `recorded` status is terminal and immutable. The
  released-frozen span is therefore the worklog's terminal state that satisfies the
  one-or-more-terminal-states requirement above, while correcting an unreleased entry in place is an
  ordinary pre-terminal edit, not a resurrection of a terminal record.

### 8.5 Transition rules

Baseline types:

| Type | States | Rules |
|---|---|---|
| backlog_item | `open` > `active` > `done` or `dropped`; `open` > `dropped` | Ratified `done` MUST create the one-to-one `done` receipt. Blocked-ness MUST NOT be a stored state; it is derived from active blocks at view time. |
| done | `recorded` | Created terminal, immutable. Links `receipt_of` to its backlog item. |
| worklog | `recorded` | Durable operational record with release-keyed terminality: the unreleased tail is pre-terminal and mutable, a released-frozen span is terminal and immutable (sections 6.2 and 8.4). Takes no `/proposed` qualifier whatever the actor. Mutability governed by section 6.2, not by transition. |
| finding | `open` > `fixed`, `routed`, `refuted`, or `accepted` | Severity MUST be graded at or after the fix decision, never before. |
| pending_decision | `open` > `decided` or `withdrawn` | All-or-none resolution bundle: an open decision MUST carry none of `decision`, `decided_at`, `decided_by`; a decided one MUST carry all. A decided record MAY be superseded by a new decision linking `supersedes`; exactly one current effective resolution MUST exist per chain. |
| autonomous_decision | `recorded` | Immutable ACT record: the classification basis, the action, links. Overturning MUST be a new record (or maintainer decision) linking it. |
| block | `active` > `released` or `expired` | Scopes an enumerated list of record IDs. A block created by an assistant or automation actor is `active/proposed` and is a proposal, not a grant: it MUST NOT count toward blocked-ness or justify a stop until a maintainer ratifies it. |
| handoff | `current` > `superseded` | Posting a new handoff MUST supersede the previous in the same act; at most one `current` handoff MAY exist among clean records authored by non-importer actors (section 8.6). The previous handoff is the one clean `current` handoff authored by a non-importer actor; a first handoff, posted while none stands, supersedes nothing. The superseded handoff lands the status the posting actor's transition takes (section 8.4): unqualified `superseded` for a maintainer, `superseded/proposed` for an assistant or automation. An importer-authored `current` handoff is history: it neither blocks a posting nor is superseded by the posting's own supersession. A handoff MUST NOT return to `current` while another such `current` handoff stands (section 8.8). |
| reference | `recorded` | Immutable captured reference. |
| contribution | `proposed` > `sent` > `acknowledged` or `superseded`; `proposed` > `withdrawn` | Records what this project proposes or sends to a peer, with a delivery bundle `{channel, ref, sent_at, receipt_ref?, receipted_at?}`: `channel`/`ref`/`sent_at` MUST be present once sent, `sent_at` MUST NOT be present before, and the receipt fields MAY appear only at `acknowledged`. `sent` is gated (an assistant lands `sent/proposed`; a maintainer, or a valid standing authorization for the recipient, lands the bare grant). `acknowledged` is the single positive terminal (responded, adopted, reshaped, or declined); the outcome MUST live in `summary`/`x-<vendor>`, never as a state. A re-send MUST be a new record linking `supersedes`; the superseded record records `superseded`. |
| maintainer_decision | `recorded` | Created-terminal, immutable maintainer ruling carrying its `decision` (answer plus rationale). `actor.kind` MUST be `maintainer` or `importer` only (a maintainer ruling with assistant attribution is a contradiction; `importer` covers migrated history). Overturning MUST be a new record linking the old. It MAY `exemplifies` the preference_pattern it instantiates. |
| preference_pattern | `active` > `retired` | A distilled preference pattern carrying `context` and `rationale` (with the envelope `title`). `active` is gated: an assistant-distilled pattern lands `active/proposed` awaiting maintainer ratification to the unqualified `active`. |

Module types, in outline (full schemas ship with the module schemas release): maintainer_action
`open` > `done` or `dropped`; artifact `staged` > `promoted` or
`rejected`; gate_run `recorded` with a three-valued verdict field (`pass`, `fail`,
`cannot_evaluate`), never folded into status; release `planned` > `published` or `abandoned`;
waiver `active` > `expired` or `revoked`, expiry required at creation; mode `active` > `retired`;
tier_assessment `recorded`; session_lease `held` > `released` or `reconciled`.

Actionability: a clean backlog item authored by a non-importer actor is actionable when its
state is `open` or `active` and no clean, unqualified `active` block authored by a non-importer
actor scopes it. Imported and importer-authored records MUST NOT enter this join on either side: an
importer-authored backlog item is history, never actionable work, whatever its recorded state,
and an importer-authored block MUST NOT block (section 8.6).
This is the block join every scheduling view renders; a scheduling view MUST surface an
importer-authored item only as history, never as actionable.

### 8.6 Links and reference capture

`links` relate records to records; `rel` comes from a closed vocabulary: `supersedes`, `resolves`,
`remediates`, `receipt_of`, `corrects`, `follows`, `relates`, `exemplifies`, `derives_from`.
Extending the vocabulary is a specification version change.

- `exemplifies`: the source record instantiates the linked pattern. Its target MUST be a
  `preference_pattern` (PP); the source side is unconstrained. Its primary user is
  `maintainer_decision` (a ruling exemplifies the pattern it instantiates).
- `derives_from`: the source record was derived from the linked record; directional, usable by any
  type. Its primary user is `contribution` (a contribution derives from the internal finding,
  decision, or backlog item that motivated it).

`refs` capture external sources at the moment a claim or artifact is produced: each is
`{kind, locator, note}` with `kind` one of `path` (a repository path, with a line where
applicable), `url`, or `doc` (a document and section). A record whose claims rest on an external
source without a captured reference is unsourced, whatever confidence backs it.

Imported history has an authority firewall, enforced by the writer and doctor and keyed on
provenance rather than on series alone: it covers every record whose `actor.kind` is `importer`.
A clean-series record MUST NOT carry `actor.kind = "importer"`. An
importer-authored record MUST NOT satisfy a current approval, receipt, actionability or
supersession obligation of any record authored by a non-importer actor. The same bar covers
every current obligation, record-level or store-level, including field-borne authority: a
gate_run verdict, a tier_assessment outcome, an artifact's promoted state, a release's published
state and a maintainer_action's done on an importer-authored record describe history and
discharge nothing now. A clean `done` record's `receipt_of` MUST target a clean backlog item, and a clean backlog item
reaching ratified `done` MUST hold a clean receipt authored by a non-importer actor.
An importer-authored decision MUST NOT be treated as the current effective resolution of a clean
`pending_decision` chain; resolving such a chain now MUST take a new clean decision linking back.
Importer-authored blocks MUST NOT grant a current stop, and an importer-authored record MUST NOT
discharge a required supersession. The firewall covers every state-bearing type: an importer-authored record MUST NOT be treated as
the current `handoff`, an active `waiver`, a held `session_lease`, an active `mode`, or a ratified
active `preference_pattern`; a state-bearing status on an importer-authored record describes
history at its source and MUST confer nothing now, and every current-state join, including the
section 8.5 at-most-one-current handoff rule, MUST evaluate only clean records authored by
non-importer actors.
The clean-series writer MUST refuse a transition on an importer-authored record in either series
(section 8.8). Acting on history MUST take a new strict clean record at the present time, with a
link back to the historical record.
C-IMPORTED-SEGREGATION enforces this firewall: a clean-series record that carries
`actor.kind = "importer"`, and a breach of any other part of this firewall, the link rules below
included, for which this specification names no other doctor check, MUST each be a
C-IMPORTED-SEGREGATION finding.

Clean-to-imported links MUST be limited to `relates`, `derives_from`, `follows`, and same-type
`supersedes`; the last records historical continuation without discharging a current supersession
obligation, and the immutable imported target keeps its recorded state, the link alone recording the
supersession (section 8.4). Imported-to-imported links MAY use every declared relation subject to
its type constraints. Imported-to-clean links MUST be refused by both writer and doctor. Links
MUST resolve over the union of both series; a dangling cross-series link MUST be a finding, never
silently omitted. The imported series MUST NOT supply current authority through a link, an
extension, or an adoption approval.

### 8.7 Extensions

Experimental or adopter-specific fields ride only under `x-<vendor>` tables, with each vendor token
registered in the manifest; an unregistered prefix is a validation failure. An extension may add
metadata but MUST NOT override identity, state, transitions, resolution completeness, publication
inclusion, block actionability, counters, lock ordering, or actor attribution.

### 8.8 Authoring operations

`opf record` is the reference tooling's record-authoring verb. It writes the record and worklog
shapes this specification defines, and it adds one optional envelope key of its own: `proposed_from`
(section 8.3), which appears only on `/proposed` records written by `opf record transition` or by a
handoff `create`'s supersession (section 8.5). Its clean-series subcommands use the strict record
model; the `import` write mode uses the separate imported model. Import is not a flag
that relaxes `create`, and the clean-series subcommands MUST refuse `actor.kind = "importer"`:
an importer authors only through `import`. The clean-series subcommands MUST also refuse an
importer-authored record as their operand: acting on imported history is a new clean record
linking back (section 8.6). Its subcommands:

- `create`: one new record of an enabled baseline type, in the type's initial state. An assistant
  or automation author entering a gated initial state lands `/proposed`; a created-terminal factual
  or ACT type (`reference`, `autonomous_decision`, `maintainer_decision`) carries no qualifier
  (section 8.4). `done` receipts and worklog entries are not created this way. A handoff `create`
  lands unqualified `current` whatever the actor and supersedes the previous handoff (section 8.5)
  in the same act: the one `current` handoff authored by a non-importer actor in the active index
  moves to unqualified `superseded` when the actor is a maintainer, or to `superseded/proposed` with
  `proposed_from` set to `current` when the actor is an assistant or automation, and its
  `updated_at` takes the operation's clock value; the new record appends one `supersedes` link to
  it after its requested links; and the worklog entry adds a `supersedes: <ID>` line to its
  `detail` and a `relates` link to the superseded record. With no such handoff standing, a store
  holding only superseded handoffs included, the create supersedes nothing and writes no
  `supersedes` link. An importer-authored `current` handoff is outside this selection (section
  8.6): it neither blocks the posting nor is superseded by the posting's own supersession, and its
  record is left unchanged. Before anything is written, a handoff `create` MUST refuse a requested `supersedes` link that names the
  handoff it supersedes, more than one such `current` handoff, such a `current` handoff found in
  the archive (section 12), an archive input that the doctor's archive walk finds defective, and a
  previous handoff that is not schema-valid or whose `updated_at` is not earlier than the
  operation's clock value.
- `transition`: a status change checked against the type's grammar (section 8.5). An assistant or
  automation author landing a terminal or gated state takes `/proposed`, and the verb MUST record
  the state the record held at that moment in the record's own `proposed_from` field (section 8.3)
  in the same act; only a maintainer ratifies, or rejects with a recorded reason back to the
  recorded pre-proposal state (section 8.4). A rejection MUST restore exactly the recorded
  `proposed_from` state, and leaving the `/proposed` status, by rejection or ratification, MUST
  remove the field. A proposed record that carries no `proposed_from` was proposed outside
  `transition`; that includes a record `create` lands directly at a `/proposed` initial state, so
  the absence establishes no provenance. Such a record cannot be rejected by `transition`, which
  never infers or invents a predecessor; the worklog entry of the proposing transition is
  informational, never evidence. `transition` MUST refuse to act on, or overwrite, a record whose
  current row is not schema-valid, `proposed_from` included, so a schema-detectable forgery must be
  repaired by the operator before `transition` acts; it is never laundered. The field is an ordinary
  record field, so a canonical hand edit of it that keeps the row schema-valid is not detected, the
  same as any other field (the section 5.7 integration-base rule remains the control). A
  pending_decision's `open` > `decided`, landing bare or `/proposed`, MUST write its resolution
  bundle (section 8.5) in the same act: `transition` MUST require the `decision` and `decided_by`
  values there and MUST refuse them on every other transition. `decided_by` MUST be given
  explicitly, never inferred from the actor, because the recorder of an answer is often not its
  decider, and `decided_at` MUST be the operation's clock value. A ratification MUST keep the
  bundle; a rejection of `decided/proposed` MUST remove it together with `proposed_from`, since
  an open decision carries none of it. A transition that lands a pending_decision at unqualified
  `decided`, a maintainer's `open` > `decided` or a maintainer's ratification of
  `decided/proposed`, MAY supersede the current resolution of a chain in the same act: `transition`
  then appends the `supersedes` link (section 8.5) to the record's `links`. Before anything is
  written, the superseded record MUST be another pending_decision at unqualified `decided`,
  schema-valid, and the head of its chain (no pending_decision not authored by an importer already
  links `supersedes` to it), and its own chain MUST NOT lead back to the superseding record. An
  importer-authored pending_decision's `supersedes` link is left out of that test: such a record
  discharges no supersession and confers nothing now (section 8.6). These target checks MUST read
  the same records as the chain rule below, the active index together with every archived record
  (section 12), so a decided, schema-valid chain head rotated to the archive can be superseded, and
  an archived pending_decision that already supersedes the target or leads back to the superseding
  record is counted. `transition` MUST refuse the link on every other transition, a `/proposed`
  landing included, because the doctor counts a `supersedes` link from a proposal too and would
  then find the superseded chain without a current resolution. Every transition that lands a
  pending_decision at unqualified `decided`, with or without a supersession, MUST then apply the
  doctor's chain rule (section 8.5) to the planned index together with every archived record before
  anything is written: the chain the record belongs to afterwards, a connected component over
  `supersedes` links in either direction, MUST have exactly one current effective resolution. So
  `transition` also refuses to decide a record that a pending_decision not at unqualified `decided`
  already supersedes when no other member of its chain is a current resolution, and a supersession
  that passes the checks above but still leaves the chain without a current resolution. The rule
  MUST read the records the doctor reads for that check, the planned index together with every
  archived record (section 12), so a chain member rotated to the archive is judged before anything
  is written. With no archive tree nothing has rotated; an archive input that the doctor's archive
  walk finds missing, unreadable, malformed or otherwise defective MUST refuse the transition with
  nothing written, never be skipped. A contribution's `proposed` > `sent`, landing bare or
  `/proposed`, MUST write its delivery bundle (section 8.5) in the same act: `transition` MUST
  require the `channel` and `ref` values there and MUST refuse them on every other transition, and
  `sent_at` MUST be the operation's clock value. The send MUST refuse a record that already carries
  `delivery`, so a rejection of `sent/proposed` removes the bundle whole and restores the record as it
  was before the proposal; a ratification MUST keep the bundle. A record that carries a planned
  delivery at `proposed` (section 8.5) therefore cannot be sent by `transition`; the way out is to
  withdraw it and create a new contribution, whose send writes the bundle. `transition` does not read
  a standing authorization (section 8.4): an assistant or automation send lands `sent/proposed` even
  where the authorization would permit a bare `sent`, for a maintainer to ratify. A recipient
  receipt reference MAY be given only on `sent` > `acknowledged`, landing bare or `/proposed`:
  `transition` then adds `receipt_ref` and `receipted_at`, the operation's clock value, to
  `delivery`, and MUST refuse the value on every other transition. A rejection of
  `acknowledged/proposed` back to `sent` MUST remove those two keys. A transition that lands a
  handoff at `current`, the maintainer rejection of `superseded/proposed`, MUST refuse with nothing
  written while another `current` handoff authored by a non-importer actor stands in the active
  index or the archive, since a rejection restores only the one named record; the maintainer MAY
  instead ratify the proposal to `superseded`. An importer-authored `current` handoff does not
  block that rejection (section 8.6). A backlog item MUST reach
  unqualified `done` only through `done-with-receipt`.
- `done-with-receipt`: maintainer-only. It moves a backlog item to unqualified `done`, from
  `active` or by ratifying `done/proposed`, and in the same act creates its one-to-one `done`
  receipt linked `receipt_of` (section 8.5). An assistant reaching `done` uses `transition` and
  lands `done/proposed`; no receipt exists until a maintainer ratifies.
- `receipt-repair`: maintainer-only, with a recorded reason. It is the reviewed repair of a backlog
  item that stands at unqualified `done` without a clean receipt authored by a non-importer actor
  (sections 8.5 and 8.6), such as an item a reviewed hand edit put at `done`: in one act it creates
  the missing `done` receipt linked `receipt_of`, and it changes no status and no other record. It
  MUST refuse, with nothing written, unless the item is at unqualified `done` and its current row is
  exactly the row the prior commit holds, and it MUST refuse an item that already holds such a
  receipt in the active index or the archive (section 12). Its new ID MUST be claimed through the
  irrevocable reservation of section 8.2. A repaired receipt is linked one-to-one to its item, so it
  is not a standalone receipt (section 8.1).
- `worklog-append`: one entry appended to the unreleased tail of `worklog.toml`, status `recorded`,
  never `/proposed` whatever the actor (sections 6.2 and 8.4). An entry that would fall inside a
  released span MUST be refused.
- `carried`: the reference profile's carried-finding subcommand, offered only by a tool that
  supports `[profiles.aiqt]` at version 1.1.0 or later and only on a store that declares it there.
  It writes the `x-aiqt.carried` table of one finding: it creates the table, replaces its `area`,
  or appends exactly one disposition, and changes no status (section 9.3).

- `import --batch FILE [--root DIR]`: the primary import surface (the import write mode; there
  is no separate `--import` flag). A single-record import is a one-row batch. The canonical TOML batch,
  `opf.record.import-batch/v1`, declares one source path, record rows, worklog rows, historical
  fields, missingness, verbatim unparsed text and batch-local link keys. The writer MUST resolve
  local keys to claimed imported IDs and MUST recompute source size and SHA-256 from preserved
  bytes, never trusting caller-supplied measurements. One invocation covers one source in one
  journaled transaction, followed by one render and one full doctor; a frozen migrate, move or
  retire source (section 14.2) MUST NOT be written, and doctor grades it under the section 11
  bounded treatment, never as an obstacle to VALID.

`create`, `transition`, `done-with-receipt`, `receipt-repair`, and `carried` MUST each append their
own worklog entry, one entry per change (section 6.2), in the same journaled transaction as the
change. Its `detail` MUST open with a lifecycle line naming the record and its status change
(`opf-record create <ID> <status>`, or `opf-record transition <ID> <from> -> <to>`), or, for
`carried`, the act of section 9.3 (`opf-record carried <ID> <act>[ <outcome>]`); a rejection's
entry MUST also
record its reason. `worklog-append` MUST refuse a `detail` that opens with that lifecycle grammar.

Every subcommand runs one operation sequence, and an implementation of the verb MUST preserve its
guarantees:

1. Resolve the store, then any interrupted authoring transaction MUST be reconciled first, under
   the section 9.2 refuse-before-write order, which applies the section 9.2 validation refusals
   before that reconciliation writes.
   Reconciliation writes the store, so it MUST run only under the single-writer lease that
   publication uses: when a live or possibly-live holder holds that lease, reconciliation MUST
   refuse before any recovery write and MUST NOT seize the lease, and reconciliation MAY itself
   release a leftover lease from a confirmed-dead run of the same verb, since that release is the
   reconciliation on resume, and section 5.7 requires a leftover lease from a dead run to be
   released only through that reconciliation.
   When any other lease is present, a confirmed-dead leftover of another verb included,
   reconciliation MUST refuse before any recovery write and MUST NOT release that lease.
   An operand changed since the interruption, to bytes that are neither its journaled prestate nor its
   planned poststate nor a write of either torn by the interruption, MUST be reported and refused,
   never overwritten. A reconciled interruption MUST refuse the new operation, so the operator
   inspects it before anything new is written.
2. Precondition: re-emitting the unchanged parsed model of every file the operation rewrites
   reproduces its on-disk bytes exactly (the section 9.2 rule). A file carrying comments or
   non-canonical serialization MUST be refused and left untouched. The check proves serialization
   only: a hand edit or hand merge that leaves canonical bytes is not detectable by it, and the
   integration-base merge policy of section 5.7 remains a separate requirement.
3. Claim each new ID as one atomic act (section 8.2): the claim is an irrevocable reservation in
   the journal home, made before the reversible publication (section 4.2).
4. Postcondition: the model diff of every rewritten file equals exactly the operation's allowed
   delta (the new rows appended, the counters advanced by exactly the claim, and for a transition
   one status and `updated_at` change plus the `proposed_from` write or removal and, for a
   pending_decision, the resolution bundle write or removal and the `supersedes` link append),
   value for value
   and type for type (a boolean or float is never equal to an integer), before anything is
   written. The expected
   delta MUST be derived from the request, the prior bytes of each rewritten file, the claimed IDs,
   the clock value, and the schema rules, never from the planned rows themselves. For a
   handoff `create` that supersedes (section 8.5), the allowed delta also holds the superseded
   handoff's `status` and `updated_at` change and, for an assistant or automation post, its
   `proposed_from` write; it holds no change to any other existing record. For `carried`, the
   allowed delta is the one section 9.3 defines.
5. The in-repo store contract (section 5.7): the planned destinations MUST be clean, including
   ignored files, and the single-writer lease MUST be held across publication, render, and the final
   doctor.
6. Every rewritten file MUST be published in one crash-durable journaled transaction, so an
   interruption leaves the store exactly at its prestate or exactly at its poststate once
   reconciled. That journal is `.working/journals/record/journal`.
7. The declared views are rendered.
   Then a full doctor MUST report VALID; a failure leaves the change for review with recovery
   advice scoped to the planned paths. One exception applies to a status change: doctor compares
   it with the prior committed snapshot, and doctor's history comparison sees only the prior
   snapshot's type and status, which identify neither the transitioning actor nor the
   pre-proposal state; doctor validates `proposed_from` but does not use it as rejection
   evidence, so doctor MAY grade that change cannot-evaluate until the change is committed. The
   verb's render and final doctor MUST accept that cannot-evaluate only for exactly the record
   and the from and to statuses it has just written, never a finding and never any other
   cannot-evaluate, and the verb MUST report it as pending until commit. `opf doctor` itself is
   unchanged and still reports it until then.
8. The lease MUST be released, and only then are the claimed IDs and touched files reported. The
   change MUST be left uncommitted in the working tree: the verb MUST NOT stage or commit it.

The verb MUST exit 0 when the change is recorded and the store is doctor-VALID (or carries only
the pending cannot-evaluate of item 7), and 2 on every refusal or cannot-evaluate.

Import MUST preserve that operation sequence, including the one allocation seam, independent model
delta check, cleanliness gate, lease and reconcile-first recovery. Its atomic operands are the
imported counter rows first, the touched `<type>.imported.index.toml` and
`worklog.imported.toml` files, and the evidence bundle: the exact original at
`.working/imported/import/<run-id>/originals/<source-path>` and `inventory.toml` in the retained
`opf.evidence.inventory/v1` format (section 4.2). The journal is
`.working/journals/record/journal`. It MUST NOT
rewrite clean records or clean counters.

Import MUST refuse with exit 2 on a non-importer actor, absent or invalid provenance, a
clean-series record operand, an imported-to-clean link, a historical timestamp later than the
run clock, an unknown missingness reason, or a type not enabled and supported by the writer.
It MUST also refuse without an adoption receipt, outside that plan's approved migrate-source
scope, or when any section 14.1 bound item, the source bytes against the plan digest (archived
under section 14.2 or frozen live), the tool release identity, or the prompt-pack version and
digest included, no longer matches the approved plan. Bound-item drift, in this session or a later one after a tool upgrade, MUST
refuse into a fresh plan with its own single approval; import MUST NOT reinterpret the old
approval.

Replay identity is `(source_sha256, batch content digest)`. A completed identical replay
MUST re-read and verify the published records and evidence, then succeed as a no-op reporting
the existing IDs. A partial overlap, including a differing batch against the same source within
the run, MUST refuse, naming the overlap and directing to journal recovery. Each source admits
at most one completed batch per correction chain: a differing batch against a source whose
batch already completed MUST refuse and name the completed run, unless the new batch declares
that run as the completed run it corrects. Such a corrected import is a fresh run; its records
MUST link `supersedes` or `corrects` to the imported records they replace, the previous run's
immutable evidence MUST be preserved, and source completion (section 14.1) evaluates the
correcting run. Before the
source's recorded retirement, the source-bytes plan check of the refusal list MUST bind a
correcting run as it binds any other; after that retirement, the preserved original under
`.working/imported/import/<run-id>/originals/` is the source of record, the digest bound is its
recorded `source_sha256`, and the source-bytes check does not apply to the retired path. Retry
MUST NOT allocate duplicate IDs.

## 9. The manifest

`.working/toml/manifest.toml` is the store's control document and discovery marker.

`.working/toml/init.toml` is the bootstrap provenance a coupled `opf init` records (its format is
frozen in OPF-INIT-D2B). It is a managed leaf when present and is never required, so a store
without it stays valid.

The optional `[opf].worklog` key selects the active worklog storage generation,
independently of `[opf].homes` and `layout`. Omission and integer `1` select the
legacy `worklog.toml` ledger. This build supports only generation 1: integer `2`
is reserved and refused before source selection; booleans, other types, and
other integers are invalid. Archive buckets retain their legacy `worklog.toml`
shape. Recognizing this key does not activate generation-2 writers or migration.

Illustrative shape (the schema release that follows this specification is normative):

```toml
# .working/toml/manifest.toml
# OPFiles (AIQT Development Operational Standard) store manifest and discovery marker.

[opf]
standard = "opf"               # discovery token; exact value required
spec_version = "2.0.0"         # OPFiles base spec version this store conforms to
homes = 2                      # homes generation; required, and 2 is the only value (section 9.2)
layout = "inline"              # storage layout: "inline" or "per-record" (was layout_profile)
posture = "required"           # "off", "warn", or "required" (section 11)
import_status = "none"         # "none", "partial", or "complete"

[store]
sync_target = ""               # the store's dedicated sync target (section 5.7); empty under the
                               # in-repo default, where the store rides the product repository

[modules]                      # base-level optional capability modules (generic, not AIQT-specific)
governance = true              # the [profiles.aiqt] profile below requires these three enabled
delivery_assurance = false
operational_policy = true      # (required by [profiles.aiqt].required_modules)
concurrent_operation = true    # (required by [profiles.aiqt].required_modules)

# --- Profiles: additive requirement bundles, namespaced, ignored by base-only tooling ---

[profiles.aiqt]
version = "1.1.0"                    # AIQT profile version, independent of spec_version above
base_compat = ">=2.0.0 <3.0.0"       # base spec_versions this profile applies to
posture_floor = "required"           # effective posture = strictest(base.posture, this)
required_modules = ["governance", "operational_policy", "concurrent_operation"]
verification_floor = "triple-family" # AIQT reference-suite policy; base tools ignore this
extension_namespace = "x-aiqt"       # record-level namespace this profile owns (section 8.7)

[profiles.aiqt.components]           # optional carried-finding component map (section 9.3)
store = ["src/store/**"]
render = ["src/render/**", "templates/**"]

# A second adopter could later add, ignored by everyone who does not support it:
# [profiles.acme]
# version = "0.1.0"
# base_compat = ">=2.0.0 <3.0.0"

[types.backlog_item]
namespace = "BI"

# ... one [types.<name>] table per enabled type; namespaces per section 8.1

[providers.local-directory]
handler = "builtin"
roles = ["create", "sync"]

[providers.generic-git-remote]
handler = "builtin"
roles = ["sync"]

# ... optional host providers, for example:
# [providers.github]
# handler = "plugin"
# roles = ["create", "auth"]

[unmanaged]
paths = []                     # pre-existing files kept in place, enumerated (section 14.2)

[views."BACKLOG.md"]
kind = "composed"
sources = ["backlog_item", "block"]
target = ".working/BACKLOG.md"

[views."WORKLOG.md"]
kind = "deterministic"
sources = ["worklog"]
target = ".working/WORKLOG.md"

[views."CARRIED.md"]           # optional area view; reads x-aiqt fields (sections 10.2 and 10.8)
kind = "composed"
sources = ["finding", "backlog_item"]
target = ".working/CARRIED.md"
profile = "aiqt"               # the profile the view depends on (section 10.2)

[views."DECISIONS.toml"]       # a machine projection (section 10.5): deterministic, byte-drift-gated
kind = "projection"
sources = ["pending_decision", "autonomous_decision", "maintainer_decision", "preference_pattern"]
target = ".working/DECISIONS.toml"

[views."VERSION"]
kind = "deterministic"
sources = ["version"]
target = "VERSION"

[views."PIPELINE.md"]
kind = "deterministic"
sources = ["pipeline", "backlog_item", "block"]
target = ".working/PIPELINE.md"

[views."ROADMAP.md"]
kind = "deterministic"
sources = ["roadmap"]
target = "ROADMAP.md"
preamble = "optional"          # the one curated-preamble seam (section 10.7)

[deliverables."CHANGELOG.md"]
kind = "curated"
target = "CHANGELOG.md"

[archive]
period = "year"

[vendors]
registered = ["x-aiqt"]        # record-level extension namespaces; the aiqt profile owns x-aiqt,
                               # registered here so base-only record validation accepts x-aiqt fields
```

View and deliverable targets under `.working/` are relative to the store repository root; the
public targets (`VERSION`, `ROADMAP.md`, `CHANGELOG.md`) are relative to the product repository
root (section 5.8). The view key `preamble` is permitted only on `[views."ROADMAP.md"]`, and only
with the value `"optional"`; the key on any other view, or with any other value, MUST fail
manifest validation (section 10.7). The view key `profile` names the profile a view depends on
(section 10.2): it is permitted only on a view of kind `composed`, its value MUST be the name of a
`[profiles.<name>]` table the manifest declares, and the key on any other view, or with any other
value, MUST fail manifest validation. A composed view whose composition reads an extension field
MUST carry the key.

Storage layout:

The `layout` field selects the storage layout only:

- **`inline`** (default): records live inline in `<type>.index.toml`; the index and the store
  coincide. One global store lock MUST serialize writers. This is the ordinary single-writer case: a
  consumer reads one small file with one parse.
- **`per-record`** (with the concurrent-operation module): `<type>.index.toml` becomes a registry
  of `{id, state, path, digest}` rows, records live one per file under `<type>/`, and any
  multi-record operation MUST take `(namespace, id)` locks in ascending order. Concurrent writers
  pay the file-count cost only when they have the problem it solves.

Readers always enter at `<type>.index.toml` in either layout. The ledgers are exempt from the
per-record layout: `version.toml`, `worklog.toml`, `pipeline.toml`, and `roadmap.toml` MUST always
be single files. `version.toml` and `worklog.toml` are written under the store lock (allocation of
WL IDs still goes through `counters.toml` atomically); `pipeline.toml` and `roadmap.toml` are
edited through ordinary review (sections 10.6 and 10.7), and an assistant or automation that edits a
planning ledger holds the section 5.7 single-writer lease instead of the store lock (section 10.6).

### 9.1 Base standard and profiles

The manifest declares one **base** standard and zero or more **profiles**.

The base is the `[opf]` table: `standard = "opf"` (the discovery token, exact value
required), `spec_version` (the base SemVer this store conforms to), and the base storage and posture
fields. Base-only tooling reads the base, validates it, and operates on it alone.

A profile is a `[profiles.<name>]` sub-table carrying its own `version` (independent SemVer) and a
`base_compat` range, plus profile-namespaced requirement fields. **A profile may only add
requirements; it may never weaken, remove, or override a base requirement.** A profile table holds
only profile-namespaced keys and cannot write a base field, so a weakening override is impossible by
construction; where a profile field combines with a base setting it combines toward the stricter
value, and a profile value that would loosen a base setting is a profile validation failure,
surfaced, never applied.

Base and profile versions evolve independently. A tool that does not recognize a declared profile,
or does not support its major version, **ignores it for enforcement** and records it as
present-but-unevaluated; it never fails base validation over an unknown profile. A tool that does
support a profile enforces the profile's additional requirements as extra gates and **fails closed**
on an unreadable, unparseable, or base-incompatible instance of that profile. Fail-safe governs a
profile outside a tool's declared coverage; fail-closed governs a profile inside it (section 17).

A profile's record-level additions ride registered `x-<vendor>` extension tables (section 8.7),
registered in `[vendors]` so base record validation accepts them as opaque; a profile's store-wide
requirements live in `[profiles.<name>]`, invisible to base validation. A profile-aware tool checks
that each supported profile's `extension_namespace` is registered in `[vendors]`; an unregistered
profile namespace is a profile-setup failure surfaced to the adopter, because base-only record
validation would otherwise reject that profile's records under the section 8.7 unregistered-prefix
rule (fail-closed, never a weakening). The shipped profile is
`[profiles.aiqt]`, dogfooded by the reference suite; it declares a posture floor, required modules,
the reference verification floor, and its `x-aiqt` extension namespace, and from its version
1.1.0 it carries the carried-finding rules of section 9.3. The `[profiles.<name>]`
namespace and these contract rules are reserved and documented; the profile-authoring interface is
not yet a committed public contract for third-party authors.

### 9.2 Store schema upgrades

Base spec 2.0.0 is the baseline, and it declares the homes generation with the required integer
`[opf].homes = 2` (section 4.2). A store that omits `[opf].homes`, or declares any value other
than the integer `2`, MUST be refused. This specification defines no earlier base version, so this
section defines no upgrade into 2.0.0; its rules bind each later base-schema version bump.
Every later base-schema version bump MUST keep every manifest discoverable through the exact base
discovery token `opf` (section 4.5). No later base version exists, so the reference tooling defines
no store upgrade (section 16.1).

A base-schema version bump MUST ship a tested, in-place store-schema upgrade (`opf upgrade`) in at
least one published implementation (section 16.1), the reference tooling, so that a store below
the new version has an upgrade path; the path holds only within this section's preconditions and
refusals and that implementation's disclosed residuals. Every requirement of this section on an
upgrade, its deltas, preconditions, refusals, and remedies binds every implementation that
provides `opf upgrade`. Every implementation MUST apply the version ceiling's refusal at the end
of this section. The
upgrade MUST be idempotent. An upgrade MUST NOT create provenance, any approval (an adoption
approval, a ratification or a receipt included), or history. A schema-level bump MUST be additive,
using atomic
replacement of existing files, create-only writes for new index files, and regeneration of declared
views through exclusively created temporary files followed by atomic rename. These writes are
sequential, with recovery scope held in memory, not a durable transaction journal. The upgrade MUST
run under the store consistency contract and the single-writer lease (section 5.7).
It MUST fail closed on an unresolvable store, a declared `spec_version` ABOVE the tooling,
a divergence, a held lease, or any populated state that contradicts its preconditions; it MUST NOT
lower the fail-closed floor. Before any write it MUST enforce two fail-closed preconditions: it
claims the single-writer lease (section 5.7) and holds it across the whole mutation, and it verifies
the working tree is clean, including ignored files, over the planned schema and render destinations
(store and product roots) and the index collision candidates, so the committed HEAD is a verified
restore path for that scope; a held lease or a dirty store refuses, and a dirty store is asked to
commit its own changes, never restored by the tool. After applying the schema delta, it MUST regenerate
the declared views and MUST require a full doctor VALID before offering the uncommitted change for
the adopter's own branch-and-merge. It MUST NOT stage or commit the change. The upgrade
MUST NOT write the adoption archive and MUST NOT overwrite, relocate or remove a plan-enumerated
frozen source (section 14.2); a frozen source sits outside the planned schema and render
destinations, so the clean-tree precondition does not read it, and the required doctor VALID grades
it under the section 11 bounded treatment. An upgrade delta or manifest change that would declare a
new view or managed store path at a registered `[unmanaged]` path or at a plan-enumerated frozen
source MUST refuse, naming the collision; the remedy is the adopter's own fresh plan
re-dispositioning that file (section 14.2).

The manifest and counters rewrite MUST be a model regeneration through the canonical new-document
emitter, never a textual round-trip edit, bounded by two guards: a precondition that re-emitting the
UNCHANGED parsed model reproduces the on-disk bytes exactly (proving the file is canonical and
comment-free, so nothing can be lost), failing closed otherwise; and a postcondition that the model
diff equals exactly the allowed delta, failing closed otherwise. Repeated upgrade is a verified
no-op only after full doctor VALID.

Declaring a spec_version above the tooling's supported version MUST be refused at validation
as a fail-closed INVALID finding naming the tooling-upgrade remedy, never treated as supported.
A store refused only at that ceiling is a store at a later version, never foreign content: that
refusal MUST NOT authorize adoption over it, and the section 8.2 zero-seed ban stands
(sections 4.5, 8.2, and 14.1).
A `spec_version` below 2.0.0 names no version this specification defines, and validation MUST
refuse it as a fail-closed INVALID finding.
A manifest so refused, whatever its `[opf].homes`, is refused as a store: that refusal MUST NOT be
read as authorizing initialization or adoption (sections 4.5 and 14.1).
A tree under a manifest so refused MUST NOT be adopted until the operator has moved that manifest
aside by hand, a step no OPF command performs; its files are then ordinary foreign content for a
section 14 first adoption (section 14.1).
Files remaining under the reserved store control children (section 14.2) are the one exception:
an adoption option MUST NOT select them, so the operator moves them aside by hand on the same
terms, a step no OPF command performs, before that first adoption can complete.
A manifest declaring a `spec_version` of 2.0.0 or above whose `[opf].homes` is missing or not the
integer 2 is refused as a store by the `[opf].homes` refusal above, never foreign content: that
refusal MUST NOT be read as authorizing initialization or adoption (sections 4.5, 8.2, and 14.1).
Before any command writes to a store, the claim, release, or reconciliation of the single-writer
lease (section 5.7), a fast-forward by `opf sync`, and the recovery of sections 8.8, 14.1, and 14.2
included, every implementation MUST apply these validation refusals and the `[opf].homes`
refusal above to the store manifest that discovery finds there, so a store they refuse stays
byte-identical.
For `opf sync`, these refusals and the `[opf].homes` refusal MUST also be applied to the store
manifest the fetched state carries, before a fast-forward lands it, so a fast-forward never brings
a refused manifest into the store.

### 9.3 The reference profile's carried-finding rules

The shipped profile `[profiles.aiqt]` carries the rules of this section from its version 1.1.0;
they map a carried low finding (section 10.6) to the later changes that address it. They bind only
a store that declares that profile at version 1.1.0 or later, and only for a tool that supports
that version (section 9.1). A tool that supports the profile only below version 1.1.0 records these
rules as unevaluated for such a store, never as passed (section 16). Base validation reads the
extension table below as an opaque registered extension (sections 8.7 and 9.1), so no store gains
a base requirement from this section. The record-level data rides the profile's registered
extension namespace while the design settles; a later version of this specification can move the
same shape into a default-off module or an optional base field, and this version makes neither
move.

A finding marks itself as a carried low finding by carrying the table `x-aiqt.carried`. The table
records the adopter's judgement that the finding is a carried low finding; the base still defines
no severity scale (section 10.6). The table:

- MUST NOT appear except on a `finding` whose status is unqualified `routed`, and MUST hold no key
  this section does not name. An assistant or automation that routes a finding lands
  `routed/proposed` (section 8.4), so the table waits for the maintainer's ratification: a
  rejection returns the finding to `open` (section 8.8), where it could not shed a table whose
  dispositions are append-only.
- `area`: an optional array of area entries, non-empty and without duplicates where present. An
  area entry is either a component reference, the string `component:` followed by the name of a
  component the component map declares, or a path glob in the dialect below. A finding without
  `area` has no area: it never matches a changed path, and the report lists it apart
  (section 10.8).
- `dispositions`: an optional array of disposition tables, in the order recorded. Each disposition
  MUST hold exactly `change`, `outcome`, and `reason`:
  - `change`: a non-empty single-line string that locates the change in the host's own terms, for
    example its URL. A change is a host object, not a store record, so no link and no doctor check
    resolves it.
  - `outcome`: one of the closed set `fixed` (the change fixed the finding) and `deferred` (the
    change touched the finding's area and left the finding unfixed).
  - `reason`: a non-empty single-line string that says why the change fixed the finding or left
    it unfixed.

Dispositions are append-only: an entry MUST NOT be removed or rewritten, and a correction is a new
entry. For each distinct `change` value, the last disposition in array order is the effective one,
so a correcting entry for the same `change` replaces the effect of every earlier one; the checks of
this section read effective dispositions only.

`opf record carried` (section 8.8) is the sanctioned writer of the table and its dispositions. Its
operand is one clean `finding` in the active store authored by a non-importer actor whose status
is unqualified `routed`; any other operand MUST be refused with nothing written. Any non-importer
actor MAY run it,
because writing the table is not a transition and lands no `/proposed` status (section 8.4); the
maintainer's ratification of the remediating backlog item's `done` stays the control (below).
Each run performs exactly one act:

- `table`: creates `x-aiqt.carried` on a finding that does not carry it, with the `area` entries
  given, or with no `area` where none is given, and with no `dispositions`.
- `area`: sets or replaces the `area` of a finding that carries the table, or removes it where no
  entry is given. `area` is a current judgement, not history, so it is not append-only.
- `disposition`: appends exactly one disposition, from the `change`, `outcome`, and `reason` given,
  after the last existing one on a finding that carries the table, creating the `dispositions`
  array where it is absent.

The run MUST refuse, with nothing written, a request that would break a rule of this section, such
as a `table` act on a finding that already carries the table, an `area` or `disposition` act on one
that does not, a component reference to an undeclared component, a glob outside the dialect
below, or a disposition that would leave a backlog item in unqualified `done` that remediates the
finding without an effective `fixed` disposition (C-CARRIED-CLOSURE, below). Its allowed delta
(section 8.8, item 4) is exactly: in the finding, that one table creation, `area` change, or
disposition append, with no change to `status`, `updated_at`, or any other field; in the
per-record layout, the finding's index row with its `digest` recomputed for the rewritten
record file (sections 9 and 13) and no other change to that row; and the run's own worklog entry
with the counter advanced by exactly its claim. That worklog entry opens its `detail` with
`opf-record carried <ID> table`, `opf-record carried <ID> area`, or
`opf-record carried <ID> disposition <outcome>`, links the finding with `relates`, and, for a
disposition, carries the change as a `refs` entry whose `locator` is the `change` value and whose
`note` is the outcome, of kind `url` where that value contains `://` (the URL test of section 5.6)
and of kind `doc` otherwise (sections 6.2 and 8.6); the report reads such entries to age the
finding (section 10.8). The run follows the whole section 8.8 operation sequence: reconciliation
first, the byte-reproduction precondition, the ID claim, the independent delta check, the
section 5.7 clean-state check and single-writer lease held across publication, render, and the
final doctor, one journaled transaction in `.working/journals/record/journal`, the render of the
declared views, a final doctor that MUST report VALID, and the lease released before the change is
reported and left uncommitted. `transition` neither writes nor removes the table, and no other
operation's allowed delta includes it.

A store kept by hand (section 1) writes the same delta through ordinary review: the written record,
and in the per-record layout its index row with its recomputed `digest`, is re-emitted in the
canonical serialization of section 5.7 before commit, together with a worklog entry of the same
shape, and the section 5.7 merge-conflict rule applies to it as to any store path. An assistant or
automation that writes the table by hand MUST hold the section 5.7 single-writer lease while it
writes. Where the enforcement pack protects the record series (section 14.1), `opf record carried`
is the only write path, and a tool that enforces C-CARRIED-CLOSURE (below) MUST offer
`opf record carried`, because enforcement MUST NOT ship before the writer can perform every
operation it forces (section 14.1). Writing the table or a disposition by any path is not a
transition, so it MUST NOT change the record's `status` or `updated_at` (section 8.3). Imported
records are immutable (section 8.3), so the table is never written onto one.

`[profiles.aiqt.components]` is the optional component map: a manifest table mapping each
component name to a non-empty array of path globs, without duplicates, in the dialect below. A
component name MUST match `^[a-z0-9]+(-[a-z0-9]+)*$`. A component reference expands to its
component's globs, so a rename or move changes one map line rather than every record that names
the component. The map is a profile store-wide field (section 9.1), invisible to base validation.

A path glob is relative to the product repository root and is written in this closed dialect:

- It is one or more segments separated by `/`, with no leading or trailing `/`, no empty segment,
  no segment that is `.` or `..`, no backslash, no C0 control character or DEL, and no leading
  `component:`.
- `**` as a whole segment matches zero or more whole segments; `**` inside a longer segment is
  outside the dialect.
- `*` inside a segment matches zero or more characters other than `/`, a leading `.` included.
- `?` matches exactly one character other than `/`.
- Every other character matches itself, compared by Unicode code point and case-sensitively; the
  dialect has no escapes, character classes, or alternation.
- A glob matches a path only when it matches the whole path.

A carried finding is a clean `finding` authored by a non-importer actor that carries
`x-aiqt.carried`. A remediating backlog item of it is a clean backlog item authored by a
non-importer actor that a `remediates` link connects to the finding, whichever of the two records
carries the link. A carried finding is:

- **open** where at least one of its remediating backlog items is not in an unqualified terminal
  state;
- **closed** where none is, and at least one stands in unqualified `done`;
- **unremediated** where it has no remediating backlog item, or every one stands in unqualified
  `dropped`.

A carried finding closes through its remediating backlog item, never through a finding transition.
The finding stays `routed`, because section 8.5 gives `routed` no outgoing transition and a
finding links its remediation rather than containing it (section 8.1). After the change that a
`fixed` disposition names has merged, an assistant or automation moves the remediating backlog item
to `done/proposed` (section 8.4); the base already permits that move, and this profile adds no
precondition to it. Only a maintainer ratifies it to `done`, and ratified `done` creates its
receipt (section 8.5). Where the effective posture (sections 9.1 and 11) is `required`, a
tool that supports the profile MUST refuse, with nothing written, a `done-with-receipt` that would
leave the item without an effective `fixed` disposition on each carried finding it remediates, or,
for a superseded carried finding, on a successor (C-CARRIED-CLOSURE, below).

A store that declares the profile MUST NOT rotate a carried finding to the archive (section 12)
unless the finding is closed. An open or unremediated carried finding can still take a
disposition, and rotation preserves an archived record byte for byte (section 13), so an archived
finding could never take one.

A tool that ignores the profile can still rotate a carried finding that is not closed (section 17).
The remedy is a successor: a new carried finding, authored through `opf record` (section 8.8),
that links `supersedes` to the archived one (section 8.6) and carries on its tracking, its own
`remediates` links included. An archived carried finding that a carried finding links `supersedes`
to is a superseded carried finding, whether or not it is closed. A superseded carried
finding is never listed by the report or the view (section 10.8), its successor standing in for it,
and an effective `fixed` disposition on its successor, or on a later successor along the
`supersedes` chain, counts as one on the superseded finding for C-CARRIED-CLOSURE.

A tool that supports the profile runs two checks as extra gates of the profile (sections 9.1 and
11). Each resolves records across the active store and the archive alike (section 12), and each
MUST fail closed on an unreadable or unparseable input:

- **C-CARRIED-SHAPE** reads every clean record authored by a non-importer actor, active and
  archived, and the component map. An `x-aiqt.carried` table on a record that is not a `finding` in
  unqualified `routed`, a key this section does not name, an `area` or `dispositions` value that
  breaks the rules above, a component reference that names no declared component, a malformed
  component map, and a glob outside the dialect MUST each be a finding. An `x-aiqt.carried` table on
  an importer-authored record, in either series, is imported history (section 8.6): it marks no
  carried finding, and no check of this section reads it.
- **C-CARRIED-CLOSURE** evaluates clean records authored by non-importer actors only (section 8.6).
  A backlog item in unqualified `done` that remediates a carried finding MUST be matched by at
  least one effective disposition with outcome `fixed` on that finding, or, for a superseded carried
  finding, on a successor (above); each carried finding it remediates without one MUST be a finding.
  A backlog item in `done/proposed` in the same position MUST be reported as `carried_unreferenced`
  detail rather than failed, so the gap shows before ratification. A remediating backlog item that
  reaches `dropped` is outside this check. A carried finding in the archive that is not closed MUST
  be a finding, because it can no longer take a disposition, unless it is a superseded carried
  finding, which MUST be reported as `carried_archived_open` detail rather than failed. The check
  reads that the disposition exists, never that the change merged or fixed the finding
  (section 17).

**Choices for the maintainer to confirm.** The maintainer's recorded decisions fix the area field
(globs plus a manifest-declared component map), the overlap check (the report run when a change,
such as a pull request, opens, plus a generated area view), the change reference (a structured
`{change, outcome, reason}` disposition list with a closed outcome set, in an extension first),
the closure rule (proposed then ratified, plus the profile doctor rule requiring a `fixed`
disposition reference), and the aging rule (age in releases or in merged changes, the unit to be
agreed in the lanes standard). The following are choices this text makes beyond those decisions.
They stand as written until the maintainer confirms or replaces them, and a replacement is a
change to this specification:

1. The outcome set is exactly `fixed` and `deferred`.
2. The area lives on the finding, and a finding is carried because it holds `x-aiqt.carried`,
   never because of a severity it records.
3. The table is permitted only on unqualified `routed`, never on `routed/proposed`.
4. The glob dialect above, its root at the product repository root, the `component:` prefix, and
   the component-name pattern.
5. The writer `opf record carried` with its three acts, open to any non-importer actor without a
   `/proposed` landing; a disposition is recorded both in the table and as its worklog entry.
6. The effective disposition is the last one for each `change`.
7. The profile narrows rotation, and the successor remedy and the detail codes
   `carried_unreferenced` and `carried_archived_open` handle a carried finding archived while not
   closed.
8. An `x-aiqt.carried` table on an importer-authored record is ignored as history.
9. The report verb `opf report`, its mode `carried`, and report contract v1 (section 10.8): its
   options, sections, formats, exit codes, and change-body block.
10. The aging reference instant: the latest linking worklog entry's `date`, else the finding's
    `created_at` (section 10.8).
11. The area view's name `CARRIED.md`, its target, and its layout (section 10.8).
12. Profile version 1.1.0, and transform vocabulary version 2 within base `spec_version` 2.0.0
    (section 10.2), together with the base manifest view key `profile` (section 9) and the
    `carried` subcommand listed in the base `opf record` (section 8.8).
13. The pre-write refusal, at the effective posture `required`, of a `done-with-receipt` that would
    leave a remediated carried finding without an effective `fixed` disposition on it, or, for a
    superseded carried finding, on a successor (above).

## 10. Views and deliverables

### 10.1 Deterministic views

Three kinds of generated view, besides the `WORKLOG.md` render below, render from the store, each
declared in the manifest's view map, to `.working/` top level except `ROADMAP.md`, whose target is
the product repository root (section 5.8):

- **1:1 index mirrors**: `<TYPE>-INDEX.md` (the type name uppercased, hyphen, INDEX), one per
  enabled type where declared, mirroring the machine index for human reading.
- **Composed views**: `TODO.md`, `BACKLOG.md`, `DONE.md`, `FINDINGS.md`, `DECISIONS.md`,
  `BLOCKS.md`, `HANDOFF.md`, `REFERENCES.md`, `CONTRIBUTIONS.md`, the optional `VERSION.md`, and
  the optional `CARRIED.md`, which depends on the reference profile (section 10.8), each composed
  from declared sources through the transform vocabulary.
- **Planning-ledger renders**: `PIPELINE.md` and `ROADMAP.md`, each the deterministic render of a
  planning control ledger (sections 10.6 and 10.7). `PIPELINE.md` is not composed through the
  section 10.2 vocabulary; it reads `backlog_item` and `block` only to derive standing through the
  block join (section 8.5). `ROADMAP.md` carries one optional curated preamble above its generated
  header (section 10.7).

Machine projections (section 10.5) are also declared in the view map.

`WORKLOG.md` is declared with the kind `deterministic`: a 1:1 render of `worklog.toml` with no
composition. It is not a planning-ledger render, because `worklog.toml` is the durable record,
never a control ledger (section 8.1).

The root `VERSION` file is a deterministic deliverable rendered from `version.toml`, a control
ledger, into the product repository (section 5.8); it is not classed with the planning-ledger
renders above.

### 10.2 The transform vocabulary

Composition is bounded by a closed, versioned vocabulary: filter on declared field predicates, a
presence predicate included; sort on declared keys with ID as the final tie-breaker; group by a
declared field, an array-valued field included; project declared columns; and exactly three named
joins, the block join (actionability, section 8.5), the decision-resolution link (current
effective resolution through the supersession chain), and the remediation join (below). Anything
beyond the vocabulary version a specification version defines requires a new vocabulary version
and a specification change; ad hoc logic never enters a generator.

This specification defines transform vocabulary version 2. Version 1, the vocabulary of earlier
drafts of this specification, held the four operations over base fields and the first two joins.
Version 2 adds the four entries below, which the area view of section 10.8 needs. Keeping base
`spec_version` 2.0.0 for this addition is a choice for the maintainer to confirm (section 9.3).
Version 2 is part of the base 2.0.0 baseline, as the planning ledgers are (section 10.6): the
reference tooling does not yet implement base 2.0.0 (section 16.1) and no earlier base version is
defined (section 9.2), so no store upgrade is needed, and the additions change the composition of
no view that version 1 composes.

1. **Extension fields as declared fields.** A field inside a registered `x-<vendor>` table whose
   shape a profile defines counts as a declared field for filter, the presence predicate included,
   sort, group, and project, in a view whose declaration names that profile in the view key
   `profile` (entry 4). In any other view an extension field is not a declared field. The
   section 10.5 exclusion of extension tables from the shipped projection is unchanged.
2. **Group by an array field.** Grouping on an array-valued field forms one group per distinct
   element, in Unicode code-point order; a record appears in each group whose element it carries,
   and the records whose array is absent or empty form one final group.
3. **The remediation join.** The third named join yields, for each finding, the backlog items a
   `remediates` link connects to it, whichever record carries the link, each with its status. It
   evaluates clean records authored by non-importer actors only, on both sides (section 8.6). A
   filter MAY select on it, such as a finding with at least one joined item not in an unqualified
   terminal state, and a projection MAY show the joined items and their statuses.
4. **Profile-dependent views.** The view key `profile` (section 9) names the profile a composed
   view depends on. A tool that does not support that profile, or does not support the profile
   version that defines the fields the view reads, records the view as present-but-unevaluated and
   neither renders nor drift-gates it, and never fails base validation over it; a tool that
   supports it renders and drift-gates it like any composed view and fails closed on an
   unreadable, unparseable, or unresolvable input of it (sections 9.1 and 11).

### 10.3 Determinism requirements and generated headers

A deterministic render is byte-reproducible: UTF-8, LF line endings, stable ordering, no
locale-dependent sorting, no wall-clock content in compared bytes, no network access, and no model
involvement. A record field value rendered into a Markdown view stays on one line: LF, CR, U+0085
NEXT LINE, U+2028 LINE SEPARATOR and U+2029 PARAGRAPH SEPARATOR each collapse to a single space (a
CR LF pair to one space), and DEL and the other C0 controls except TAB are dropped, so the rendered
value holds no character that Python's str.splitlines() treats as a line boundary; the store keeps
the value as written.
Every generated file opens with a header stating that it is generated and must not be
hand-edited, naming its source paths, the schema and generator versions, a digest of the source
set, and the regeneration command; the header carries no timestamp. One declared exception exists:
`ROADMAP.md`, the one view that may be declared with `preamble = "optional"` (section 9), MAY
carry a curated preamble above its header, under the delimiting and gating rules of section 10.7.

### 10.4 The curated changelog is not a view

`CHANGELOG.md` is a deliverable, not a deterministic view: its prose is human-curated, so it is
never byte-drift-gated. Its gates are range coverage and freeze (section 7). Its entries carry no
do-not-edit header; instead the changelog opens with a short note that it is a curated summary of
the project's worklog, gated on coverage and publication freeze.

### 10.5 Machine projections

A machine projection is a third generated-output class beside deterministic views and the curated
changelog: a deterministic, byte-drift-gated TOML deliverable at `.working/` top level, its name
UPPERCASE per the casing convention (section 4.6) because it is generated, never hand-authored truth.
It is declared in the manifest view map with the view kind `projection`, so it is covered by the same
render, drift, and doctor gates as any declared view with no new gate. Every determinism requirement of
section 10.3 applies verbatim (UTF-8, LF, stable ordering, no locale-dependent sorting, no wall-clock
content, no network access, no model involvement, and a leading do-not-edit header naming its sources,
the schema and generator versions, a source-set digest, and the regeneration command, with no
timestamp), the header being a leading TOML comment block. Advisory activity over a projection, an
assistant-side prediction, dedup, or pattern-spotting pass, is a READ-TIME activity outside the
generator, so no model output can ever be baked into the generated bytes.

The shipped projection is `DECISIONS.toml`, the machine counterpart to the composed `DECISIONS.md`
view, projected from `pending_decision`, `autonomous_decision`, `maintainer_decision`, and
`preference_pattern`. Its payload (projection contract v1) carries `schema = 1` (the projection
contract's own version, bumped independently) and `projection = "decisions"`; four arrays of tables,
one per source type, each row sorted by numeric ID and projecting the full base record (the envelope
fields, the type's declared extra fields, and `links`/`refs` as nested arrays of tables), with
`x-<vendor>` extension tables excluded as profile-owned data; and one `[derived]` table carrying the
existing decision-resolution join's output (`effective` and `superseded` pending_decision IDs,
numerically sorted) and nothing beyond the closed section-10.2 vocabulary, so no new join is
introduced.

### 10.6 The pipeline control ledger and PIPELINE.md

`.working/toml/pipeline.toml` is the pipeline control ledger: one machine pipeline file beside
`version.toml` and `counters.toml`, a control ledger rather than a record type (section 8.1). It
holds, per lane, the ordered entries the pipeline definition of section 2.1 names: clean backlog
item IDs, or named bundles of them. It is lowercase machine source (section 4.6), exempt from the
per-record layout like the other ledgers (section 9). It is working state rather than a durable
record: an entry leaves the ledger when its item or bundle completes or is dropped, a `[[bundle]]`
row leaves in the same change as the one entry that names it, and removing either deletes no
record, because the ledger holds references and order only, while the durable facts live in the
backlog records, the `done` receipts, and the worklog. `opf init` MUST create the ledger,
create-only, holding `schema = 1` and no rows, and an empty ledger renders a `PIPELINE.md` stating
that no lane is declared. The pipeline and roadmap control ledgers and their renders are part of the
base 2.0.0 baseline: no earlier base version carries them, because none is defined (section 9.2),
and the reference tooling does not yet implement base 2.0.0 (section 16.1), so no store upgrade is
needed. Each ledger and its render are required where the manifest's view map declares the render
(section 9). `opf init` MUST declare both renders in the manifest it writes and MUST create both
ledgers, so every newly initialized store carries both by default; an adopter that publishes no
roadmap MAY remove the `ROADMAP.md` declaration through ordinary review; the `PIPELINE.md`
declaration MUST NOT be removed, and a manifest that does not declare `[views."PIPELINE.md"]` MUST
fail manifest validation (section 9). Where its render is declared, an absent ledger MUST fail
closed at `required` (section 11), never read as empty; where the `ROADMAP.md` render is not
declared, the roadmap ledger MAY be absent. A ledger that is present is a managed store path and
is checked by its doctor check (C-PIPELINE or C-ROADMAP, below and section 10.7) whether or not its
render is declared.

Illustrative shape (the schema release that follows this specification is normative):

```toml
schema = 1

[[lane]]
lane = "fixes-and-hardening"
entries = [
  { item = "BI-412" },
  { bundle = "render-hardening" },
  { item = "BI-398", act = "MD-31", pinned = true },
]

[[bundle]]
name = "render-hardening"
items = ["BI-371", "BI-385", "BI-390"]
```

The shape is closed:

- Each `[[lane]]` table MUST hold exactly `lane` (the lane's name, an adopter-supplied name under
  any lanes standard the adopter follows; section 2.1) and `entries` (an ordered array of entry
  tables, which MAY be empty: a lane with no entries renders as a lane with no entry). Each lane
  name MUST appear exactly once: one list per lane.
- An entry MUST hold exactly one of `item` (a clean backlog item ID) or `bundle` (a declared bundle
  name), plus an optional `act` (the ID of the `maintainer_decision`, or of the `maintainer_action`
  where the governance module is enabled, that records a maintainer override) and an optional
  `pinned` (permitted only as `true`, and only beside `act`). An unknown key MUST fail validation.
- Each `[[bundle]]` table MUST hold exactly `name` (unique among bundles) and `items` (a non-empty
  ordered array of clean backlog item IDs). A bundle is delivered as one reviewed change.
- A bundle name and a roadmap milestone name (section 10.7) MUST each match
  `^[a-z0-9]+(-[a-z0-9]+)*$`; these names are this specification's own. A lane name MUST be a
  non-empty single-line string, unique within the ledger; its form belongs to any lanes standard
  the adopter follows (section 2.1), and this specification constrains it no further.
- Canonical form, the form whose departure is the non-canonical C-PIPELINE failure below and never
  a second C-CONTAINMENT finding (section 5.7), is the canonical serialization of section 5.7 with
  these orderings: the `schema` key first; then every `[[lane]]` table, their file order being the
  ledger order the render follows; then every `[[bundle]]` table, sorted by `name`; within a
  `[[lane]]` table, `lane` then `entries`; within an entry, `item` or `bundle`, then `act`, then
  `pinned`, each entry an inline table on its own line; within a `[[bundle]]` table, `name` then
  `items`; and the byte rules of section 10.3 (UTF-8, LF). The schema release that follows this
  specification fixes any remaining layout bytes.
- Both planning ledgers are hand-edited machine sources written through ordinary review and
  re-emitted in canonical form before commit; no section 8.8 authoring operation writes them. An
  assistant or automation that edits either ledger MUST take the section 5.7 single-writer lease,
  observable at the sync target where the store has one, before it writes, and hold it across its
  writes and, where the store has a sync target, their sync-back (section 5.7), and the command that
  re-emits a ledger in canonical form ships with the schema release that follows this specification.
  After a merge conflict on either ledger, the section 5.7 rule applies as to any store path: take
  the integration base's version and redo the edit on that base, which claims no ID, because the
  ledgers hold references and order only.

The stored order is the authority, and the head entry is the lane's next. The actor that operates
a lane (typically an assistant or automation), working under the adopter's standing priorities,
owns that lane's order; the order is recorded in the ledger and visible in every render of it. The
maintainer MAY reorder or pin any entry, and MAY insert an urgent entry at the head, by a recorded
act: the override's `maintainer_decision` or `maintainer_action` record, whose ID each affected
entry names in `act`. The act record's `actor.kind` MUST be `maintainer`, and a `maintainer_action`
act MUST stand in the unqualified `done` state, which only a maintainer transition lands
(section 8.4), so an assistant or automation can never author or ratify the act that authorizes
its own override. A pin fixes the entry's position relative to the other entries of its lane: except
by a further recorded act, an entry MUST NOT be inserted ahead of, or reordered across, a pinned
entry; a pinned entry MUST NOT be removed except by a further recorded act or once its item, or
every item of its bundle, stands in an unqualified terminal state. An `act` on an unpinned entry
records provenance only: the lane owner MAY later move that entry, and only `pinned` protects
position. Where a `finding` the adopter grades as low severity is left unfixed by the change that
found it (a carried low finding), the backlog item that remediates it (section 8.6, `remediates`)
MUST enter the pipeline as a member of a bundle whose items touch the same area of the product, or,
where no such bundle exists, as an entry in the lane the adopter designates for fixes and hardening,
or, where none exists, as an entry in the lane that owns the area. Severity and area are the
adopter's judgement; the base defines no severity scale and no area field. Where the store declares
the reference profile, the finding's `x-aiqt.carried` table records that judgement for the area
(section 9.3), `opf report carried` lists the open carried findings a change touches, and the
optional `CARRIED.md` view lists them by area (section 10.8). In either case this placement rule is
enforced by review, not by the doctor (section 17). Blocked-ness MUST NOT be stored in the ledger:
it is derived at view time through the existing block join (sections 8.5 and 10.2), and a ledger
render is bounded by the rules of this section and section 10.7 plus that join, never by any new
entry in the section 10.2 vocabulary.

`PIPELINE.md` is the ledger's deterministic render, declared in the view map with the sources
`pipeline`, `backlog_item`, and `block`, and gated on byte drift like any deterministic view
(sections 10.3 and 11). It renders every lane in ledger order and each lane's entries in stored
order, head first. For each entry it renders the entry's item ID or its bundle's `name` and member
item IDs, the `act` ID and the pin where present, and the entry's standing with that standing's
marker; it renders no backlog field beyond the item ID. The fixed marker strings are left to the
schema release that follows this specification.

Each entry's standing is derived at view time, resolving items across the active store and the
archive alike (section 12), and every entry holds exactly one standing, the first of these that
applies, in this order:

- **stale**: the entry's item, or its bundle's every item, stands in an unqualified terminal state
  (the stale entries of the doctor list below);
- **awaiting ratification**: the entry's item holds a `/proposed`-qualified status (section 8.4),
  or its bundle's every non-terminal item does;
- **blocked**: a clean, unqualified `active` block authored by a non-importer actor scopes the
  entry's item, or, for a bundle entry, every non-terminal item of its bundle is so scoped: the
  block join proper (section 8.5), nothing wider;
- **actionable**: the entry's item is actionable or, for a bundle entry, some item of its bundle
  is actionable (section 8.5);
- **not actionable**: every remaining case, for example a bundle mixing blocked, `/proposed`, and
  terminal items of which none is actionable.

The head entry is the lane's next (section 2.1). Where the head is not actionable, the render MUST
mark the head with its standing and MUST name beside it the lane's first entry whose standing is
actionable, passing over stale, awaiting-ratification, and not-actionable entries as it passes over
blocked ones, never reordering the stored list. Where no entry of a lane is actionable, the render
MUST state that the lane has no actionable entry. The render MAY display a lane's keep-ahead depth
where a lanes standard the adopter follows defines one; this specification does not define lane
operation (section 2.1).

The doctor checks the ledger in the integrity layer as C-PIPELINE (section 11); each defect below
is a finding that fails at `required`, except where a bullet states a different treatment:

- a ledger that violates the shape rules above, for example an unknown or missing key, an entry
  holding both or neither of `item` and `bundle`, a `pinned` value other than `true`, an empty
  bundle `items`, a bundle name outside the lexical form, or a lane name that is empty,
  multi-line, or appears more than once, MUST be a finding; a defect a later bullet names is
  reported by that bullet alone;
- every `item` value, and every member of every referenced bundle's `items`, MUST name a clean
  backlog item authored by a non-importer actor, resolving across the active store and the archive
  alike (section 12);
- an entry whose item, or whose bundle's every item, stands in an unqualified terminal state is a
  stale entry: it MUST be reported as `pipeline_stale` detail rather than failed, so a ratified
  completion never fails the store, and it SHOULD leave the ledger in the next ledger change;
- a backlog item MUST NOT appear in more than one lane, or more than once within a lane, directly
  or through a bundle; each such duplicate MUST be a finding;
- every `bundle` value MUST name exactly one declared `[[bundle]]` row, and every declared bundle
  MUST be named by exactly one lane entry;
- a `pinned` key without `act`, and an `act` value that does not resolve, across the active store
  and the archive alike (section 12), to a clean `maintainer_decision` or `maintainer_action`
  record whose `actor.kind` is `maintainer` (for a `maintainer_action`, one standing in the
  unqualified `done` state), MUST each be a finding;
- an unreadable, unparseable, or non-canonical ledger, and an absent ledger whose render the view
  map declares, MUST each fail closed at `required` (section 11), never read as an empty pipeline.

### 10.7 The roadmap ledger and ROADMAP.md

`.working/toml/roadmap.toml` is the roadmap ledger: the machine milestone source beside
`version.toml`, a control ledger rather than a record type (section 8.1). It is lowercase machine
source (section 4.6), exempt from the per-record layout (section 9), and it is working state in
the same sense as the pipeline control ledger: direction, never durable fact. It is written as the
pipeline control ledger is (section 10.6): hand-edited through ordinary review, re-emitted in
canonical form before commit, under the same merge-conflict rule. A milestone's row MUST leave the
ledger in the change that records, in `version.toml`, the release that discharges it; from then on
the changelog entry accounts for the work. The discharging release of a milestone carrying
`target_version` is the release of that version; for a milestone carrying `items` alone, it is the
first release cut after every member item stands in an unqualified terminal state. An item MAY be
named by more than one milestone; each milestone discharges on its own terms. `opf init` MUST
create the ledger, create-only, holding `schema = 1` and no rows, and an empty ledger renders a
`ROADMAP.md` stating that no milestone is declared.

Illustrative shape (the schema release that follows this specification is normative):

```toml
schema = 1

[[milestone]]
name = "adoption-tooling"
title = "Ship the adoption apply and completion path"
theme = "adoption safety"
target_version = "1.4.0"
items = ["BI-371", "BI-412"]
```

- Each `[[milestone]]` table MUST hold `name` (unique among milestones, in the lexical form of
  section 10.6) and `title` (one line), and MUST hold no key this section does not name: an
  unknown key MUST fail validation.
- `theme` is an optional short direction field. `target_version` is an optional SemVer version of
  the planned release that discharges the milestone and MUST NOT name a version already released
  in `version.toml`. `items` is an optional non-empty array, each member of which MUST name a
  clean backlog item authored by a non-importer actor. A milestone MUST carry `target_version`, a
  non-empty `items`, or both, so every milestone names what will discharge it.
- Direction is carried as these short fields. The ledger MUST NOT carry release prose
  (section 6.1); whatever story the fields cannot carry has exactly one curated home, the optional
  preamble below.
- The ledger ordinarily covers the next two or three releases: the milestones and themes ahead,
  ordered by intent (section 2.1) and rendered in row order.

`ROADMAP.md` is a generated public deliverable at the product repository root (section 5.8): the
deterministic render of the roadmap ledger in row order, under the determinism requirements of
section 10.3 and declared in the view map with the source `roadmap` alone and with
`preamble = "optional"` (section 9). The render shows, per milestone in row order, its `name`,
`title`, `theme`, and `target_version` where present, and its `items` as backlog item IDs alone:
the render MUST NOT include a backlog item's title or any other backlog field, so no backlog prose
from a private store enters the public deliverable (section 5.8). Item IDs are rendered as the
opaque strings the ledger holds, and their resolution is C-ROADMAP's alone (below), so a backlog
change never alters the public render or its header's source-set digest.

One optional curated preamble is the single curated seam, the one declared exception to the
section 10.3 rule that a generated file opens with its header. The first line of the `ROADMAP.md`
generated header MUST be the fixed delimiter line `<!-- opf:generated -->`, the same bytes in
every render whatever the sources, digests, or generator version, and the header MUST state that
any bytes above it are a curated preamble, gated on facts (section 3). The preamble is the bytes
of the target file before the first line byte-equal to that fixed delimiter line, and it MUST NOT
contain such a line; `opf render` MUST copy the preamble verbatim above the freshly generated body
and MUST read nothing else from its target. An absent target has an empty preamble; a target that
exists but holds no delimiter line MUST fail closed at `required` and MUST NOT be rendered over.
The byte drift gate compares the bytes from the delimiter line to the end of the file, so the
generated body is drift-gated while the preamble is never byte-drift-gated. The preamble is
hand-written and edited through ordinary review, with no machine draft and no freeze digest; it is
gated on its facts, not its bytes, like the changelog (section 7): every version token the
preamble carries (a SemVer 2.0.0 version string with a leading `v`, delimited by word boundaries;
the leading `v` is what marks a token as a version, so a bare dotted number, a date, or an address
is never gated) MUST, once its leading `v` is removed, name a released version in `version.toml` or
a declared `target_version` in the roadmap ledger, and the gate fails closed on an unreadable input.
`opf render` MUST refuse to write `ROADMAP.md` while the preamble fact gate fails (section 5.8). A
store that wants no curated voice omits the preamble, and `ROADMAP.md` is then byte-identical to
its render.

The doctor checks the ledger in the integrity layer as C-ROADMAP (section 11); each defect is a
finding that fails at `required`: a milestone that violates the shape rules above, a milestone
carrying neither `target_version` nor a non-empty `items`, an `items` member that does not resolve
(across the active store and the archive alike, section 12), a `target_version` naming a released
version, and an unreadable, unparseable, or non-canonical ledger, or an absent ledger whose render
the view map declares, which MUST fail closed, never read as an empty roadmap. Canonical form is
the canonical serialization of section 5.7 under the section 10.6 orderings: the `schema` key
first, then every `[[milestone]]` table in row order, keys within each table in the order this
section lists them (`name`, `title`, `theme`, `target_version`, `items`); a departure is this
non-canonical C-ROADMAP failure, never a second C-CONTAINMENT finding (section 5.7).

### 10.8 The carried-finding report and area view

`opf report` is the reference tooling's report verb. Every mode of it MUST be read-only and
report-only: it MUST write nothing but its standard output and standard error, MUST NOT take a
lease, read the network, or read the clock, and no posture makes its content a gate (section 11).
The verb adds no conformance requirement for a store, so a store that never runs it stays
conformant (section 1). This specification defines one mode, `opf report carried`, the report over
the carried findings of section 9.3. A host or an assistant runs it when a change opens or is
updated; how its output reaches the change is the host's concern.

Inputs (each option at most once; an unknown or repeated option, or a combination this list does
not allow, is a malformed argument):

- The resolved store. Where it does not declare `[profiles.aiqt]` at version 1.1.0 or later, in a
  version the tool supports (section 9.3), the command MUST exit as cannot-evaluate, never with an
  empty report.
- Exactly one mode: `--changed <file>` (change mode) or `--by-area` (by-area mode). Both, or
  neither, is a malformed argument.
- `--changed <file>`: the change's changed paths, where `-` reads standard input. The input is
  UTF-8, every line ends with LF, and an empty input is an empty list. Each line is a path relative
  to the product repository root: one or more segments separated by `/`, with no leading or
  trailing `/`, no empty segment, and no segment that is `.` or `..`. A segment MAY hold any
  character other than `/`, a C0 control character, and DEL, so a `*` or `?` in a path stands for
  itself. Identical lines collapse to one.
- `--by-area`: list every open carried finding grouped by area entry, instead of matching a change.
- `--format text` (the default) or `--format toml`.
- `--age-unit releases` or `--age-unit changes`, with `--age-threshold <n>` for a positive decimal
  integer `n` without leading zeros: both or neither. The command has no default unit and no
  default threshold: the unit and the threshold are for the lanes standard the adopter follows to
  agree (section 2.1), and the command takes them only as arguments.
- `--merged <file>`: required with the `changes` unit and a malformed argument otherwise. It lists
  the merged changes, where `-` reads standard input; at most one of `--changed` and `--merged`
  reads standard input. The input is UTF-8, every line ends with LF, and an empty input is an empty
  list. Each line is an RFC 3339 UTC instant ending in `Z`, one space, and the change's locator, a
  non-empty string holding no C0 control character and no DEL. Identical lines collapse to one;
  two lines that give one locator different instants are malformed.

Selection reads the carried findings and remediating backlog items of section 9.3, across the
active store and the archive alike (section 12). The report lists open and unremediated carried
findings; a closed carried finding is never listed, and neither is a superseded carried finding
(section 9.3), whose successor stands in for it. The open remediating backlog items of an open
carried finding are those not in an unqualified terminal state, and its standing is
`awaiting_ratification` where every one of them holds a `/proposed` status and `open` otherwise.

A changed path matches an open carried finding when it matches a glob of one of the finding's area
entries, a component reference contributing its component's globs (section 9.3). An open carried
finding without `area` is listed as having no area in every run and never matches.

Aging measures how long an open carried finding has gone untouched; an unremediated finding is not
aged. Its reference instant is the latest `date` of an entry of the clean worklog (section 6.2),
its archive included, that links the finding, whatever the relation, or the finding's `created_at`
where no such entry links it. Its age in `releases` is the number of `[[release]]` rows in
`version.toml` without the `imported` flag whose `date` is later than the reference instant; its
age in `changes` is the number of distinct `--merged` lines whose instant is later than the
reference instant. A finding whose age reaches the threshold is aged. An aged finding is a
candidate only: routing it to a lane is an act under the lanes standard and a pipeline control
ledger change (section 10.6), never a write of this command.

Output contract (report contract v1):

- The output MUST be deterministic under the byte rules of section 10.3: UTF-8, LF line endings,
  no timestamp, and the orderings below, so the same store and the same inputs give the same bytes.
- The command MUST exit 0 whenever it writes the report, whatever the report lists, and MUST exit 2
  as cannot-evaluate, writing nothing to standard output, on an undeclared or unsupported reference
  profile, an unreadable or unparseable store input, a C-CARRIED-SHAPE defect (section 9.3) in a
  record or table it reads, or a malformed argument or input line. It never exits 1, because a
  report has nothing to fail.
- Every run reports these sections, in this order: in change mode `match`, then `no_area`,
  `unremediated`, and, where aging is requested, `aged`; in by-area mode `area`, then `no_area`,
  `unremediated`, and, where aging is requested, `aged`. Their entries, with keys in the order
  listed:
  - `match`: one per open carried finding that a changed path matches, with `finding`,
    `standing`, `backlog` (its open remediating backlog item IDs), `areas` (the area entries, as
    written, that a changed path matched), and `paths` (the changed paths that matched).
  - `area`: one per distinct area entry that an open carried finding carries, with `entry` (the
    entry as written, a component reference never expanded) and `findings` (the open carried
    findings that carry it).
  - `no_area`: one per open carried finding without `area`, with `finding`, `standing`, and
    `backlog`.
  - `unremediated`: one per unremediated carried finding, with `finding`.
  - `aged`: one per open carried finding whose age reaches the threshold, with `finding`,
    `standing`, `backlog`, and `age` (an integer).

  The `area` entries are in Unicode code-point order of `entry`, and the entries of every other
  section in ascending numeric order of `finding`. Within an entry, `backlog` and `findings` are in
  ascending numeric ID order, and `areas` and `paths` in Unicode code-point order.
- The `toml` format holds, in this order: `schema = 1` (the report contract's own version, bumped
  independently), `report = "carried"`, and `mode` (`"change"` or `"by-area"`); an `[inputs]`
  table, present only where it holds a key, holding in this order `changed_sha256` (in change mode,
  the SHA-256 digest of the `--changed` bytes as read), `age_unit` and `age_threshold` (where aging
  is requested), and `merged_sha256` (for the `changes` unit), each digest written as 64 lowercase
  hexadecimal digits; then one array of tables per reported section, `[[match]]`, `[[area]]`,
  `[[no_area]]`, `[[unremediated]]`, and `[[aged]]`, in the section order and each present only
  where the section has an entry. It is written in the canonical serialization of section 5.7 with
  this layout: each key on its own line as `key = value`; strings as TOML basic strings; integers in
  decimal; every array inline on one line, its elements separated by a comma and one space, with no
  space inside the brackets; one empty line before each table header and no other empty line; no
  comment; no trailing whitespace; and a final LF.
- The `text` format carries the same content in fixed lines, each ending with LF and none carrying
  trailing whitespace. The first line is the title line, the fixed string
  `opf report carried: report contract v1, mode ` followed by `change` or `by-area`, with one space
  after the comma and after `mode`. Then comes one line per `[inputs]` key present, in the `toml`
  key order, written as the key, a colon, one space, and the value. Then each section the run
  reports, in the section order, opens with one empty line and its fixed heading line:
  `## Matches`, `## Areas`, `## No area`, `## Unremediated`, or `## Aged`. A section with no entry
  holds the single line `none`. Each entry opens with a line holding `- ` and the entry's first
  value (the finding ID, or the `entry` of an `area` entry), then one line per remaining key, in the
  key order above, holding two spaces, the key, a colon, one space, and the value; an array key
  gives one such line per element, in the array's order.
- In change mode, the `text` format ends with one empty line, the fixed heading line
  `## Change body`, and the change-body block: the fixed delimiter line
  `<!-- opf:carried:begin -->`, one line per `match` entry in the section's order, and the fixed
  delimiter line `<!-- opf:carried:end -->`. A block line holds the finding ID, one space, the
  entry's `backlog` IDs separated by a comma and one space and enclosed in parentheses, a colon,
  one space, `fixed here`, the separator ` | ` (one space, a vertical bar, one space), and
  `not fixed, because:`. With no `match` entry, the section holds the single line `none` and no
  delimiter line. The change's author keeps one alternative on each line and completes the reason.
  The change body is not a store file, so completing the block breaks no generated-file rule, and
  the list of IDs is never kept by hand. The author records each outcome as a disposition in the
  store through `opf record carried` (section 9.3); the block itself records nothing.

An example `text` report in change mode without aging, where `--changed` holds the two lines
`src/render/header.py` and `docs/usage.md` in that order, the first matches the carried finding of
Appendix A, one open carried finding has no area, and none is unremediated:

```text
opf report carried: report contract v1, mode change
changed_sha256: 5d01140ebfcf660058a7faa8b5983ad039cdaecfdb149deac2ba9a0c67ba9239

## Matches
- FN-12
  standing: open
  backlog: BI-57
  areas: component:render
  paths: src/render/header.py

## No area
- FN-19
  standing: awaiting_ratification
  backlog: BI-63

## Unremediated
none

## Change body
<!-- opf:carried:begin -->
FN-12 (BI-57): fixed here | not fixed, because:
<!-- opf:carried:end -->
```

`CARRIED.md` is the area view: the standing generated listing of the open carried findings grouped
by area entry, a composed view under the determinism requirements of section 10.3, composed through
transform vocabulary version 2 (section 10.2). It is optional: a store that declares the reference
profile at version 1.1.0 or later MAY declare it, and its declaration MUST carry
`kind = "composed"`, the sources `finding` and `backlog_item`, the target `.working/CARRIED.md`, and
`profile = "aiqt"` (section 9). As an exception to section 10.2, entry 4, a tool that supports the
profile at version 1.1.0 or later MUST fail manifest validation for a `CARRIED.md` declaration in a
store that declares the profile below version 1.1.0; a tool that supports the profile only below
1.1.0 records the view as present-but-unevaluated (section 10.2, entry 4). The view's composition
is fixed:

- Filter: a clean `finding` authored by a non-importer actor, in unqualified `routed`, on which
  `x-aiqt.carried` is present, with at least one item of the remediation join not in an unqualified
  terminal state: the open carried findings of section 9.3.
- Group: by `x-aiqt.carried.area`, one group per area entry as written, a component reference under
  its own name and never expanded, so the view reads neither the product tree nor the component
  map; the open carried findings without `area` form the final group.
- Sort: within each group, by finding ID in ascending numeric order, and the projected items of a
  finding by item ID in ascending numeric order.
- Project: per finding, its ID, its `title`, and each item of the remediation join not in an
  unqualified terminal state with its status, so an item awaiting ratification shows its
  `/proposed` status (section 8.4).

Layout: after the generated header of section 10.3, each group opens with one empty line and the
heading line `## Area ` followed by its area entry as written, and the final group's heading line
is `## No area`, which no area group's heading can equal; a finding's line is `- `, its ID, one
space, and its `title`, and each projected item follows on its own line as two spaces, `- `, the
item ID, one space, and its status. A group with no finding is not written. The schema release
that follows this specification fixes any remaining layout bytes, as it does for `PIPELINE.md`
(section 10.6).

The view reads the active store alone: an open carried finding does not rotate (section 9.3), and
neither does an open backlog item (section 12). `opf report carried --by-area` lists the same open
carried findings by area as tool output, apart from a carried finding rotated against section 9.3
that no successor supersedes, which only the report lists, and adds the unremediated and aged
sections the view does not carry.

## 11. Enforcement posture

Enforcement has two layers with deliberately different ceilings:

| Layer | `off` | `warn` | `required` |
|---|---|---|---|
| Artifact and record integrity | not run | reported, non-failing | build-failing, fail-closed |
| Adoption coverage | not run | report only | report only, never build-failing |

The integrity layer is deterministic and safe to hard-fail; `opf doctor` runs it. It includes:
schema validity of what exists; ID uniqueness across active, archive, and staging; counter
monotonicity; bidirectional index reconciliation; transition legality and no-resurrection; the
all-or-none resolution bundle; view drift (byte) for every deterministic view including `VERSION`,
with the `ROADMAP.md` body compared from its fixed delimiter line and its preamble fact gate
evaluated beside it (section 10.7); the pipeline control ledger checks (C-PIPELINE, section 10.6);
the roadmap ledger checks (C-ROADMAP, section 10.7);
worklog span tiling and frozen coverage digests; changelog range coverage; changelog freeze;
archive integrity; the tracked-store requirement against the resolved store; pointer and
sync-target agreement (the committed pointer, the manifest's recorded sync target, and the store
repository's actual remote agree; section 5.6); unmanaged-path containment (section 14.2); and
path containment. At `required`, an unreadable, unparseable, or unresolvable declared input MUST be
a failure, never an empty or clean result. Imported history joins this integrity layer through
the deterministic checks in sections 8.3 and 8.6; the authority firewall MUST NOT be report-only.
A tool that supports a declared profile runs that profile's checks beside this layer as extra
gates at the effective posture (section 9.1); for the reference profile these are C-CARRIED-SHAPE
and C-CARRIED-CLOSURE (section 9.3), whose findings are reported against the profile, never
against the base (section 16). A profile-dependent composed view, such as `CARRIED.md`, joins the
view drift check only in a tool that supports its profile; any other tool records it as
present-but-unevaluated (section 10.2). The output of `opf report` is never a gate at any posture
(section 10.8).

`import_status = "none"` means clean start with no approved migrate-source import.
`"partial"` means the adoption receipt enumerates migrate-disposed sources whose completion
results are not yet recorded green (section 14.1); it can persist across assistant sessions
without a process running.
`"complete"` means every such source has a green completion result and recorded retirement under
section 14.1 with a live full doctor VALID.
A partial or complete status that no adoption receipt with completion results substantiates MUST
fail closed, as does a missing, unreadable
or contradictory input. Elapsed time and a staging directory MUST NOT be taken as proof of status.
From the recorded approval until its retirement is recorded, a path the approved plan enumerates
as a frozen retire, move or migrate source (section 14.2) is bounded adoption state: while its
live bytes still match its plan digest, containment MUST report it as `migration_incomplete`
detail rather than failing it, at `"none"` during a clean start as much as at `"partial"`. A
digest mismatch (a drifted source), a source that is gone before its retirement is recorded (a
vanished source), or an unenumerated path MUST remain a containment-gate failure at `required`;
the bounded treatment is never a blanket exemption. A formerly occupied
destination needs no bounded treatment: its occupying source was archived at apply (section
14.2), the destination is an ordinary managed path from apply onward, and a check that reads the
adoption archive, the section 14.1 completion check and import included, MUST fail at `required`,
naming the path, on a missing, unreadable or digest-mismatched archived copy.

Adoption coverage (which types are populated, which modules are wired, how much of the project's
operational surface has moved into the store) is a report, never a gate: breadth of adoption is a
journey, and failing a build over it would train bypasses. It MUST stay report-only at every
posture.

Defaults: scaffolding and clean-start adoption MUST write `posture = "required"` and
`import_status = "none"`. An adoption with migrate-disposed sources keeps `required` and MUST
hold `import_status = "partial"` until each source's completion result is recorded green
(section 14.1), then `"complete"`.
Import status MUST NOT weaken posture. Reports MUST carry `migration_incomplete` while an approved
source or detected file remains unresolved. Weakening the posture (`required` toward `warn`
or `off`) is a guardrail-configuration change: it MUST take effect only through the
maintainer's explicit, recorded authorization, separate from adoption approval, and MUST NOT
be self-applied by the assistant or by tooling.

A profile MAY raise, and MUST NOT lower, the effective posture: the effective posture is the
strictest of the base `posture` and every supported profile's `posture_floor`. Weakening the base
`posture` remains a guardrail-configuration change under the maintainer's recorded authorization; a
profile floor is additive and MUST NOT substitute for that authorization in the loosening direction.

## 12. Rotation, archive, and retention

Rotation MUST be relocation, never deletion, and never ID reuse. Records in unqualified terminal
states, other than worklog records, MAY rotate to `.working/toml/archive/<YYYY>/` (calendar-year
buckets) on manifest-declared age or size thresholds. Worklog records are excluded from that generic
terminal-record permission and rotate solely under the release-based rule: only released, frozen
worklog spans MAY rotate, and the unreleased `recorded` tail never rotates whatever its age or size,
because it is pre-terminal and mutable-until-release (sections 6.2 and 8.4). Open records, active
blocks, unresolved decisions, unexpired waivers, the current handoff, and the
unreleased worklog tail MUST NOT rotate. A declared profile can only narrow rotation further: the
reference profile keeps a carried finding that is not closed out of the archive (section 9.3).
The imported series MUST NOT rotate:
`<type>.imported.index.toml` and `worklog.imported.toml` sit outside the rotation thresholds and
their records MUST NOT move to the record archive.

The record-rotation archive under the discovered machine store is distinct from the store-tree
`archive/` in section 4.2, which retains relocated adopter files, adoption preimages and archived
occupying sources (section 14.2), never rotated records. Tooling MUST NOT scan either as the
other. Imported originals, acceptance evidence, retirement preimages, and archived occupying sources
MUST be retained indefinitely by default, except for the pre-commit abort reversal of archived
occupying sources and retirement preimages written by the aborted, uncommitted apply in section 14.2.
Automatic reclamation MUST apply only to staging runs,
after independent re-read and digest verification of their required evidence in its durable home;
age alone MUST NOT authorize deletion.

Each rotation MUST write the year's `archive.toml`, enumerating every moved ID (and, for the
worklog, every moved span) and its destination. Validation MUST confirm that every ID exists in
exactly one active or archived location, and coverage gates MUST read active and archive together,
so rotation never changes any gate's answer. `counters.toml` MUST remain untouched by rotation,
preserving ID permanence. Retention is thereby indefinite by default; an adopter bound by a
retention policy MUST apply it as a recorded maintainer decision governing archival and rotation
(aged data moved into the archive, preserved byte for byte), never as deletion of a record.

## 13. Change evidence

Change evidence is layered. History makes every record change, including an edit that bypasses the
recorded flows, visible to review. The integrity layer (section 11) also reports such an edit
wherever one of its checks covers it; section 11 describes its checks. An edit that none of its
checks covers is visible to review only. No layer detects a deliberate edit by someone who can also
rewrite the history and the recorded digests, which remains the same-user tampering residual
disclosed in section 14.1. The layers are:

- **History.** The tracked store (section 5) puts every record change in version-control history
  under the project's review gate, and store relocation preserves that history (section 5.4); the
  store is never the only copy of its own past.
- **Frozen digests.** Released worklog spans are frozen by `coverage_digest`; published changelog
  entries are frozen by their summary digests. A silent edit to either breaks a recorded digest and
  fails the integrity layer; the only way through is the recorded re-publish flow (section 7.2).
- **Index reconciliation.** In the per-record layout, index rows carry per-record digests, and
  reconciliation between the index and record files is bidirectional; in the inline layout, the
  index and store coincide and reconciliation runs against the views and ledgers.
- **Archive enumeration.** `archive.toml` makes every rotation enumerable, so a record cannot
  quietly vanish under the name of rotation.

Records are never deleted: an unreleased entry may be corrected in place, and a frozen or released
record is immutable or supersession-marked. Nothing ever leaves the store. A record moves only by
rotation, an archival relocation within the store that `archive.toml` enumerates (section 12), which
preserves the record byte for byte and keeps every ID resolvable in its active or archived location.
That enumeration records the movement; it never authorizes a departure from the store or a deletion.

## 14. Adoption, post-adoption import and pre-existing files

`opf adopt` guides setup and wiring; `opf import` is only the post-adoption import activity.
Relocating the store remains `opf migrate` (section 5.4). Clean start is first-class: preserve
and retire old operational files, establish the new store and enforcement, and import nothing.
This makes no claim that historical obligations were fulfilled or converted.

Adoption follows investigate, plan, one approval, apply, completion, then retirement. Investigation
MUST distinguish first adoption from re-adoption and MUST record a digest-stamped inventory,
including governance surfaces for each supported assistant platform. Every foreign `.working/` file,
and every pre-existing file at a declared view or deliverable destination outside `.working/`, the
product-root `VERSION` and `ROADMAP.md` included, MUST have a disposition before `init-store`;
adoption MUST NOT run blind init over populated content. Apply MUST compose the coupled-init
substrate and the journaled adoption operations, with per-operation preimage checks and reversal.
It MUST end with rendered views at every declared destination, a destination whose occupying source
apply archived under section 14.2 included, and with an adoption receipt plus its outcome-event
chain. A bootstrap `views-ready` marker alone MUST NOT count as adoption success.

### 14.1 One approval and completion

A manifest declaring a `spec_version` of 2.0.0 or above whose `[opf].homes` is missing or not
the integer 2 is refused as a store (section 9.2), never foreign content: investigation over it
MUST fail closed and MUST NOT read that refusal as authorizing any adoption (sections 4.5 and
8.2). A manifest refused only at the section 9.2 version ceiling marks a store at a later version,
never foreign content: investigation over it MUST fail closed, naming the tooling-upgrade remedy,
and MUST NOT read that refusal as authorizing any adoption (sections 4.5 and 8.2).

Exactly one adopter approval MUST follow each concrete plan. The `opf.adoption.plan/v2` plan MUST
bind:

- product and store identities and the observed revision;
- every source path, byte digest, disposition and preservation destination;
- exact creations, replacements, removals and consumer repointings;
- tool release identity, including `manifest_sha256` and the named anchor it was checked against
  (a copy of that digest published apart from the release artefact), the two digests agreeing;
- the version and digest of the prompt pack;
- enforcement-pack contents per platform and each platform's disclosed residual coverage;
- the completion-check roster and the rule that retirement requires green checks and matching bytes;
- the missingness and unparsed-content policy, the skip policy under which a migrate-disposed
  source may be recorded as skipped, and the migrate-disposed sources import may touch.

The attributed approval MUST bind `plan_digest` and `inventory_digest`, hence that whole plan.
A per-fragment acceptance or later adopter checkpoint MUST NOT occur within the approved plan.
Any bound-item drift MUST refuse into a fresh plan with its own single approval; a changed old
file MUST NOT be retired. One renewal is not drift: a section 5.4 whole-store relocation MUST
rebind the plan's bound paths to their relocated equivalents with the bound digests unchanged
(section 14.2). Approval MUST NOT absorb a separate posture-weakening authorization (section 11)
or changelog curation (section 7.3). Digests establish binding, not actor authenticity or
semantic correctness; self-asserted identity and same-user tampering remain disclosed residuals.

The clean-start completion check MUST deterministically verify the following roster:

1. Authority and freshness: roots, destinations and live preimages still match the approved plan.
2. Discovery accounting: every inventory entry has a disposition or recorded exclusion.
3. Preservation and restore: each retirement preimage, preserved at apply for a retire-disposed
   file and for a non-occupying migrate-disposed source alike, and each archived occupying source
   (section 14.2) exists, digest-matched, under `.working/archive/adoption/<run-id>/`, and a
   restore exercise reproduces its bytes.
4. Operational readiness: the store resolves to the planned identity, and CI asserts store
   presence and identity so absence cannot pass as NOT-APPLICABLE. Doctor validity and
   declared-view byte drift are evaluated on the live tree, where apply has already rendered
   every declared view, a formerly occupied destination included, and any drift the plan does
   not account for fails the check. Consumer repointings match the plan.
5. Wiring: the enforcement pack is installed and probed, with a direct store write denied, a
   write under `.working/archive/adoption/<run-id>/` denied, and sanctioned writer and render
   paths succeeding on the live tree. Server-side branch protection is adopter-attested,
   explicitly outside the local probe's guarantee.
6. Retirement readiness: each retire-disposed file that occupied no managed destination is
   present in the live tree and its live bytes still equal its plan digest, and each archived
   occupying source still equals its plan digest in the archive.

Retirement MUST be recorded only on a green completion check. For an occupying source, apply has
already archived and removed it under section 14.2, so the green check records its retirement
without touching the live tree, and MUST re-verify its archived bytes against the plan digest
before recording. For an old file at no managed destination, the physical removal or relocation
MUST also wait for the green check: the file MUST stay frozen, byte-identical in place, its live
bytes MUST still equal the plan digest when the removal or relocation runs, and that removal or
relocation MUST run as one journaled, recoverable transaction under the section 5.7 consistency
contract and lease. A completion-check failure or cannot-evaluate MUST report incomplete and MUST
retire nothing; changing the approved work MUST take a fresh plan. Once apply commits, restoring
an archived file to the live tree is new approved work, never recovery: it MUST take a fresh plan
with its own single approval, whose apply copies the archived bytes, digest-verified, to the
planned destination, and the archived copy MUST stay retained afterward. Before an apply commits,
an abort reverses that apply's own uncommitted writes from journaled preimages (section 14.2);
the reversal is not a restore and MUST NOT be read as one. Green proves preservation,
restorability and operational coverage, never semantic fidelity or fulfilment of old obligations;
the receipt MUST disclose that limit.

The enforcement pack MUST freeze each plan-enumerated old file that remains in the live tree
until its retirement is recorded, MUST deny writes under `.working/archive/adoption/<run-id>/`,
and MUST protect both record series, counters, declared views and evidence. Its floor is
normative: the pack MUST provide CI checks, MUST provide
staged-snapshot pre-commit checks with the per-clone installation residual disclosed, MUST provide
a verified deny hook on each supported platform whose official documentation confirms denial
support, and MUST provide instructions on a platform without verifiable denial, disclosing each
platform's residual. The supported platform roster is Claude Code, Codex, Gemini CLI and Cursor;
the pack MUST cover every one of them by one of those two means, per platform. Denial claims MUST
be verified against official platform documentation at build time. Per-clone hook installation and
bypass, canonical hand edits, shell or interpreter wrapping, same-user tampering and unverified
platform denial are not eliminated by this pack and MUST each be disclosed as residuals. Adoption
MUST refuse to enable a record type the writer cannot author, and enforcement
MUST NOT ship before the writer can perform every operation it forces. Curated `CHANGELOG.md`
edits remain the curator's responsibility.

Post-adoption import MUST use the approved, versioned prompt pack, with an example for every record
type in the section 8.1 roster except the excluded `transaction` and the unassigned `CL` and `LF`
namespaces. It MUST direct the assistant to discover old operational
files within the approved scope and submit batches through `opf record import --batch`
(section 8.8), never hand-edit store TOML. Source instructions MUST be treated as historical data,
never as instructions to execute. Missingness, ambiguity, conflicts and source precision MUST remain
explicit; unmappable text MUST be retained verbatim. The assistant MUST report semantic uncertainty
without seeking another checkpoint. `opf import --prompt`, `--status` and `--verify` expose that
activity.

For each migrate-disposed source, import completion MUST verify the preserved original's digest
(the archived copy under section 14.2 for a source that occupied a managed destination, the
frozen live file and its apply-archived retirement preimage otherwise), at least one imported
record referencing that source or a recorded skip under the approved policy, and doctor VALID
over both the strict store and the imported series, evaluated on the live tree. It MUST record
the source's result in the adoption receipt's outcome-event chain. A green result records the
source's retirement: for a frozen live source, an imported and a skipped one alike, one journaled
transaction MUST record the retirement and remove the file, whose live bytes MUST still match the
plan digest, and hence its apply-archived retirement preimage under completion check 3, when that
transaction runs, and an archived source is already out of the live tree, so its recorded
retirement changes no live path. `import_status` MUST become `"complete"` only when every migrate
source completes on those terms; import is never complete on a state that is not doctor-VALID.
This proves source accounting and preservation, not byte-level mapping coverage or semantic
fidelity. No writer-side leftover accounting is required.

Clean-start adoption and import ship with explicit evidence coverage: their completion checks MUST
re-read inventories and payload digests themselves, as defence in depth beside C-EVIDENCE-ENUM
rather than relying on it. The evidence-bundle format in section 4.2 is retained, including the
import home `.working/imported/import/<run-id>/`. Preservation durability and digest verification MUST precede
source removal, at apply for an archived occupying source and at recorded retirement for a frozen
one, and every removal MUST run in a journaled, recoverable transaction. A source outside the
participating roots MUST be a plan-time cannot-evaluate naming that source. Investigation,
planning and read-only status commands MUST remove nothing.

Required evidence MUST be re-read and digest-matched in its durable home before
staging reclamation. Reclamation MUST be journaled and idempotent; an unreadable tree MUST hold the
run. Read-only commands MUST NOT clean staging.

### 14.2 Pre-existing files at the store location

`opf adopt` MUST investigate every file at the target `.working/` location that is not OPF-managed,
and every pre-existing file at a declared view or deliverable destination outside `.working/`, the
product-root `VERSION` and `ROADMAP.md` included: the manifest, ledgers, counters, clean and
imported typed indexes, declared views and registered control areas define the managed set. A
matching pathname alone does not prove OPF ownership: foreign content at a planned managed
destination, a machine-store path as much as a view path, MUST still take a disposition. A
hand-maintained `TODO.md` belongs to the adopter.
`opf init` MUST refuse undispositioned foreign content; post-adoption import MUST use only its
approved source scope and MUST NOT authorize an incidental discovery.

The plan MUST record one disposition per foreign file from `keep`, `migrate`, `move`, `retire`:

- **Keep.** Leave it untouched and register it under `[unmanaged]`. Ordinary tooling MUST NOT read,
  rewrite or delete it. An `[unmanaged]` path MUST NOT equal or contain a discovery candidate, a
  `manifest.toml` present in an immediate subdirectory of `.working/` (section 4.5); such an entry
  is a contradictory input and MUST yield cannot-evaluate, so the keep protection never covers a
  file that discovery reads. A `keep` declaration whose path equals or contains a discovery
  candidate MUST refuse at plan time, naming that candidate, the same way a collision refuses below. A
  no-follow existence probe of `manifest.toml` in an immediate subdirectory of `.working/`, a kept
  one included, used only by discovery and by this rule, is not a read of a kept path. An unmanaged
  path MUST NOT collide with an OPF-managed file or view: a
  `keep` declaration naming a declared view or managed store path MUST refuse at plan time, and a
  later manifest change, type enablement or upgrade delta that would declare a view or managed store
  path at a registered `[unmanaged]` path MUST refuse the same way (section 9.2), so a kept path
  never becomes an occupied destination.
- **Migrate.** Keep the source for post-adoption import into the separate imported series. Its
  exact bytes MUST be preserved at apply, as the archived occupying copy for an occupying source
  and as a retirement preimage under `.working/archive/adoption/<run-id>/<source-path>` for a
  non-occupying one (completion check 3), and its retirement MUST be recorded only after its
  source completion check is green (section 14.1). There MUST NOT be an imported view. Import
  MUST read an occupying source's archived copy and a non-occupying source's frozen live file.
- **Move.** Relocate to a named destination outside the managed store, or by default to
  `.working/archive/moved/<source-path>`, preserving substructure. An occupied move destination
  MUST be a collision finding, never an overwrite. An explicit destination inside the store tree
  MUST lie beneath `.working/archive/moved/`. The default Move MUST refuse a store resolved
  outside the product root until a multi-root coordinator exists. The relocation MUST run only
  after the plan-bound green completion check, with digest-verified preservation; for an
  occupying source it MUST copy the archived bytes to the move destination, and the archived
  copy MUST stay retained.
- **Retire.** The first-class clean-start choice: the exact preimage MUST be preserved under
  `.working/archive/adoption/<run-id>/` with restore proven, and the retirement MUST be recorded
  only on the green completion check (section 14.1). No old obligation is thereby fulfilled.

Occupied destinations are resolved preserve-first, uniformly for a declared view path and a
machine-store path alike. Within the one approved apply transaction, apply MUST copy each
occupying source byte-identically to `.working/archive/adoption/<run-id>/<source-path>`, MUST
verify the copy's digest against the plan digest, MUST commit the copy durably, and only then
MUST remove the source from the live path: verify, then remove, in that order, never reversed
and never split across transactions. Before apply commits, an abort takes the ordinary
per-operation preimage reversal of section 14: the reversal MUST restore each removed source to
its live path from its journaled preimage, MUST verify the restored bytes against the plan
digest, MUST commit the restored bytes durably, and only then MAY discard the aborted run's
archive copy of that source, so an interruption leaves each source either live and byte-identical
or archived with its removal journaled, never removed
without a durably committed, digest-verified archive copy.
The reversal MAY also discard retirement preimages written by that uncommitted apply for
non-occupying sources, since each such source remains frozen, live and byte-identical in place
and is never removed at apply. That
reversal undoes the uncommitted apply's own writes; it is not the section 14.1 restore, whose
fresh-plan rule governs an archived file only once apply commits. Recovery of an interrupted
apply MUST resolve from the apply journal alone and MUST NOT require the live tree to resolve as
a store: on restart the one transaction either completes forward from its durably committed
journal or reverses fully as above, so an interruption that removed an occupying machine-store
file, the manifest included, never leaves the store unresolvable or waiting on a plan it cannot
form. A fully reversed first adoption leaves `.working/` holding its retained journal, so the
store location reads as present without a manifest (section 4.5), and journal state that a
foreign tree planted there is touched only by a fail-closed refusal, never consumed as recovery
state; clearing it is the operator's own act outside any OPF operation, a same-user residual of
the class section 14.1 discloses. After the archival
the destination is an
ordinary managed path: apply initializes
the machine file or renders the view immediately, and no writer carries an occupied-destination
obligation afterward. The archived copy is the disposition's preserved original: the retire
preimage, the source import reads for `migrate`, or the bytes a `move` relocation copies out
after the green check. Archival is preservation, not retirement: the green completion check of
section 14.1 remains the one gate that records each disposition's retirement. An old file at no
managed destination takes no archival at apply beyond its retirement preimage under completion
check 3, preserved at apply for a retire-disposed and a migrate-disposed file alike: it MUST stay
frozen, byte-identical in place, and MUST be removed or relocated only after the applicable green
check, exactly as section 14.1 orders.

The adoption archive is immutable in each archived file's store-relative identity and bytes. Once
apply commits, a file under `.working/archive/adoption/<run-id>/` MUST keep that store-relative
path and those exact bytes: it MUST NOT be written, rewritten, relocated or removed within its
store by any OPF operation, and the enforcement pack MUST deny writes there (section 14.1). A
section 5.4 whole-store relocation MAY carry the archive, and only as part of the whole
`.working/` tree it relocates: every archived file keeps its store-relative path and its exact
bytes, `opf migrate --store` MUST re-verify every carried archived copy's digest against the plan
at the destination before the old tree is removed, and the enforcement pack's write denial with
the completion check 5 probe (section 14.1) binds `.working/archive/adoption/<run-id>/` within
the resolved store, at the destination after that relocation as before it. The completion check
MUST re-verify every archived copy's digest against the plan (section 14.1, check 3), import MUST
re-verify an archived source's digest against the plan before reading it, and a missing,
unreadable or digest-mismatched archived copy MUST fail closed at `required`, naming the path.
Once apply commits, restoring an archived file to the live tree MUST be a fresh plan with its own
single approval (section 14.1); no other operation restores it, and the pre-commit abort reversal
above is not restoration. A frozen source whose live bytes no longer match its plan digest is a
drifted source: it MUST NOT be archived, retired, moved or removed, doctor MUST fail it at
`required` (section 11), and the remedy MUST be a fresh plan with its own single approval
(section 14.1).

`opf migrate --store` is whole-store relocation (section 5.4), never disposition execution: it
MUST carry every frozen source, the adoption archive and every evidence bundle byte-identically
into the destination at unchanged store-relative paths, MUST NOT execute, advance or end any
disposition, and MUST renew the approval's bound paths to their relocated equivalents in the
same recorded change, the bound digests unchanged; any byte difference remains bound-item drift
refusing into a fresh plan (section 14.1).

Detection MUST surface unresolved files in the plan and MUST NOT silently absorb, delete or
overwrite them. Dispositions are plan data and MUST be covered by the single approval, never by
separate approvals per file. An unreadable declaration or detected input MUST fail closed. Reports
MUST retain `migration_incomplete` until the declared work is resolved.

The reserved children `archive/`, `imported/`, `staging/`, and `journals/` are OPF control area.
Detection MUST NOT surface them as adopter content, an adoption option MUST NOT select them, and
an `[unmanaged]` declaration MUST NOT equal, contain, or lie within them. Adoption evidence MUST
be committed and immutable under `.working/imported/adoption/<run-id>/`; append-only outcome
events retain the receipt's history. Every adoption evidence inventory MUST carry the
section 4.2 `[adoption]` identity table, naming its own run id, its phase and the approved
plan's `plan_digest`. Transaction records live under `.working/journals/adoption/`.

After adoption, containment uses the receipt-bound `import_status` and the bounded treatment of
section 11: a plan-enumerated frozen retire, move or migrate source whose live bytes still match
its plan digest MUST be reported rather than failed until its retirement is recorded, whatever
the status, and a drifted source MUST fail at `required` exactly as section 11 defines. An
unregistered path outside that enumerated scope MUST fail containment at `required`. No source is
implicitly imported, and staging presence MUST NOT grant authority.

### 14.3 Migrating an existing release flow

An adopter with an existing single-source release flow (for example, a release-notes TOML
that generates a version file and a changelog) migrates by recording its releases in
`version.toml` as imported-flagged `[[release]]` rows (the optional `imported` flag of
section 6.1) and its per-release notes as published
per-release `[[summary]]` rows.
Pre-migration releases have no worklog entries: their spans MUST be empty and their summary digests
MUST be recorded as imported facts, flagged when the summary row is recorded by the optional
summary-row `imported` key of section 6.1 as resting on imported provenance rather than on a
witnessed release cut. A curator MAY later remove that flag under section 6.1. This is the
historical-release path: the ledger is not an
imported record type, its spans MUST NOT refer to `imported:WL` IDs, and import MUST NOT create a
separate version or changelog TOML file. Changelog prose MUST still come from the curator's act.

## 15. Genericization boundary

A conforming store's base-required schema vocabulary MUST NOT name a particular adopter,
operator, profile, internal system, endpoint, tier vocabulary, or command. A profile schema (for
example `[profiles.aiqt]`) legitimately names its owner, and a conforming store's own data
legitimately names an operator via `actor.id`; the neutrality constraint binds the base-required
vocabulary, not profile schemas or store data. `actor.kind` MUST carry only the
portable categories; identity detail lives in `actor.id` or extensions. `mode`,
`tier_assessment`, and `waiver` MUST ship structure only (evidence, assessor, outcome, validity,
scope, expiry) with adopter-supplied vocabularies. The location patterns of section 5.3 are
described generically; no pattern names a real repository, host account, or internal system. Import
and adoption provenance, including originals under `imported/` and retired files under `archive/`,
MUST stay inside the adopter's own repositories. `.aiqt/` is AIQT-owned material, not an
OPF state home; OPF operates without it. OPF MUST NOT read OPF artefacts from
former `.aiqt/` locations or touch unrelated AIQT material.
A no-follow existence probe of a former `.aiqt/` location, used only to refuse an operation, is
not a read of that material.
Experimental fields MUST ride registered
`x-<vendor>` tables only, within the limits of section 8.7.

The base standard's required schema vocabulary names no adopter, operator, or profile by
definition; a conforming store's own data legitimately may (an operator via `actor.id`, a profile
via a `[profiles.<name>]` table the adopter chose). AIQT appears in the standard's title and brand
as trademark and authorship attribution (the standard is authored and maintained by its lead
maintainer), which is attribution rather than a requirement dependency; AIQT is also one profile,
`[profiles.aiqt]`, cited only as the reference enforcement suite and a consumer. A profile
carries an adopter's own additional requirements without the base ever depending on them.

## 16. Conformance vocabulary and claims

Conformance is reported against the base and, separately, against each declared profile a tool
evaluated. A report speaks in `conformant_for_declared_scope`, `nonconformant`, `indeterminate`, or
`migration_incomplete`, each qualified by whether it concerns the OPFiles **base** or a named
**profile**. Every report names its scope, its exclusions, and its cannot-evaluate results. A
base-conformant store may declare a profile the reporting tool did not evaluate; the report names
that profile as unevaluated rather than implying whole-store coverage. An unqualified claim of
"OPFiles conformant" or "AIQT conformant" is never emitted, by tooling or by prose: a
conformance claim is a completeness claim over a declared set, and it enumerates that set, including
which profiles were and were not evaluated. A profile check's finding, such as one from
C-CARRIED-SHAPE or C-CARRIED-CLOSURE (section 9.3), makes a report `nonconformant` for that profile
alone and leaves the base result untouched; where the tool did not evaluate the profile, or
supports it only below the profile version that defines a check, that check is unevaluated, never
passed. Until validation tooling ships, a conformance claim is self-asserted and MUST say so.

### 16.1 Implementation conformance

An implementation is a tool or tool suite offered to create, write, or validate OPF stores. A
project that keeps its own store by hand, with its own checks over that store alone (section 1), is
not an implementation under this section. The base defines one implementation model and no
implementation conformance classes: a declared scope, exclusion, profile, or posture MUST NOT
waive a base requirement, and current-format requirements, the imported series, adoption, and the
section 8.6 authority firewall included, bind every implementation.

An implementation supports base `spec_version` 2.0.0 and homes generation 2, the only ones this
specification defines (sections 4.2 and 9.2), and the worklog storage generation it declares, and
initializes stores directly at them. The reference tooling
does not yet implement base 2.0.0: it still initializes and validates stores at base `1.2.0`, a
pre-release format this specification does not define, and it makes no claim of conformance to
this specification. The reference tooling's `opf doctor` grades a manifest declaring
`spec_version = "2.0.0"` with `homes = 2` under its 1.2.0 rules, so its VALID verdict on such a
store says nothing about conformance to this specification, and its `opf upgrade` and `opf record`
refuse such a store. The reference tooling defines no store upgrade: its `opf upgrade` refuses every
invocation with exit 2, reading and writing nothing.

An implementation MUST declare, in the documentation of each release and in every report its emitter
writes, its release identity and its supported `spec_version`, homes generation, and
worklog storage generation. Each release MUST ship that declaration as one file, the declaration
file. A runtime check is the step of the implementation that, in a run, reads the declaration and
gates that run's store operations, the emitter is the step of the implementation that writes the
conformance reports section 16 describes, never a store-file emitter such as the canonical
new-document emitter, and a documented run of the runtime check and the emitter need not resolve a
store. Whether a run authorized store operations is an observable of that run: it authorized them
exactly where it performed one, a write within a store that run resolved or to that store's lease,
as the checker observes the run's writes, and an authorization no performed operation shows is not
compared. The following writes, and no others, are not store operations under this section, for
the runtime-result comparison and the store part below alike: the claim of the single-writer lease
a command takes; its release; the `session_lease` record of that claim and of that release; and
the reconciliation and recovery writes sections 5.7, 8.8, 14.1, and 14.2 require to reconcile or
release such a lease. A run that stops as cannot-evaluate and writes nothing but what section 5.7
requires to end its own claim therefore performed no store operation. Every other write within a
store the run resolved is a store operation, the other writes sections 8.8, 14.1, and 14.2 require
included: a record publish performed where the expected runtime result is `cannot_evaluate`
remains one. A runtime check MUST read the declaration from the
copy of that file installed with the implementation (the installed copy) alone, never from the
documentation of the release or from any report. Each release MUST also carry, in the implementation
and apart from that file, the SHA-256 digest of that file's bytes as the release ships them (the
shipped-file digest), and the documentation of each release MUST state where the implementation
carries it. A release that carries no such digest, or whose documentation states no such place, does
not conform to this section, and a conformance claim MUST NOT be made for it. A runtime check MUST
compare the installed copy's bytes with the shipped-file digest before it reads any field, and an
installed copy that is absent or unreadable, or whose bytes differ from that digest, MUST yield
cannot-evaluate and MUST NOT authorize any store operation. That comparison detects an edit of the
installed copy alone; section 17 discloses that residual and the others these rules leave.

Every report the emitter of a release writes MUST carry the four parts compared in every report,
exactly these: the restatement of the declaration, the shipped-file digest the implementation
carries, the installed-copy digest, and the runtime result. The installed-copy digest is the SHA-256
digest of the installed copy's bytes that the runtime check read, or the token `not-read` where that
check read none because the installed copy is absent or unreadable, and a report MUST NOT carry
`not-read` with any runtime result other than `cannot_evaluate`. Each digest in a report MUST be
written as 64 lowercase hexadecimal digits, and the runtime result MUST be written as one of the
tokens of the three-valued gate_run verdict field (section 8.5): `cannot_evaluate` where that run's
runtime check yielded cannot-evaluate or another rule of this section made that run yield
cannot-evaluate, and otherwise `pass`
where it authorized store operations and `fail` where it did not. Section 8.5 fixes those tokens,
not their meaning here: under this section `pass` and `fail` read observably, over performed store
operations, so a documented run that resolves no store, and one whose only writes are the exempt
writes above, each authorized none and, where no rule yields cannot-evaluate, write `fail`. A
restatement differs from that file's declaration where it gives a different value for any field the
file carries, omits such a field, or states a field the file does not carry. The documentation of
each release MUST restate that file's declaration without differing from it. The expected report of
a release is fixed by the bytes the release ships alone: its restatement is the declaration of that
file as the release ships it, each of its digests equals the SHA-256 digest of that file's bytes as
the release ships them, and its runtime result is `cannot_evaluate` exactly where a rule of this
section makes those bytes yield cannot-evaluate, and otherwise `pass` or `fail`, between which this
section, as it now stands, sets no rule. A report
deviates from the expected report where any of the four compared parts is omitted, written in
another form, or holds another value; no other content of a report is compared. The runtime-result
part also deviates where its token disagrees with whether that run
authorized store operations, the performed operations the checker observes; this comparison reads
the run's writes, so the runtime result is the only part of a report compared with more than the
shipped bytes alone. A `pass` token beside no performed store operation, a `fail` token beside one,
and a `cannot_evaluate` token beside one each disagree that way, whatever the expected result, since
a run that yields cannot-evaluate authorizes no store operation. The behaviour-coupled comparisons
are exactly two, the token comparison above and the store part below, and they read only the writes
the checker observed: a run for which the checker cannot determine whether it observed every write
gives it no evidence under either comparison, so a result-part or store-part failure that only those
two comparisons of such runs could show MUST be reported as unresolved, never as established, a
residual section 17 discloses; the rest of the expected-report comparison reads such a run's
report as any other.

An execution environment is unaltered where it is a stock install of a platform and version within
what the documentation of the release names or, where that documentation names none, of the platform
the checker uses, as that platform's own installer leaves it, changed only as that documentation
directs and in this closed operational list, and in nothing else: the account name, administrative
privilege only where that documentation directs it, the working and temporary locations, and the
clock. Every default of that stock install that the documentation does not exclude, by directing
that it be changed or by naming a platform that lacks it, is part of an unaltered execution
environment, so meeting it is the release's, whichever platform and version within that naming a
checker uses. An attempt is the documented installation of a release, made by one checker in an
unaltered execution environment, from the bytes the release ships and, for each installed file the
release does not ship, from the source its documentation directs, followed by two successive
documented runs of the runtime check and the emitter over that installation. A reference run of a
release is a run of an attempt whose installed copy holds that file's bytes as the release ships
them and is readable when the run starts. The installation or the execution environment is altered
where any byte, file, or setting of either differs from what the stock install's defaults, the
changes the closed operational list above permits, the documented steps, the release's own code, and
code those steps install from a source the documentation of the release directs left it; the working
and temporary locations the checker chose are the checker's own, and what sits there alters neither,
the installation apart: the installed files, the installed copy included, and the files a documented
step or the release's own code wrote belong to the installation wherever they sit, those locations
included, so an edit of any of them alters the installation there as anywhere. An attempt whose
installation or execution environment anything else altered is not an attempt and establishes
nothing. A verdict under this section is decided from the checker's own observations, given its
detection of alterations (section 17), and an attempt whose eligibility under this rule the checker
cannot determine establishes nothing for that checker: a failure that only such attempts show MUST
be reported as unresolved, never as established.

A release MUST be available: every attempt MUST complete the documented installation and yield two
reference runs, so an installer that rewrites that file's bytes, by converting its line endings or
otherwise, an installed copy a documented run cannot read, an installation step an attempt cannot
complete, and a first run whose writes leave the second run with an installed copy that no longer
holds the shipped bytes are each a failure of this rule. A reference run of a release MUST NOT emit
a report that deviates from the expected report, and its runtime check MUST NOT authorize any store
operation where the expected runtime result is `cannot_evaluate`.

Only a checker's own attempts and reference runs are evidence under the two rules above: a report of
any other run or installation, altered or not, MUST NOT be presented as establishing or countering
conformance of any release, and whether a release conforms to this section is judged only from the
bytes the release ships, the implementation and the installer included, inspected, from the
documentation of the release, and from the checker's own attempts and reference runs. A failure of
either rule is shown for a checker where one of its own attempts or reference runs shows it, and
established for that checker where a second of its own attempts or reference runs, made on the same
platform and version, shows a failure of the same rule and, under the reference-run rule, in the
same part, the four compared parts of the report and the store part below each one part; attempts
and reference runs that show no failure, however many there are, never counter a
shown or established failure. The two rules above are the one path from attempts and reference runs
to a verdict: a breach of any requirement of this section that an attempt or a reference run shows
in what those rules compare, the four compared parts of a report, `not-read` beside another runtime
result, a run's cannot-evaluate and the store operations it performs, a restatement a report states,
and the store part below included, MUST be judged solely as a failure of the
availability rule or of the reference-run rule, shown and established only as those rules provide,
never as nonconformance on one showing; only what a checker inspects in the bytes the release ships
or reads in the documentation of the release decides a verdict under this section without that
procedure. Every requirement of this section that those rules do not compare is a requirement on the
bytes the release ships, on the documentation of the release, or on a checker's own conduct and
reporting: in particular, a requirement on the conduct of the implementation's commands outside what
the parts above read is a property of the bytes the release ships, and a breach of it is judged by
that inspection alone,
never by this procedure. A run that is no reference run and belongs to none of the checker's
attempts, a run of another command over a store the checker made and the Appendix E scratch-copy
probe over an edited installed copy included, is an observation of the implementation's behaviour,
never an inspection of the bytes the release ships or a reading of the documentation of the release:
however often it is repeated, it is no evidence under the two rules above, it shows and establishes
nothing there, and it decides no verdict under this section, on one showing or many, since only
those two rules, that inspection, and that reading decide; it can only direct the checker to what an
inspection of the bytes the release ships then finds, and section 17 discloses what every inspection
and such an observation rest on. An availability failure is shown by a failed attempt and
established by a second failed attempt of the same checker on the same platform and version; it has
no part, so the same-part condition does not apply to it. Under the reference-run rule the same-part
condition applies to every failure, a store operation performed where the expected runtime result is
`cannot_evaluate` included: that operation is a failure in a part of its own, the store part, shown
and
reproduced only by a run that performs such an operation, never by a deviating report. The showing
and the reproducing evidence MAY be any two of the
checker's own reference runs on the same platform and version, the two runs of one attempt included.
A checker that reports on a shown failure MUST report it as established or, where its own evidence
has shown it and not reproduced it, as unresolved, MUST name the platform, the version, and its own
attempts and reference runs behind that state, and MUST NOT report an unresolved failure, or the
absence of a shown one, as conformance of the release. A release for which a checker's own evidence
establishes a failure of either rule does not conform to this section, and that checker MUST NOT
make a conformance claim for it; a conformance claim under this section MUST name the attempts and
reference runs it rests on. Each such failure is a release nonconformance, never a runtime state of
the declaration: it MUST NOT be treated as making the declaration malformed or contradictory, and it
does not change what a runtime check of an installed copy yields.

An unreadable, malformed, or contradictory declaration MUST yield cannot-evaluate and MUST NOT
authorize any store operation. A declaration that is absent, or that omits its release identity,
its `spec_version`, its homes generation, or its worklog storage generation, is malformed: it MUST
yield cannot-evaluate and MUST NOT authorize any store operation. The rules on an absent,
unreadable, malformed, or contradictory declaration govern the file alone: a runtime check MUST
apply them to the installed copy as it stands, a check of the documentation or of the reports MUST
apply them to that file as the release ships it, and each check MUST NOT take any field from the
documentation of the release or from any report.

## 17. Residual coverage disclosures

The gates in this standard are strong where they are strong and say so where they are not:

- The freeze gate proves a published summary's bytes changed only through recorded re-publication;
  it cannot prove the prose is accurate or complete. Human curation (section 7.3) is that control.
- Range coverage proves every release is summarized exactly once; it cannot judge summary quality.
- The pipeline control ledger checks prove that every entry resolves, that each backlog item holds
  one place across lanes, and that each lane has one list; they cannot prove that the recorded
  order matches the adopter's standing priorities, or that work is actually taken in that order. A
  recorded override act binds through review like any other store change, never through
  authenticated authority, and the same-user tampering residual of section 14.1 covers the ledger
  as it covers every store file. Blocked-ness is derived at render time, so `PIPELINE.md` names a
  next entry that is current as of its last render; the byte drift gate reports a stale render, it
  does not prevent one.
- Pin stability is enforced by review, not by the doctor: the doctor reads one ledger snapshot, so
  it proves a pinned entry's act resolves, never that no entry crossed the pin between snapshots
  (section 10.6). Version-control history over the tracked store is the control.
- The rule that a milestone's row leaves the roadmap ledger in the change that records its
  discharging release (section 10.7) binds through review: for a milestone carrying
  `target_version`, the doctor reports a leftover row, because its `target_version` then names a
  released version, but it cannot prove the row left in the same change; for a milestone carrying
  `items` alone, review is the only control, because no leftover-row doctor check exists for it.
- The carried-low placement rule of section 10.6 is enforced by review, not by the doctor:
  severity and area are the adopter's judgement, and no check reads either for placement. Where the
  reference profile is declared, C-CARRIED-SHAPE checks the shape of a recorded area (section 9.3),
  never that it is the right area or that the finding is low severity.
- C-CARRIED-CLOSURE (section 9.3) proves that a ratified remediating backlog item has an effective
  `fixed` disposition on its carried finding, or on a successor of a superseded one; it cannot
  prove that the named change exists, that it merged, or that it fixed the finding, because a
  change is a host object outside the store. Maintainer ratification of `done` (section 8.4) and
  review are that control.
- Dispositions are append-only (section 9.3). `opf record carried` only appends, but the doctor
  reads one store snapshot, so it cannot see a disposition removed or rewritten between snapshots
  by a hand edit; review and version-control history over the tracked store are the control. The
  same holds for the rule that writing the `x-aiqt.carried` table changes no `status` or
  `updated_at`: `opf record carried` checks its own delta, but the doctor sees only the snapshot a
  hand edit leaves.
- The rule that a carried finding rotates only once closed (section 9.3) binds the rotation itself,
  and a tool that ignores the profile does not apply it; C-CARRIED-CLOSURE reports an archived
  carried finding that is not closed after the fact, never before the rotation lands, and the
  successor remedy of section 9.3 turns that finding into detail rather than clearing the archived
  record, which stays as rotated and stays superseded once it closes.
- `opf report` (section 10.8) reads the local store as found and is outside the section 5.7
  reconciliation, so a report run against a store that is behind its sync target lists stale state.
- `CARRIED.md` (section 10.8) lists the open carried findings as of its last render, like any
  composed view; the byte drift gate reports a stale render, it does not prevent one. A tool that
  does not support the reference profile neither renders nor drift-gates the view (section 10.2).
- A path glob can go stale when product files are renamed or moved, and the product tree is not
  store data, so no check proves that a glob matches any existing path; C-CARRIED-SHAPE proves
  only that each glob is in the dialect and that each component reference resolves. The component
  map (section 9.3) narrows the upkeep to one map line per component.
- `opf report carried` (section 10.8) is as complete as its inputs: it cannot detect a changed path
  missing from `--changed` or a merged change missing from `--merged`, a changed path holding a C0
  control character or DEL makes the run exit 2 rather than report it, and its aging reads worklog
  entries that link a finding, so a disposition recorded without such an entry does not reset the
  finding's age. The report lists candidates only, and whether an aged finding reaches a lane is the
  lanes standard's matter, which no check reads.
- The section 2.1 rule that a planning surface describes itself only within the fixed vocabulary
  is enforced by review, not by the doctor: no doctor check reads a surface's self-description,
  for declared views and command surfaces alike.
- The `ROADMAP.md` preamble fact gate proves that every `v`-prefixed version token in the preamble
  resolves to a released version or a declared target; it cannot prove the preamble's direction is
  accurate or complete. Human curation through ordinary review (section 10.7) is that control for
  the preamble, as the curation flow (section 7.3) is for the changelog.
- The unreleased worklog tail is mutable until release: an entry there MAY be corrected in place, a
  guarantee that rests on review and version-control history rather than machine enforcement; machine
  freezing and immutability begin at release cut.
- Adoption and import run with C-EVIDENCE-ENUM, which re-enumerates their control areas
  (`.working/imported/<kind>/<run-id>/`, `.working/archive/adoption/<run-id>/` and
  `.working/archive/moved/`) on every doctor run, and the section 14.1 completion checks still
  verify their evidence digests themselves when they run; C-EVIDENCE-ENUM asserts membership, not
  authenticated actor history; deleting a whole bundle (inventory and payload together) is
  outside its local snapshot check (section 4.2). Version-control history over the tracked store
  is the control, and C-IMPORTED-PROVENANCE still re-verifies every preserved original an imported
  record references.
- Journals are machine-local (section 4.2), and the doctor reads the ID reservations under
  `journals/<kind>/allocations/` for the section 8.2 counter checks, so a clone, which holds none,
  can grade those checks differently from the original store: where a reservation covers a number
  that no published record carries, the original store's doctor treats that number as issued and a
  clone's doctor reports it missing. Adoption admission and recorded retirement, which the doctor
  decides from committed evidence alone, grade the same in both (section 4.2).
- Store resolution fails closed on a pointer that does not resolve and on zero or multiple
  manifests at the target; it cannot detect a second store that no pointer names, placed somewhere
  the tooling was never aimed.
- The tracked-store check verifies the resolved store is under version control, not ignored, and
  that the pointer, the manifest's recorded sync target, and the actual remote agree; it cannot
  verify the backup, access, or hosting discipline of the repository that tracks the store. The
  local-only pattern in particular places durability wholly on the adopter's own backup, which is
  why choosing it SHOULD be a recorded decision (section 5.3).
- The single-writer lease has a propagation window: between a lease being taken and its becoming
  observable at the sync target, two systems can both begin. The consistency contract's divergence
  check is the overlapping control that catches that collision after the fact; the two layers
  together, not the lease alone, are the guarantee (section 5.7).
- The dead-run lease release of sections 5.7 and 8.8 proves holder death by a process probe on the
  probing host, serialized by a lock on the lease's directory so concurrent recoveries whose locks
  one kernel arbitrates never race it: a live holder in another PID namespace that shares the store
  and this hostname can read as dead there and lose its lease, and a dead holder whose pid a live
  process reused reads as possibly-live and keeps refusing until the operator reconciles. The probe
  errs toward refusal, and the journal-lock owner model shares the same residual where no process
  start time is recorded. That serialization holds only within one kernel: where the store sits on
  NFS or another filesystem whose flock is local to each client kernel, two hosts that share the
  store under one hostname can both take the lock and race the release, and where flock is
  unsupported or fails, every dead-run release refuses, naming the lock failure, and stays the
  operator's reconciliation step.
- A host provider's create and auth conveniences call the external API of the host the target
  names. The egress bound is that named host and nothing else; the standard cannot vouch for the
  host's own behaviour beyond that bound.
- Public deliverables reach the product repository through `opf render` under the product
  repository's normal review flow (section 5.8); the quality of that review flow is the adopter's
  own discipline, which this standard requires to exist but does not itself gate.
- A base-only tool does not evaluate profiles: a store could satisfy the base and violate a profile
  it declares, and a base-only tool would not detect it. This is by design (profiles are additive
  and a base tool is out of their scope), and it is the reason a conformance report always names
  which profiles it did and did not evaluate. Fail-safe-for-unknown-profiles is scoped to a tool
  that does not cover the profile; a profile-aware tool MUST fail closed on its own profile.
- The base discovery token `opf` is a single exact string carried in every adopter manifest.
  A mistyped or altered token makes the store undiscoverable, which resolves to cannot-evaluate
  (fail-closed), never to a silent empty store. The token is stable, and this
  specification gives a store-breaking rename no path: every later base-schema version bump stays
  additive and keeps every manifest discoverable through the exact base discovery token `opf`
  (sections 4.5 and 9.2), so no bump this specification permits renames the token.
- The section 16.1 runtime check compares the installed copy of a release's declaration file with
  the shipped-file digest the implementation carries, so it detects an edit of that copy alone,
  which yields cannot-evaluate; it does not detect a co-edit that changes both the installed copy
  and the digest the implementation carries to match it, or one that changes the installed copy
  together with the implementation's comparison code so that the comparison no longer refuses that
  copy, and an anchor outside the installation, such as a signature over that file that the
  implementation verifies, is the stronger option only against an edit that does not also change the
  implementation's verification key or its anchor check; section 16.1 does not require one. Whether
  a release's runtime check compares the installed copy's bytes with the digest the implementation
  carries at all, and whether that digest sits at the place the documentation states, are
  established only by an inspection of the implementation, never by a reference run: every reference
  run's installed copy holds the shipped bytes, over which a runtime check that skips that
  comparison and one that makes it can yield the same report. Section 16.1 verdicts are
  observer-local: each rests on a checker's own knowledge of its stock baseline and of what it
  changed, so an alteration the checker did not detect, such as an organization-wide package-manager
  configuration file taken for part of the stock install, can mislead that checker. Another checker
  contests a claim only with its own evidence: under the section 16.1 availability and reference-run
  rules, with its own attempts and reference runs alone, and otherwise with what it finds by
  inspecting the bytes the release ships or by reading the documentation of the release, such as
  that the release carries no shipped-file digest or that its documentation states no place for it.
  Honest checkers can reach different verdicts on stock installs of different platforms or versions,
  each within what the documentation of the release names or, where that documentation names none,
  the platform the checker in question uses, since section 16.1 makes every default of each such
  install that the documentation does not exclude, by directing that it be changed or by naming a
  platform that lacks it, the release's to meet. They can also reach different verdicts on one
  platform and version, where the changes the section 16.1 closed operational list permits, such as
  the account name or the clock, differ between their attempts, or where one checker's own attempts
  and reference runs show a failure of one rule twice, under the reference-run rule in the same part
  both times, and another checker's show it once or never. The same residual covers the section 16.1
  rule that an attempt whose installation or execution environment differs from what the stock
  install's defaults, the changes the closed operational list permits, the documented steps, the
  release's own code, and code those steps install from a source the documentation of the release
  directs left it is not an attempt and establishes nothing: only a checker that detects the
  alteration can know to set that attempt aside, and section 16.1 has a checker that cannot
  determine an attempt's eligibility report what only such attempts show as unresolved, never
  established. It covers whether a checker observed every write of a run the same way: the
  section 16.1 runtime-result token comparison and store part read the writes the checker observed,
  so a write a checker missed could make an honest token read as disagreeing, or hide a disagreeing
  token or a store-part failure that the run's writes show, and a checker that cannot determine
  whether it observed every write of a run reports what only the behaviour-coupled comparisons of
  such runs show as unresolved, never established. The working and temporary locations a checker
  chose are its own, and what sits there alters nothing, the installation apart: the installed
  files, the installed copy included, and the files a documented step or the release's own code
  wrote stay part of the installation wherever they sit, so the Appendix E scratch-copy probe, which
  edits an installed copy, alters the installation it probes. That probe, like every run outside the
  checker's own attempts and reference runs, is an observation of the implementation's behaviour,
  never an attempt, a reference run, or an inspection of the bytes the release ships: it establishes
  nothing under the section 16.1 rules however often it is repeated, it decides no verdict of its
  own, and it informs only the section 16.1 inspection of the implementation, which rests on the
  same observer-local attribution. A requirement of section 16.1 on the conduct of the
  implementation's commands that its two rules do not compare is judged only by that inspection, so
  a conduct breach a
  checker cannot attribute to the bytes the release ships decides nothing for that checker, and one
  it can attribute is decided by what that inspection finds in those bytes, never by the observed
  run itself on any number of showings. A failure that a checker cannot show twice in its own
  attempts and reference runs, on the same platform and version and, under the reference-run rule,
  in the same part, stays unresolved, however many other checkers each show it once, and an
  unresolved failure neither establishes nor counters any conformance or nonconformance of the
  release. Where the documentation of a release directs that a file the release does not ship be
  installed and does not pin its bytes, attempts made at different times can differ as the bytes the
  directed source serves differ, a residual of the release's own documentation. Appendix E gives
  informative guidance for checking release conformance: a record of attempts, redaction of secrets,
  sharing and repetition, corroboration across checkers, a consistency probe over third-party
  reports, scratch-copy probes of the byte comparison, and an optional content-addressed reference
  environment.

## Appendix A: record envelope example

Synthetic data throughout; no real project, person, or record.

```toml
[[record]]
id = "FN-7"
type = "finding"
status = "fixed/proposed"
title = "Generated view drifted from its source index"
created_at = "2026-08-12T09:14:02Z"
updated_at = "2026-08-12T11:40:55Z"
actor = { kind = "assistant" }
summary = "BACKLOG.md no longer matched backlog_item.index.toml after a hand edit."
severity = "minor"
links = [ { rel = "remediates", id = "BI-42" } ]
refs = [ { kind = "path", locator = ".working/BACKLOG.md", note = "drifted bytes" } ]
```

A carried low finding under the reference profile (section 9.3), routed to its remediating backlog
item and deferred once by a change that touched its area:

```toml
[[record]]
id = "FN-12"
type = "finding"
status = "routed"
title = "Generated header omits the source-set digest on empty sources"
created_at = "2026-09-03T08:21:10Z"
updated_at = "2026-09-03T08:30:44Z"
actor = { kind = "maintainer" }
links = [ { rel = "remediates", id = "BI-57" } ]
refs = [ { kind = "path", locator = "src/render/header.py", note = "empty-source branch" } ]

[record.x-aiqt.carried]
area = ["component:render", "src/digest/**"]
dispositions = [
  { change = "https://example.invalid/changes/311", outcome = "deferred", reason = "Header layout change; the empty-source branch needs its own test first" },
]
```

## Appendix B: version.toml example

```toml
schema = 1

[[release]]
version = "1.2.3"
date = "2026-06-14T00:00:00Z"
worklog_span = ["WL-1", "WL-88"]
coverage_digest = "sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"

[[release]]
version = "1.3.0"
date = "2026-08-30T00:00:00Z"
worklog_span = ["WL-89", "WL-131"]
coverage_digest = "sha256:fcde2b2edba56bf408601fb721fe9b5c338d10ee429ea04fae5511b68fbf8fb9"

[[summary]]
covers = "unreleased"
status = "working"

[[summary]]
covers = "1.3.0"
status = "superseded"
digest = "sha256:a3f5c1de9b6a44708d622de1f9f26bbee2ccc0be9cbb1c19b599162eeb0ed4f1"
superseded_by = "1.2.3..1.3.0"

[[summary]]
covers = "1.2.3"
status = "superseded"
digest = "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
superseded_by = "1.2.3..1.3.0"

[[summary]]
covers = "1.2.3..1.3.0"
status = "published"
digest = "sha256:60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752"
```

## Appendix C: worklog.toml example

```toml
schema = 1

[[entry]]
id = "WL-131"
date = "2026-08-29T16:22:41Z"
actor = { kind = "maintainer" }
kind = "fixed"
summary = "Close the view generator's stale-output gap on renamed types"
links = [ { rel = "resolves", id = "BI-42" }, { rel = "remediates", id = "FN-7" } ]

[[entry]]
id = "WL-132"
date = "2026-09-02T10:05:19Z"
actor = { kind = "assistant" }
kind = "docs"
summary = "Correct the block-join description in the composed-view docs (corrects WL-90)"
links = [ { rel = "corrects", id = "WL-90" } ]
```

## Appendix D: CHANGELOG.md entry examples

```markdown
## unreleased

- In progress: per-record layout documentation.

## 1.2.3..1.3.0 (2026-06-14 to 2026-08-30)

The baseline store through the view-generator hardening: the typed store, the nine
baseline record types, deterministic views with a drift gate, and the first import
tooling; then renamed types can no longer leave a stale generated view behind, and
composed views now surface records awaiting ratification.
```

## Appendix E: checking release conformance (informative)

This appendix is informative: it recommends practice for checkers and releases working under
section 16.1, it adds no requirement, and section 16.1 alone decides what a failure, a verdict, or a
conformance claim is.

- Keep a record of each attempt. A useful record holds the platform and version the documentation
  names, if any, and the platform and version used; the account and whether it held administrative
  privilege; the umask, locale, and character encoding; every environment variable set; the path and
  SHA-256 digest of each interpreter, version-control, and package-manager configuration file a step
  read; each package index or other source a step used; the documented steps followed and the
  commands run; the interpreter and tool versions; the store a run read, with the SHA-256 digest of
  each of its files; the list of installed files, with the SHA-256 digest of each; and each setting
  or component the checker knows it changed relative to the stock install.
- Redact secrets everywhere in a record: a credential, a token, a password, or a private key, in an
  environment variable's value, in a source's address, or in a command argument, is written as its
  name and a redaction marker, never as its value.
- Share records so that another checker can repeat an attempt on its own stock install; keeping the
  bytes each source served, and replaying them, makes a repetition closer. A shared record informs
  another checker's work and never substitutes for that checker's own attempts and reference runs.
- Corroborate across checkers: where two checkers each show the same failure once, on the same
  platform and version, that agreement is a strong reason to keep attempting, though under
  section 16.1 the failure stays unresolved for each checker until its own attempts or reference
  runs show it twice, on the same platform and version and, under the reference-run rule, in the
  same part.
- A report of a third-party installation can be probed for consistency. Where its installed-copy
  digest is 64 lowercase hexadecimal digits other than the SHA-256 digest of the shipped file's
  bytes and its runtime result is other than `cannot_evaluate`, the report is inconsistent with a
  run whose runtime check compared the installed copy's bytes with that digest before reading any
  field and, on finding them different, yielded cannot-evaluate as section 16.1 requires, whose
  emitter reported that run truthfully, and whose report no one altered after the emitter wrote it.
  It does not show that no comparison ran: a co-edit that also changed the digest the implementation
  carries (section 17), a comparison that is skipped, defective, or made without refusing a
  mismatch, an emitter that misreports, and a report altered after it was written each explain it,
  and the report does not tell which. It establishes nothing under section 16.1.
- Probe the byte comparison on a scratch copy: install the release somewhere disposable, edit the
  installed copy, and observe whether the runtime check yields cannot-evaluate and authorizes no
  store operation. This observes the implementation's behaviour over bytes the release did not ship;
  section 17 discloses that no reference run can show whether that comparison is made. An edited
  installed copy is an altered installation under section 16.1 wherever it sits, a disposable
  location included, so a probe run is no attempt and no reference run and, however often it is
  repeated, establishes nothing under the section 16.1 availability and reference-run rules. It is
  an observation, never an inspection of the bytes the release ships, and it decides no verdict: it
  can only direct the checker to what an inspection of those bytes then finds.
- A content-addressed reference environment, such as a container image named by digest, makes a
  checker's stock baseline reproducible and repetitions cheaper; section 16.1 does not require one,
  and a release's documentation can name one as the platform it documents.

---
