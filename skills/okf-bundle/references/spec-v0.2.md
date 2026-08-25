# OKF v0.2: the format

Condensed from the specification. The authority is
https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md.
Fetch it when a detail matters, and never answer a conformance question from
memory. This file exists so routine authoring needs no fetch.

## Contents

- [Bundle structure](#bundle-structure)
- [Concept documents](#concept-documents)
- [Provenance, trust, lifecycle](#provenance-trust-lifecycle)
- [Actor convention](#actor-convention)
- [Links and paths](#links-and-paths)
- [Reserved files](#reserved-files)
- [Attested Computation](#attested-computation)
- [Conformance](#conformance)

## Bundle structure

A directory of markdown, distributed as a git repository or a tarball. Two
filenames are **reserved** and are not concepts: `index.md` (a directory
listing) and `log.md` (an update history). Every other `.md` file is a concept.

A `references/` subdirectory is a convention for material a concept points at,
not a requirement.

## Concept documents

Every concept carries YAML frontmatter with a non-empty `type`.

| Field | Status | Notes |
|---|---|---|
| `type` | REQUIRED | Producer-chosen, no central registry. Pick something descriptive: `API Contract`, `Data Model`, `Playbook`. `Concept` is the spec's own generic word and routes nothing. |
| `title` | Recommended | |
| `description` | Recommended | One sentence; index files reuse it. |
| `resource` | Recommended | URI of the underlying asset the concept describes. |
| `tags` | Recommended | |

Timestamps are ISO 8601 with an explicit UTC offset: `2026-06-30T14:00:00Z`.

## Provenance, trust, lifecycle

All optional. Absence carries meaning and is never a rejection.

**`sources`** is a list, or a bare mapping treated as a list of one.

- `resource`: REQUIRED per entry. An absolute URL, a bundle-relative path, a
  path into `references/`, or a scope descriptor a consumer cannot follow (for
  example `all queries in project X`).
- `id`: optional, but SHOULD be present when the body cites the source. It is
  the footnote label used for per-claim attribution.
- `title`, `author`, `usage_count`, `last_modified`: optional credibility
  signals. `usage_window: { from, to }` is written once as a sibling of
  `sources` and frames every `usage_count`.

**`generated: { by, at }`** records who wrote the concept and when. `by` follows the
actor convention.

**`verified`** is a mapping or a list of `{ by, at }`. Consumers MUST treat a
bare mapping as a one-element list.

**Trust tiers derive ONLY from `verified`:**

| `verified` | Tier |
|---|---|
| absent | Unverified |
| present, no `human:` actor | Machine-confirmed |
| present with a `human:<id>` actor | Human-reviewed |

`generated.by` confers no tier, whoever wrote it. The spec says nothing about
whether the verifier may be the author. That is a local decision, and
`conventions.md` argues for requiring independence.

**`status`** is `draft`, `stable` or `deprecated`. Absent means `stable`.

**`stale_after`** is an absolute instant after which the concept should be
re-read. The spec only defines the field; acting on it is the producer's job.

## Actor convention

| Form | For |
|---|---|
| `<producer>/<version>` | tools, e.g. `reference_agent/gemini-2.5-pro` |
| `human:<id>` | people, e.g. `human:dk@kyndryl.com` |
| `process:<id>` | automation |

The id after `human:` is unconstrained; an email is fine.

## Links and paths

Two forms are legal for `resource`, `sources[].resource`, `executor.resource`
and body links:

- **Bundle-relative**, starting with `/`, resolved from the bundle root. The
  spec *recommends* this form.
- **Relative**, e.g. `../computations/revenue.md`.

The spec sets no floor, so a relative path may leave the bundle. That breaks
tarball distribution, a deliberate trade. See `conventions.md`.

Per-claim attribution uses markdown footnotes whose labels match `sources[].id`.

## Reserved files

**`index.md`** is a directory listing, no frontmatter, with ONE exception: the
bundle-root `index.md` MAY carry `okf_version: "0.2"` and nothing else. Entries
are `* [Title](path) - description`, grouped under headings.

**`log.md`** holds date-grouped entries, newest first:

```markdown
# Update Log

## 2026-05-22
* **Update**: Added a reference for [Customer Metrics](/tables/customer-metrics.md).

## 2026-05-15
* **Initialization**: Created foundational directory structure.
```

Date headings **MUST** use ISO 8601 `YYYY-MM-DD`. That is the only hard
requirement in the log section; newest-first ordering and the leading bold word
are described as convention.

## Attested Computation

`type: Attested Computation` adds:

| Field | Status | Notes |
|---|---|---|
| `runtime` | REQUIRED | Producer-chosen; there is no registry. It fixes what `parameters` mean and how executor and attester read the computation. |
| `parameters` | Optional | List of `{ name, type, required }`, the typed holes an agent may fill. |
| `computation` | Optional | Path to a file holding the computation. Absent means the body's `# Computation` fenced block IS the computation. |
| `executor` | Optional | `{ resource, receipt }`. `resource` names run instructions; `receipt` lists the fields a run must return, the evidence an attester inspects. |
| `attester` | Optional | `{ resource }` naming deterministic, non-LLM code that takes a receipt and returns a verdict. |

**The binding rule that is easy to break:** an agent may only supply *values*
for the declared `parameters`, and **MUST NOT** author or edit the computation.
So every hole in the computation body must correspond to a declared parameter,
or the document cannot be executed at all.

Conventional body headings with defined meaning: `# Schema`, `# Examples`,
`# Computation`.

## Conformance

A bundle is conformant if:

1. Every non-reserved `.md` has a parseable YAML frontmatter block.
2. Every frontmatter block has a non-empty `type`.
3. Reserved filenames follow their structure when present.

Consumers **MUST NOT** reject a bundle for: missing optional fields, unknown
`type` values, unknown extra keys, broken cross-links, or a missing `index.md`.

That constrains *consumers*. It does not stop an author from checking their own
bundle harder, which is the entire basis for the house half of the gate.
