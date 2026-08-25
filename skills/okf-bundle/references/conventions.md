# House conventions

Local rules on top of OKF v0.2. Each one exists because the bundle is worse
without it. The reasons matter more than the rules: a project may decide
differently, but it should decide knowingly.

## Contents

- [The author is a person](#the-author-is-a-person)
- [Self-verification does not count](#self-verification-does-not-count)
- [Freshness is a gate, not a note](#freshness-is-a-gate-not-a-note)
- [Links are relative](#links-are-relative)
- [Never cite what the reader lacks](#never-cite-what-the-reader-lacks)
- [Pin copied literals](#pin-copied-literals)
- [Say what the gate does not prove](#say-what-the-gate-does-not-prove)

## The author is a person

```yaml
generated: { by: human:someone@example.com, at: 2026-08-24T21:30:00Z }
```

The actor is whoever owns the content, never the tool that typed it. An agent
name in `generated.by` puts a machine where accountability belongs, and readers
discount the document accordingly. **Ask the user whose address to use.** Do not
guess it from git config, and do not put yourself there.

## Self-verification does not count

`verified[].by` must differ from `generated.by`, and the gate enforces it.

Without that rule the Human-reviewed tier is a stamp the author applies to
themselves in the same edit, which is exactly the distinction the tier exists
to draw. The consequence is deliberate: **every concept is born Unverified**,
and rises only when someone else signs.

Comparison must ignore case and internal spacing. `human:DK@x` and
`human: dk@x` are the same person as `human:dk@x`, and a byte compare lets both
through.

An agent that writes, reviews and corrects a bundle has still not verified it.
Leave `verified` absent and say so.

## Freshness is a gate, not a note

`stale_after` on anything that rots: contracts owned by other services,
playbooks that track a moving environment. Six months is a reasonable default.
Skip it on stable architecture prose.

An expired `stale_after` **fails the build**. The only way to clear it is a
`verified` entry whose `by` starts with `human:`, names somebody, differs from
the author, and is dated at or after `generated.at`.

A `process:` actor must not clear it: that delivers Machine-confirmed where the
gate promises a human read.

**What this proves:** a named human who is not the author put their name on the
document after its last recorded content change. **What it does not prove:** that
they read it carefully. Write that limit into the gate's own comments rather
than letting the green build imply more.

If it ever blocks real work because no reviewer is available, downgrade it to a
warning **with that evidence in hand**, not pre-emptively.

## Links are relative

The spec recommends bundle-relative `/...` paths, but GitHub resolves a leading
`/` against the site root, not the bundle. For the usual audience (developers
reading in an editor and on GitHub) relative paths work in both, and one rule
then covers intra-bundle links and links out to source.

**Resolution rule, stated once:** every relative path resolves against the
directory of the file containing it, never against the bundle root. That is what
makes `../../internal/store/mongo.go` correct in `knowledge/api/x.md` and wrong
if copied to the root.

Links that leave the bundle break tarball distribution. That is a real cost;
take it deliberately, and record the decision in the root `index.md` so the next
reader knows it was a choice.

## Never cite what the reader lacks

`sources[].resource` may only name something a fresh clone has: tracked files
and public URLs. Check before adding one:

```sh
git ls-files --error-unmatch <path>
```

Local-only design notes and personal runbooks are usually the most valuable
content in the bundle, and they must be **rewritten into concept bodies**, not
linked. A dangling reference to a file only one person has is worse than no
reference.

The same applies to generated artifacts. A committed OpenAPI snapshot is a
convenient link, but if it lags the handlers it is not a source of truth; cite
the router or the handlers instead.

## Pin copied literals

Prose ages slowly. A list of names copied out of the code is wrong at the first
rename. Mark those blocks:

```markdown
<!-- house:from ../../internal/store/mongo.go -->
| Collection | Struct |
|---|---|
| `hosts` | `model.Host` |
```

Every backticked literal in the block must still appear in the cited file. Keep
one origin per block: a block citing `mongo.go` may only quote things that live
in `mongo.go`.

Use `house:from`, not `okf:from`. The convention is local, and prefixing it with
the specification's name implies the specification defines it.

**What it catches:** renames, deletions, drifted enumerated values: most real
rot. **What it does not:** prose that describes the semantics wrongly. Only a
human read catches that, which is what the freshness gate asks for.

## Say what the gate does not prove

Every rule that could be mistaken for a stronger guarantee states its limit, in
the gate's own source. A green build that silently implies "reviewed and
correct" is worse than no build, because it stops people looking.
