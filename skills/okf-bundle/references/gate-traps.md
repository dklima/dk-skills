# How a gate goes green while checking nothing

Read this before porting the validator to another language or adding a rule.
Every trap below was found by deliberately breaking a bundle and watching the
suite stay green. None was found by re-reading the code.

**The pattern:** every silent failure lived in a helper that *transforms text
before checking it*: a YAML loader, a fence stripper, a comment stripper. The
transform quietly produced nothing, the check ran over nothing and passed, and
the build went green. Treat every such helper as guilty until you have watched
it fail.

## Contents

- [Type coercion](#type-coercion)
- [Silently dropped entries](#silently-dropped-entries)
- [Fence handling](#fence-handling)
- [Comment stripping](#comment-stripping)
- [Literal matching](#literal-matching)
- [Bounded sections](#bounded-sections)
- [Identity comparison](#identity-comparison)
- [Missing-field escapes](#missing-field-escapes)
- [Regexes that over- and under-match](#regexes-that-over--and-under-match)
- [The harness itself](#the-harness-itself)

## Type coercion

YAML loaders resolve unquoted scalars aggressively. `2027-02-24T00:00:00Z`
becomes a date object, not a string. A `.(string)` assertion or an
`isinstance(v, str)` test then yields nothing, the check `continue`s, and every
freshness rule is inert, on exactly the values a real bundle writes.

Normalise through one accessor that accepts both, and distinguish *absent* from
*present but not a timestamp*:

```python
def as_stamp(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat(), True
    if isinstance(v, str):
        return v, True
    return None, v is not None
```

The same applies to `yes`/`no`/`on`/`off` (booleans), `1.0` (float) and `null`.

## Silently dropped entries

A `sources` list whose entry holds one non-string key decodes as `{1: ...}`.
Code that filters for string-keyed mappings drops that entry, and with it every
check on that entry, while the field still looks present.

A malformed element must invalidate the whole field, not vanish from it:

```python
for e in v:
    if not isinstance(e, dict) or any(not isinstance(k, str) for k in e):
        return None      # caller reports "not a mapping or list of mappings"
```

## Fence handling

Documentation about markdown must not be read as markdown, so blank fenced
contents before scanning for links, headings and footnotes. Three ways that goes
wrong:

**Blanking the delimiters too.** "Is there a fenced block here" is itself a rule.
Keep the delimiter lines, blank only the contents, and preserve the line count so
reported positions stay true.

**Toggling on any delimiter.** A three-backtick line shown inside a
four-backtick example closes its parent, and the example spills into every scan.
Follow CommonMark: record the opening character and its run length, and close
only on a run of the same character at least as long.

**Ignoring an unbalanced fence.** One unclosed fence makes every later line
blank, so the rest of the file stops being checked, silently, with a green
build. An unclosed fence is broken markdown anyway: **fail on it**.

## Comment stripping

When checking that a literal still exists in a source file, strip comments
first. A renamed symbol usually survives in the comment explaining the rename,
and counting that as "still present" misses the exact drift being hunted.

Two ways this bites back, in opposite directions:

**A `//` inside a string literal.** A cited file holding `"http://localhost:3000"`
loses everything after the `//`, and a document that correctly quotes that value
fails. Step over `"`, `'` and backtick literals while scanning.

**An unterminated `/*`.** Returning the truncated prefix discards the rest of the
file, so one odd string in a source turns every literal in the document red at
once, for a reason no author can act on. Return the input unchanged instead.

A false positive is not the safer failure here. It fires on ordinary edits, and
that is how a gate gets deleted.

## Literal matching

`strings.Contains` is wrong both ways. `conf` matches a file containing only
`config`, and a substring match of a partial rename passes. Use a word boundary:

```python
re.search(r"(?<![A-Za-z0-9_])" + re.escape(lit) + r"(?![A-Za-z0-9_])", text)
```

## Bounded sections

Two rules need a section body, and both are wrong when unbounded:

- "Is there a fenced block under `# Computation`": an unbounded search finds a
  fence under a *later* heading, so an empty section passes.
- "Is `# Attestation` non-empty": measuring to end of file counts the next
  section's text as this section's content.

Take the text from the heading to the **next top-level heading**.

Related: testing only that a backtick run appears somewhere in the section
accepts prose that merely mentions one. Require a fence at the start of a line.

## Identity comparison

Comparing actor strings byte-for-byte lets `human:DK@x` review `human:dk@x`, and
`human: dk@x` (one space) review `human:dk@x`. Normalise case and all internal
whitespace before comparing.

`human:` with nothing after it names nobody and must not satisfy a
human-review requirement. `process:` must not either, where the rule promises a
human.

## Missing-field escapes

The most dangerous class: the rule reads a field, the field is gone, and the
absence reads as success.

- **No `generated` block.** The author string is empty, so the
  "signer must differ from the author" test never fires; the zero timestamp makes
  any signature look recent enough. The document clears its own freshness gate.
  Guard: no usable author or no parseable `generated.at` means no valid review.
- **No `stale_after`.** Deleting one line is an unaudited escape from the
  freshness gate. Require the field on the document types that need it.
- **A field whose value coerced away.** Covered above, same shape.

For every rule, ask: *what happens when the field it reads is absent or
unparseable?* If the answer is "the loop does not execute", the rule has a hole.

## Regexes that over- and under-match

Each of these was observed, in both directions:

| Pattern | Misses | Falsely fires on |
|---|---|---|
| Inline link | `[the [inner] doc](x.md)`, nested brackets | |
| Reference definition `^\[..\]:` | | `[ -f .env ]: source .env` in a shell example |
| Footnote `\[\^(..)\]` | | a `[^0-9]+` character class in a code example |
| Reference usage `\]\[` | | `results[0][name]`, `[draft] [stable]` |
| Link destination | `[x](<path with space>)`, angle brackets | |
| Heading `^## (\d\S*)$` | a heading it does not fully match becomes invisible to **every** check on that file | |

That last row is the nastiest shape: a regex that *skips* what it cannot parse
turns malformed input into silence. Match loosely, then validate, so
`## 2026-08-24 (initial release)` is a failure rather than a ghost.

Also parse dates rather than shape-matching them, or `2026-13-45` passes.

## The harness itself

The self-test found a bug in the self-test: writing a mutated file as

```python
open(p, "w").write(mutate(open(p).read()))
```

truncates the file before the read is evaluated, so every mutation became a
no-op, while the run still reported "caught" for roughly half of them, because
an empty file trips a different rule. Read fully, then write.

The general lesson: **a test that reports "caught" is not proof it caught the
thing you meant**. Include controls that must stay green, and check that a
legitimate construct is tolerated as carefully as that a broken one is rejected.
