---
name: okf-bundle
description: Build a versioned Open Knowledge Format (OKF) v0.2 knowledge bundle for a codebase - markdown with YAML frontmatter, plus a CI gate that fails when the documents drift from the code they describe. Use when the user asks to implement OKF, create an okf bundle, add a knowledge/ directory, put project knowledge under version control, document a service so a fresh clone carries its context, model live resources or API operations as Attested Computations, or write documentation that cannot silently rot. Also use when validating, extending or porting an existing OKF bundle or its conformance gate.
---

# OKF bundles

OKF v0.2 is a **file format**, not a service: a directory of markdown files with
YAML frontmatter. No runtime, no endpoint, no build step. The upstream tooling is
Python-only and none of it is needed.

The value is not the format. It is that a bundle can be **mechanically checked
against the code it describes**, so documentation fails the build instead of
quietly going stale. Build the gate first; a bundle without one is just a folder
of markdown that will be wrong in six months.

## Workflow

1. **Scope it with the user.** Confirm four things before writing anything: which
   codebase, who reads it (devs in git is the usual answer, and it decides link
   style), whether operations get modeled as Attested Computations, and who the
   author actor is. Never make yourself the author - see `references/conventions.md`.

2. **Find what is NOT already in the repo.** This is the whole justification.
   Check what a fresh clone actually receives:
   ```sh
   git ls-files '*.md' | head -50
   cat ~/.gitignore .gitignore 2>/dev/null | grep -vE '^\s*(#|$)'
   ```
   Design docs and runbooks are routinely gitignored or live only on one machine.
   That content gets **rewritten into concept bodies**. Never cite a file the
   reader will not have.

3. **Scaffold and wire the gate before writing prose.**
   ```sh
   scripts/okf_validate.py --init knowledge
   scripts/okf_validate.py knowledge
   ```
   Add it to CI now, so every later file is born validated. For a Go, Node or
   Rust project that would rather keep the gate in its own test suite, port the
   rules - read `references/gate-traps.md` first, it is the list of ways a gate
   goes green while checking nothing.

4. **Write concepts from the code, not from existing docs.** Read the source and
   describe what it does. README files and generated specs are usually stale;
   treating one as a source propagates its errors into the bundle. Details and
   the per-file content plan: `references/authoring.md`.

5. **Pin every copied literal.** Any block that copies names out of the code -
   collections, routes, error codes, tuning constants - gets a marker naming its
   origin:
   ```markdown
   <!-- house:from ../../internal/store/mongo.go -->
   | Collection | Holds |
   |---|---|
   | `hosts` | Machines, synced or entered by hand. |
   ```
   Every backticked literal in the block must still exist in that file. This is
   what turns a rename in the code into a failing build.

6. **Capture live evidence for anything the repo cannot prove.** A contract owned
   by another service is a snapshot; commit the raw capture next to the documents
   that cite it so the snapshot is diffable. Without evidence, do not write the
   document - an invented contract is worse than an absent one.

7. **Verify by breaking it.** Non-negotiable, and covered below.

8. **Review in two passes.** Correct against the spec, against the code, and
   against the gate; then re-check the corrections. Expect roughly one new error
   per five fixed, so a single pass is not enough.

## Verify by breaking it

A green gate proves nothing until you watch it fail. Every silent-skip bug found
while building this skill was found this way and by no other means - including
one in the self-test itself, where opening a file for writing truncated it before
the mutation could read it, turning every mutation into a no-op while the run
still reported "caught".

```sh
scripts/okf_validate.py --self-test
```

This scaffolds a bundle, applies 18 breakages and 6 pieces of legitimate-but-
tricky markdown, and reports any breakage that slipped through or any valid
construct that tripped the gate. Run it after any change to the validator.

Then break the **real** bundle a few ways by hand and confirm each is reported:
rename a literal inside a `house:from` block, point a link at a missing file,
put a date in the past in `stale_after`.

Both failure directions matter equally. A gate that misses a defect is useless;
a gate that fails on correct input gets deleted, and the most common cause is a
document that legitimately contains example markdown.

## The validator

`scripts/okf_validate.py` is language-agnostic. It needs Python 3 and
**PyYAML** (`pip install pyyaml`), and exits with that message if it is
missing. The dependency is deliberate: hand-rolling a YAML parser for
`sources[]` and `parameters[]` would be exactly the kind of helper that
quietly produces nothing and lets every check pass — see
`references/gate-traps.md`.

```sh
scripts/okf_validate.py knowledge                 # both halves
scripts/okf_validate.py knowledge --conformance-only
scripts/okf_validate.py knowledge --no-freshness  # only with evidence, never by default
scripts/okf_validate.py --init knowledge          # scaffold
scripts/okf_validate.py --self-test               # prove it still bites
```

It reports two halves separately, and the split is deliberate:

- **CONFORMANCE** - what the spec requires of a producer. It never rejects a
  bundle for what the spec tells *consumers* to tolerate: unknown types, unknown
  keys, absent optional fields.
- **HOUSE** - stricter local rules. A producer may check its own bundle harder
  than a consumer must; that is exactly what makes it a gate rather than a
  parser. Every house rule states what it does not prove.

## Reference material

- `references/spec-v0.2.md` - the format: frontmatter families, reserved files,
  Attested Computation, trust tiers, link rules. Read before writing frontmatter.
- `references/conventions.md` - the local rules that make a bundle hold up, each
  with its reason. Read at step 1; the actor and freshness rules are decisions
  the user must agree to.
- `references/authoring.md` - what to put in each document, the evidence rules,
  and a worked Attested Computation. Read at step 4.
- `references/gate-traps.md` - how a gate goes green while checking nothing. Read
  before porting the validator to another language or adding a rule.

## What not to do

- **Do not sign your own work.** Leave `verified` absent. A document is Unverified
  until a second person reads it, and the gate enforces that the signer is not the
  author. If you review and correct a bundle, you still have not verified it.
- **Do not write a concept per struct.** The code already documents those, and a
  markdown copy is guaranteed rot. One data-model document with a pinned table
  beats twenty mirrors.
- **Do not cite generated or gitignored files as sources.** Check with
  `git ls-files --error-unmatch <path>` before adding any `sources[].resource`.
- **Do not claim more than the evidence supports.** If a shape was observed once
  rather than captured, say so in the document. A concrete-looking number with no
  source reads as evidence without being any.
