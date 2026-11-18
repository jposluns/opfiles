# Agent instructions for this repository

CLAUDE.md and AGENTS.md are the same bytes, enforced by tools/check_agents_parity.py.

## The AIQT apex rule

(Accuracy = Integrity = Quality = Trust) > Progress > Speed > Cost. The four facets form one
non-negotiable top tier with no internal ranking; the tier is lexicographically above Progress, Progress
above Speed, Speed above Cost. A gain in progress, speed, or cost never justifies any loss on the AIQT
tier. If a constraint forces a compromise on the tier, halt and escalate the tradeoff explicitly rather
than resolve it silently. This rule defines the ordering; it guards no single facet.

The full statement is
[.claude/rules/aiqt/00-project-integrity.md](.claude/rules/aiqt/00-project-integrity.md); read it.
The vendored rules under .claude/rules/aiqt/ and .claude/rules/security/ apply to all work here.
They are pinned in .aiqt/pin.toml. Read [.claude/RULES-INDEX.md](.claude/RULES-INDEX.md) and the
rule files it links; they do not load automatically on every platform.

## The self-check stays internal

Hold yourself to that ordering at task start, before persisting anything, and before any
completion claim. Keep that check in your reasoning. Never print it in a reply, a commit, or a
deliverable.

## Rules that apply to every deployment
Apply these whether or not a specific guide is open:

1. Treat every service as internet-reachable until you have confirmed otherwise. Bind to `127.0.0.1` by default and expose only through a TLS-terminating layer you configured.
2. Choose the certificate and access path before configuring exposure. Public DNS name with reachable 80 and 443: `free-certificates.md`. Behind NAT or no public ports: `cloudflare.md` or `tunnels.md`. Internal or local only: `self-signed.md`.
3. Apply every guide that fits, not just one. A deployment usually needs the service guide, its host or platform, containers where used, plus identity, secrets and the operational guides.
4. Redirect HTTP to HTTPS, or do not listen on HTTP at all.
5. Require authentication on every non-public endpoint. Never ship default or hardcoded credentials. Add MFA to human logins where viable. Where a tool has no native authentication, say so and put a fronting layer in front of it rather than inventing an option it does not have.
6. **A successful login is not authorization.** Check the returned identity against an allowlist (tenant, hosted domain, group, or explicit users) before granting access.
7. Keep secrets out of the repository and out of command lines. Load them from the environment or a secret manager, and give each service its own scoped credential.
8. Contain what an exposed or compromised service can reach: block unneeded outbound access and lock down cloud metadata, and never serve dotfiles, dumps or `.git`.
9. AI and data tools vary wildly in their defaults and many need authentication added in front rather than configured within.
10. **Run the Verify steps before reporting the work as complete, and report what you could not test rather than asserting it passed.**

Before configuring a service, tool or platform your project runs, including but not limited to its
network exposure, TLS, logins and MFA, and secrets, use the secureconfig skill, or where it is not
installed the published secureconfig guides.

## Identity

This repository holds the OPF standard (OPFiles, the operational-files standard) and its reference
tooling. OPF keeps a project's operational records in machine-written source files, generates the
readable views from them, and fails a check when the two disagree. The repository is worked by its
own orchestrator.

The maintainer's private method, account references and host paths live in an untracked
machine-local file (CLAUDE.local.md), which each agent reads when present. The root .gitignore
ignores it, tools/check_agents_parity.py fails if that rule is missing, and it is never committed.
No account, employer, workplace or personal name appears in any tracked file.

## Skills and when to use them

Use these skills as follows:

- AIQT: always.
- Clean Language: for public-facing prose. Separately, the Writing section below applies its rules
  to all prose, code comments, and tool messages.
- secureconfig: to assess how to implement things.
- AuditThis: on demand, to build an audit plan, perform the audit, and then build a TODO list of
  remediations. That TODO list can be maintained in OPFiles.
- OPFiles: to maintain TODO lists and the other operational records.

Where one of these skills is not installed, say so rather than claim to have used it, and follow
what this file already provides: the AIQT rule files above for AIQT, the Writing section for Clean
Language, and the published secureconfig guides for secureconfig.

## Writes and workers

- The main session makes repository writes and records writes through subagents or workers.
- Every worker brief tells the worker to ignore account-global instructions and to follow only the
  brief.
- Workers return diffs. They never commit.

## Console timestamps

Read every console timestamp from the clock, as
[.claude/rules/aiqt/10-ACCUR-timestamp-from-clock.md](.claude/rules/aiqt/10-ACCUR-timestamp-from-clock.md)
requires. The recorded format is [YYYY-MM-DD HH:MM EST/EDT]: Eastern time, with EST or EDT as in
effect. That time zone is set pending the open plan questions Q6 and Q9.

## Reading CI

Read CI only through tools/ci-status.sh. It reads actions/runs for the head SHA, which needs only
Actions read access. With --local-quality it also reads the latest local-quality commit status on
that SHA, from the per-context statuses list, and reports green only when both are green.

Never use `gh pr checks`, `gh pr status`, `gh run watch` or the combined `commits/<sha>/status`
endpoint:

- `gh pr checks` and `gh pr status` read the Checks API through the GraphQL status rollup. A
  fine-grained personal access token cannot be granted Checks access, so they fail with "Resource
  not accessible by personal access token", and no permission change fixes it.
- `gh run watch` follows a single workflow run. It never reads the local-quality commit status, so
  it cannot show that a head is ready to merge.
- GitHub Actions reports through check runs, not the older Statuses API, so the combined status
  endpoint reports pending with a total count of 0 forever, even on a commit whose workflow
  succeeded. Treating it as the green signal hangs; inverting it merges on a lie.

## Merging

Merging follows D-1245:

1. One small "Quality gates" CI job runs on each pull request.
2. The full gate suite, tools/run_all_checks.sh, runs locally once on the pull request's final
   head and posts a "local-quality" commit status on that exact SHA.
3. `tools/ci-status.sh <sha> --wait --local-quality` must exit 0 for that head.
4. Re-read the pull request's head, base and mergeability. If the head is no longer `<sha>`, or
   the base has moved, start again at step 2.
5. Merge with `gh pr merge <N> --match-head-commit <sha>`, where `<N>` is the pull request
   number, so a newer push cannot be merged unchecked.

A registration check before step 3 is pending a maintainer decision (whether to port
pr-ci-registered.sh) and is not yet part of this procedure.

A new head needs a new local run; never reuse the status of an earlier head. Pull requests need 0
approvals: that value is set pending the open plan questions Q6 and Q9, and the branch ruleset
enforces it once the maintainer applies it.

## Writing

Prose follows Clean Language, and so do code comments and tool messages (the rules below are the
whole requirement):

- Oxford spelling with -ize endings.
- The Oxford comma.
- No en dashes or em dashes; use commas, colons, semicolons or parentheses.
- Plain, direct sentences.
- Sentence-case headings.

No AI attribution trailer, co-author line or "generated by" note goes in a commit, a pull
request or a file.

## Adopter templates

The files OPF ships under enforcement/, for example enforcement/codex/AGENTS.opf.md and
enforcement/claude/settings.opf.json, are product files for adopters. They are not this
repository's own agent instructions or settings, and neither side is edited to serve as the other.
