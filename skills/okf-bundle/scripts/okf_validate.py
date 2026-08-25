#!/usr/bin/env python3
"""Validate an Open Knowledge Format v0.2 bundle.

Two independent halves, reported separately:

  CONFORMANCE  what the OKF v0.2 spec requires of a producer. Never rejects a
               bundle for the things the spec tells CONSUMERS to tolerate:
               unknown types, unknown keys, absent optional fields.
  HOUSE        stricter local rules. A producer may check its own bundle harder
               than a consumer must; that is what makes it a gate.

Usage:
  okf_validate.py BUNDLE [--repo-root DIR] [--conformance-only] [--no-freshness]
  okf_validate.py --init BUNDLE      scaffold a minimal conformant bundle
  okf_validate.py --self-test        prove the validator still catches breakage

Exit 0 when clean, 1 when anything is reported, 2 on bad usage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile

try:
    import yaml
except ImportError:
    sys.exit("okf_validate: needs PyYAML (pip install pyyaml)")

RESERVED = ("index.md", "log.md")
FRONT_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})")
# One level of nested brackets in the link text, or [the [inner] doc](x.md) is missed.
INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(([^)]+)\)")
REF_DEF = re.compile(r"(?m)^[ \t]*\[([^^\]][^\]]*)\]:[ \t]*(\S+)")
REF_USE = re.compile(r"(^|[^\w\]])\[[^\]]*\]\[([^\]^][^\]]*)\]")
FOOTNOTE_USE = re.compile(r"\[\^([^\]]+)\]")
FOOTNOTE_DEF = re.compile(r"(?m)^\[\^([^\]]+)\]:")
HOUSE_FROM = re.compile(r"^[ \t]*<!--[ \t]*house:from[ \t]+(\S+)[ \t]*-->[ \t]*$")
LITERAL = re.compile(r"`([^`\n]+)`")
DATE_HEAD = re.compile(r"(?m)^## (\d\S*)(.*)$")
SLASH_LANGS = {".go", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cc",
               ".cpp", ".rs", ".cs", ".swift", ".kt", ".scala", ".php"}
HASH_LANGS = {".py", ".rb", ".sh", ".bash", ".yaml", ".yml", ".toml", ".tf", ".pl"}


class Finding:
    def __init__(self, half: str, where: str, msg: str):
        self.half, self.where, self.msg = half, where, msg

    def __str__(self) -> str:
        return f"  [{self.half}] {self.where}: {self.msg}"


# ---------------------------------------------------------------- text helpers

def fence_mask(lines: list[str]) -> tuple[list[int], bool]:
    """Classify each line: 0 outside, 1 delimiter, 2 fence contents.

    Closing follows CommonMark - only a run of the SAME character at least as
    long as the opener closes it. A plain toggle would let a ```sh line shown
    inside a ````-fenced example close its parent, spilling the example into
    every prose scan.
    """
    mask = [0] * len(lines)
    open_char, open_len = "", 0
    for i, ln in enumerate(lines):
        m = FENCE_RE.match(ln)
        if not open_len:
            if m:
                open_char, open_len = m.group(2)[0], len(m.group(2))
                mask[i] = 1
            continue
        if m and m.group(2)[0] == open_char and len(m.group(2)) >= open_len \
                and ln.strip() == m.group(2):
            open_len = 0
            mask[i] = 1
            continue
        mask[i] = 2
    return mask, open_len == 0


def strip_fences(body: str) -> tuple[str, bool]:
    """Blank fence CONTENTS, keep delimiters and line count.

    Delimiters stay because "is there a fenced block here" is itself a rule.
    Line count stays so reported positions remain true to the file.
    """
    lines = body.split("\n")
    mask, balanced = fence_mask(lines)
    return "\n".join("" if m == 2 else ln for ln, m in zip(lines, mask)), balanced


def strip_code_comments(src: str, ext: str) -> str:
    """Remove comments, leaving string literals alone.

    Both halves matter. A renamed symbol usually survives in a comment
    explaining the rename, and counting that as "still present" misses exactly
    the drift this checks for. Meanwhile a cited file may hold "http://host",
    and treating that // as a comment would swallow real code and fail a
    document that is perfectly correct.
    """
    slash = ext in SLASH_LANGS or ext not in HASH_LANGS
    hashes = ext in HASH_LANGS
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            j = end_of_literal(src, i)
            out.append(src[i:j])
            i = j
        elif slash and src.startswith("//", i):
            nl = src.find("\n", i)
            if nl < 0:
                break
            out.append("\n")
            i = nl + 1
        elif slash and src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                return src  # unterminated: keep everything rather than truncate
            out.append(" ")
            i = end + 2
        elif hashes and c == "#":
            nl = src.find("\n", i)
            if nl < 0:
                break
            out.append("\n")
            i = nl + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def end_of_literal(src: str, i: int) -> int:
    """Index just past the literal starting at i. Unterminated ends at newline."""
    quote = src[i]
    j = i + 1
    while j < len(src):
        ch = src[j]
        if ch == "\\" and quote != "`":
            j += 2
            continue
        if ch == "\n" and quote != "`":
            return j
        if ch == quote:
            return j + 1
        j += 1
    return len(src)


def literal_present(text: str, lit: str) -> bool:
    """Whole-token match, so `conf` does not satisfy a file holding only `config`."""
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(lit) + r"(?![A-Za-z0-9_])",
                     text) is not None


def as_stamp(v):
    """Normalise a timestamp field to an RFC3339-ish string.

    YAML resolves an unquoted ISO 8601 scalar to a date/datetime, so a plain
    isinstance(v, str) test returns nothing for exactly the values a bundle
    writes - silently disabling every freshness check instead of failing.
    Returns (value_or_None, present).
    """
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(), True
    if isinstance(v, str):
        return v, True
    return None, v is not None


def parse_instant(s: str):
    if s is None:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def same_actor(a: str, b: str) -> bool:
    """Ignore case and all internal spacing, so neither "human:DK@x" nor
    "human: dk@x" passes as somebody other than "human:dk@x"."""
    return "".join(a.split()).lower() == "".join(b.split()).lower()


# ---------------------------------------------------------------------- model

class Doc:
    def __init__(self, path: str, rel: str, raw: str):
        self.path, self.rel = path, rel
        self.dir = os.path.dirname(path)
        self.front, self.has_front, self.front_error = {}, False, None
        m = FRONT_RE.match(raw)
        self.body = raw[m.end():] if m else raw
        if m:
            self.has_front = True
            try:
                loaded = yaml.safe_load(m.group(1))
            except yaml.YAMLError as e:
                self.front_error = str(e).split("\n")[0]
                loaded = None
            self.front = loaded if isinstance(loaded, dict) else {}
            if loaded is not None and not isinstance(loaded, dict) and not self.front_error:
                self.front_error = "frontmatter is not a mapping"
        self.prose, self.fences_balanced = strip_fences(self.body)

    @property
    def reserved(self) -> bool:
        return os.path.basename(self.rel) in RESERVED

    @property
    def is_root_index(self) -> bool:
        return self.rel == "index.md"

    def typ(self) -> str:
        v = self.front.get("type")
        return v.strip() if isinstance(v, str) else ""

    def s(self, key: str) -> str:
        v = self.front.get(key)
        return v if isinstance(v, str) else ""

    def maps(self, key: str):
        """Normalise a field the spec allows as one mapping or a list of them.

        A list element that is not a string-keyed mapping invalidates the whole
        field rather than vanishing: YAML decodes a mapping holding one
        non-string key as {1: ...}, which would otherwise drop the entry and
        every check on it, silently.
        """
        v = self.front.get(key)
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            out = []
            for e in v:
                if not isinstance(e, dict) or any(not isinstance(k, str) for k in e):
                    return None
                out.append(e)
            return out
        return None


def load(bundle: str, out: list[Finding]) -> list[Doc]:
    if not os.path.isdir(bundle):
        sys.exit(f"okf_validate: bundle {bundle!r} is not a readable directory")
    docs = []
    for root, _, files in os.walk(bundle):
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, bundle).replace(os.sep, "/")
            if f.endswith(".json"):
                try:
                    json.load(open(p, encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    out.append(Finding("HOUSE", rel, f"not valid JSON: {e}"))
                continue
            if not f.endswith(".md"):
                continue
            docs.append(Doc(p, rel, open(p, encoding="utf-8").read()))
    if not docs:
        sys.exit(f"okf_validate: bundle {bundle!r} contains no markdown files")
    return sorted(docs, key=lambda d: d.rel)


# ------------------------------------------------------------------ the rules

def check_conformance(docs: list[Doc], out: list[Finding]) -> None:
    add = lambda d, m: out.append(Finding("CONFORMANCE", d.rel, m))
    for d in docs:
        if d.front_error:
            add(d, f"frontmatter does not parse: {d.front_error}")
        if d.reserved:
            if d.has_front and not d.is_root_index:
                add(d, "a reserved file must not carry frontmatter")
            elif d.has_front:
                for k in d.front:
                    if k != "okf_version":
                        add(d, f"the root index may only carry `okf_version`, found {k!r}")
            if os.path.basename(d.rel) == "log.md":
                heads = DATE_HEAD.findall(d.prose)
                if not heads:
                    add(d, "no date headings")
                for date, tail in heads:
                    if parse_date(date) is None or tail.strip():
                        add(d, f"date heading {(date + tail).strip()!r} must be exactly YYYY-MM-DD")
            continue

        if not d.has_front:
            add(d, "concept has no YAML frontmatter")
            continue
        if not d.typ():
            add(d, "frontmatter has no non-empty `type`")

        if d.typ() == "Attested Computation":
            if not d.s("runtime").strip():
                add(d, "an Attested Computation needs a non-empty `runtime`")
            comp = d.front.get("computation")
            if isinstance(comp, str) and comp.strip():
                pass
            elif comp is not None:
                add(d, "`computation` is present but not a non-empty string")
            else:
                sec = section(d.prose, "# Computation")
                if sec is None or not re.search(r"(?m)^[ \t]*(```|~~~)", sec):
                    add(d, "no `computation` path and no fenced block under `# Computation`")

        for key in ("sources", "verified"):
            if key in d.front and d.maps(key) is None:
                add(d, f"`{key}` is present but is not a mapping or list of mappings")
        seen_ids = set()
        for i, s in enumerate(d.maps("sources") or []):
            if not str(s.get("resource", "")).strip():
                add(d, f"sources[{i}] has no `resource` (required per entry)")
            if "id" in s:
                sid = str(s["id"]).strip()
                if not sid:
                    add(d, f"sources[{i}] has an empty `id`")
                elif sid in seen_ids:
                    add(d, f"sources[{i}] repeats id {sid!r}; attribution becomes ambiguous")
                seen_ids.add(sid)
        g = d.front.get("generated")
        if g is not None:
            if not isinstance(g, dict):
                add(d, "`generated` must be a mapping")
            elif not str(g.get("by", "")).strip():
                add(d, "`generated` is present but has no `by`")
        for i, v in enumerate(d.maps("verified") or []):
            if not str(v.get("by", "")).strip():
                add(d, f"verified[{i}] has no `by`")
            at, present = as_stamp(v.get("at"))
            if not present or not at:
                add(d, f"verified[{i}] has no usable `at`")


def check_house(docs: list[Doc], bundle: str, out: list[Finding],
                freshness: bool, now: dt.datetime) -> None:
    add = lambda d, m: out.append(Finding("HOUSE", d.rel, m))
    for d in docs:
        if not d.fences_balanced:
            # This is the one input that can blind the whole validator: every
            # later line is treated as code and stops being scanned.
            add(d, "a fenced block is opened and never closed")

        for target in link_targets(d):
            if not os.path.exists(os.path.join(d.dir, target)):
                add(d, f"reference {target!r} does not resolve (from {os.path.relpath(d.dir)})")

        defs = {m[0].strip().lower() for m in REF_DEF.findall(d.prose)}
        for m in REF_USE.findall(d.prose):
            if m[1].strip().lower() not in defs:
                add(d, f"reference-style link [{m[1]}] has no matching definition")

        for line_no, cited, block in house_from_blocks(d):
            src = os.path.join(d.dir, cited)
            try:
                text = strip_code_comments(open(src, encoding="utf-8").read(),
                                           os.path.splitext(src)[1])
            except OSError as e:
                add(d, f"line {line_no}: house:from cites {cited!r}, unreadable: {e}")
                continue
            lits = [m for m in LITERAL.findall(block)]
            if not lits:
                add(d, f"line {line_no}: house:from block has no backticked literal, "
                       "so it checks nothing")
                continue
            for lit in dict.fromkeys(lits):
                if not literal_present(text, lit):
                    add(d, f"line {line_no}: literal `{lit}` is no longer in {cited}")

        if d.reserved:
            if os.path.basename(d.rel) == "log.md":
                dates = [m[0] for m in DATE_HEAD.findall(d.prose) if parse_date(m[0])]
                for k in range(1, len(dates)):
                    if dates[k - 1] < dates[k]:
                        add(d, f"{dates[k-1]} appears before {dates[k]}; entries go newest first")
            continue

        st = d.front.get("status")
        if st is not None and st not in ("draft", "stable", "deprecated"):
            add(d, f"`status` is {st!r}, want draft|stable|deprecated")

        ex = d.front.get("executor")
        if ex is not None:
            if not isinstance(ex, dict):
                add(d, "`executor` must be a mapping")
            elif "resource" in ex and not str(ex["resource"]).strip():
                add(d, "`executor.resource` is present but empty")

        if d.typ() == "Attested Computation":
            heads = re.findall(r"(?m)^# Attestation[ \t]*$", d.prose)
            if len(heads) != 1:
                add(d, f"want exactly one `# Attestation` section, found {len(heads)}")
            elif not (section(d.prose, "# Attestation") or "").strip():
                add(d, "`# Attestation` section is empty")
            if freshness and not as_stamp(d.front.get("stale_after"))[0]:
                add(d, "an Attested Computation must carry `stale_after`")

        ids = {str(s.get("id", "")).strip() for s in (d.maps("sources") or [])}
        defined = set(FOOTNOTE_DEF.findall(d.prose))
        for label in FOOTNOTE_USE.findall(d.prose):
            if label not in ids:
                add(d, f"footnote [^{label}] has no matching `sources[].id`")
            if label not in defined:
                add(d, f"footnote [^{label}] is used but never defined")

        gen = d.front.get("generated") if isinstance(d.front.get("generated"), dict) else {}
        author = str(gen.get("by", "")).strip()
        gen_at_raw, _ = as_stamp(gen.get("at"))
        gen_at = parse_instant(gen_at_raw)
        if gen_at_raw and gen_at is None:
            add(d, f"`generated.at` is {gen_at_raw!r}, want an ISO 8601 instant")

        for i, v in enumerate(d.maps("verified") or []):
            by = str(v.get("by", "")).strip()
            if author and same_actor(by, author):
                add(d, f"verified[{i}].by is the author ({by}); self-verification does not count")
            at_raw, _ = as_stamp(v.get("at"))
            at = parse_instant(at_raw)
            if at_raw and at is None:
                add(d, f"verified[{i}].at is {at_raw!r}, want an ISO 8601 instant")
            elif at and gen_at and at < gen_at:
                add(d, f"verified[{i}].at predates generated.at; it cannot vouch for this text")

        if not freshness:
            continue
        sa_raw, sa_present = as_stamp(d.front.get("stale_after"))
        if not sa_present:
            continue
        deadline = parse_instant(sa_raw)
        if deadline is None:
            add(d, f"`stale_after` is {sa_raw!r}, want an ISO 8601 instant")
            continue
        if now < aware(deadline, now):
            continue
        if not independent_human_review(d, author, gen_at):
            add(d, f"stale_after {sa_raw} has passed and no `human:` reviewer other than "
                   f"{author or '(nobody)'} has signed since generated.at; re-read and record it")


def independent_human_review(d: Doc, author: str, gen_at) -> bool:
    """A `human:` actor other than the author, signed at or after generated.at.

    Both guards matter. With no author or no generated.at there is nothing for a
    signature to be independent OF or later THAN, so a document missing its
    `generated` block would otherwise clear its own gate.
    """
    if not author or gen_at is None:
        return False
    for v in d.maps("verified") or []:
        by = str(v.get("by", "")).strip()
        if not by.startswith("human:") or same_actor(by, author):
            continue
        if not by[len("human:"):].strip():
            continue  # "human:" with nothing after it names nobody
        at = parse_instant(as_stamp(v.get("at"))[0])
        if at and aware(at, gen_at) >= aware(gen_at, at):
            return True
    return False


def aware(a, like):
    """Match tz-awareness so naive and aware instants can be compared."""
    if a.tzinfo is None and like.tzinfo is not None:
        return a.replace(tzinfo=dt.timezone.utc)
    if a.tzinfo is not None and like.tzinfo is None:
        return a.replace(tzinfo=None)
    return a


def parse_date(s: str):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def section(prose: str, heading: str):
    """Body of a top-level heading, ending at the next one.

    Bounded on purpose: an unbounded search would accept a fenced block living
    under a later section, so an empty `# Computation` would pass.
    """
    m = re.search(r"(?m)^" + re.escape(heading) + r"[ \t]*$", prose)
    if not m:
        return None
    rest = prose[m.end():]
    nxt = re.search(r"(?m)^# ", rest)
    return rest[:nxt.start()] if nxt else rest


def link_targets(d: Doc) -> list[str]:
    """Every local relative path the document points at.

    Scans the fence-stripped prose, so an example that SHOWS markdown is not
    read as markdown. Includes the top-level `resource` key, which is a
    concept's primary provenance pointer and easy to forget.
    """
    raw = [m for m in INLINE_LINK.findall(d.prose)]
    raw += [m[1] for m in REF_DEF.findall(d.prose)]
    raw.append(d.s("resource"))
    for s in d.maps("sources") or []:
        raw.append(str(s.get("resource", "")))
    ex = d.front.get("executor")
    if isinstance(ex, dict):
        raw.append(str(ex.get("resource", "")))

    out = []
    for r in raw:
        r = r.strip().strip("<>")          # angle-bracket destinations are legal
        r = re.split(r"[ \t]", r, maxsplit=1)[0]    # drop a link title
        r = re.split(r"[#?]", r, maxsplit=1)[0]
        if not r or r.startswith("/") or "://" in r or r.startswith("mailto:"):
            continue
        out.append(r)
    return out


def house_from_blocks(d: Doc):
    """Yield (line_no, cited_path, block) for each house:from marker.

    Markers are read from the RAW body, not the stripped prose: stripping would
    blank a fenced block and leave the marker checking nothing, silently. A
    marker inside a fence is skipped instead - that one is an example, not a
    marker. The block is the contiguous run of non-blank lines directly below;
    blank lines are NOT skipped, or one sentence between marker and table would
    quietly move the check onto the sentence.
    """
    lines = d.body.split("\n")
    mask, _ = fence_mask(lines)
    for i, line in enumerate(lines):
        if mask[i] != 0:
            continue
        m = HOUSE_FROM.match(line)
        if not m:
            continue
        j = i + 1
        start = j
        while j < len(lines) and lines[j].strip():
            j += 1
        yield i + 1, m.group(1), "\n".join(lines[start:j])


# ------------------------------------------------------------------ scaffold

SCAFFOLD = {
    "index.md": '---\nokf_version: "0.2"\n---\n\n# Knowledge\n\nWhat this bundle covers.\n\n'
                "## Architecture\n\n* [Example concept](architecture/example.md) - replace me.\n",
    "log.md": "# Update Log\n\n## {today}\n\n* **Initialization**: bundle created.\n",
    "architecture/index.md": "# Architecture\n\n* [Example concept](example.md) - replace me.\n",
    "architecture/example.md": (
        "---\ntype: Architecture Note\ntitle: Example concept\n"
        "description: Replace this with one sentence saying what the document explains.\n"
        "tags: [example]\n"
        "generated: {{ by: human:you@example.com, at: {stamp} }}\n"
        "sources:\n  - id: example-source\n    resource: ../index.md\n"
        "    title: Replace with the file this was written from\n---\n\n"
        "# Example concept\n\nWrite the explanation here, from the code rather than from\n"
        "older documents.[^example-source]\n\n"
        "[^example-source]: Replace with the file this was written from\n"),
}


def scaffold(dest: str) -> None:
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit(f"okf_validate: {dest!r} already exists and is not empty")
    today = dt.date.today().isoformat()
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for rel, text in SCAFFOLD.items():
        p = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text.format(today=today, stamp=stamp))
    print(f"scaffolded a conformant bundle at {dest}")
    print("next: run this validator against it, then replace the example concept")


# ------------------------------------------------------------------ self test

MUTATIONS = [
    ("missing type", "architecture/example.md", lambda s: s.replace("type: Architecture Note\n", "")),
    ("broken markdown link", "index.md", lambda s: s.replace("architecture/example.md", "nope.md")),
    ("broken sources resource", "architecture/example.md", lambda s: s.replace("resource: ../index.md", "resource: ../nope.md")),
    ("frontmatter on a subdirectory index", "architecture/index.md", lambda s: "---\ntype: X\n---\n\n" + s),
    ("extra key on the root index", "index.md", lambda s: s.replace('okf_version: "0.2"', 'okf_version: "0.2"\ntitle: nope')),
    ("footnote without a source id", "architecture/example.md", lambda s: s.replace("[^example-source]", "[^nosuch]")),
    ("self-verification", "architecture/example.md", lambda s: s.replace("sources:", "verified: { by: human:you@example.com, at: 2099-01-01T00:00:00Z }\nsources:")),
    ("case-and-space self-verification", "architecture/example.md", lambda s: s.replace("sources:", 'verified: { by: "human: YOU@example.com", at: 2099-01-01T00:00:00Z }\nsources:')),
    ("signature predating the content", "architecture/example.md", lambda s: s.replace("sources:", "verified: { by: human:other@example.com, at: 2000-01-01T00:00:00Z }\nsources:")),
    ("bad status value", "architecture/example.md", lambda s: s.replace("tags: [example]", "tags: [example]\nstatus: finished")),
    ("unparseable timestamp", "architecture/example.md", lambda s: s.replace("tags: [example]", "tags: [example]\nstale_after: not-a-date")),
    ("expired stale_after", "architecture/example.md", lambda s: s.replace("tags: [example]", "tags: [example]\nstale_after: 2000-01-01T00:00:00Z")),
    ("unclosed fence", "architecture/example.md", lambda s: s + "\n```sh\nunclosed\n"),
    ("coerced sources entry", "architecture/example.md", lambda s: s.replace("sources:\n", "sources:\n  - 1: oops\n    resource: ../nope.go\n")),
    ("house:from drift", "architecture/example.md", lambda s: s + "\n<!-- house:from ../index.md -->\n| `totally_invented_token` |\n"),
    ("house:from with nothing to check", "architecture/example.md", lambda s: s + "\n<!-- house:from ../index.md -->\n```go\nx := 1\n```\n"),
    ("non-ISO log date", "log.md", lambda s: re.sub(r"## \d{4}-\d{2}-\d{2}", "## 2026-13-45", s)),
    ("log entries out of order", "log.md", lambda s: s + "\n## 2099-01-01\n\n* **Later**: thing.\n"),
]

TOLERATED = [
    ("markdown example inside a fence", "architecture/example.md",
     lambda s: s + "\n```markdown\n* [x](nope.md)\n[r]: nope2.md\n# Attestation\n```\n"),
    ("nested fences", "architecture/example.md",
     lambda s: s + "\n````\n```sh\ncurl [x](nope.md)\n```\n````\n"),
    ("brackets in prose", "architecture/example.md",
     lambda s: s + "\nRead results[0][name] and pick [draft] [stable].\n"),
    ("angle-bracket link target", "index.md",
     lambda s: s.replace("(architecture/example.md)", "(<architecture/example.md>)")),
    ("non-date heading in the log", "log.md", lambda s: s + "\n## Notes\n\nplain section\n"),
    ("unknown type and unknown keys", "architecture/example.md",
     lambda s: s.replace("type: Architecture Note", "type: Something Nobody Registered\nwidget: 3")),
]


def self_test() -> int:
    """Break the bundle on purpose and confirm each break is reported.

    A green validator proves nothing until you watch it fail. Every silent-skip
    bug this code guards against was found this way and by no other means.
    """
    import shutil
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "base")
        scaffold_quiet(base)
        clean = run(base, True, True)
        if clean:
            print("SELF-TEST FAILED: the pristine scaffold does not validate")
            for f in clean:
                print(f)
            return 1
        print("ok    pristine scaffold is clean")

        for name, rel, mutate in MUTATIONS:
            work = os.path.join(tmp, "w")
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(base, work)
            apply_mutation(os.path.join(work, rel), mutate)
            if run(work, True, True):
                print(f"ok    caught: {name}")
            else:
                print(f"MISS  not caught: {name}")
                failures += 1

        for name, rel, mutate in TOLERATED:
            work = os.path.join(tmp, "w")
            shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(base, work)
            apply_mutation(os.path.join(work, rel), mutate)
            found = run(work, True, True)
            if found:
                print(f"FALSE-POSITIVE  {name}")
                for f in found:
                    print(f)
                failures += 1
            else:
                print(f"ok    tolerated: {name}")

    print(f"\n{'FAILED' if failures else 'PASSED'}: "
          f"{len(MUTATIONS)} breakages, {len(TOLERATED)} legitimate constructs, {failures} problem(s)")
    return 1 if failures else 0


def apply_mutation(path: str, mutate) -> None:
    """Read fully, then write. Opening for write first truncates the file before
    the read is evaluated, which silently turns every mutation into a no-op."""
    text = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write(mutate(text))


def scaffold_quiet(dest: str) -> None:
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        scaffold(dest)


def run(bundle: str, house: bool, freshness: bool) -> list[Finding]:
    out: list[Finding] = []
    docs = load(bundle, out)
    check_conformance(docs, out)
    if house:
        check_house(docs, bundle, out, freshness, dt.datetime.now(dt.timezone.utc))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", nargs="?", help="path to the bundle directory")
    ap.add_argument("--init", metavar="DIR", help="scaffold a minimal conformant bundle")
    ap.add_argument("--self-test", action="store_true",
                    help="break a scaffold on purpose and confirm each break is caught")
    ap.add_argument("--conformance-only", action="store_true",
                    help="run only the OKF spec half, skipping the house rules")
    ap.add_argument("--no-freshness", action="store_true",
                    help="do not fail on an expired stale_after (use with evidence, not by default)")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if a.init:
        scaffold(a.init)
        return 0
    if not a.bundle:
        ap.print_usage()
        return 2

    found = run(a.bundle, not a.conformance_only, not a.no_freshness)
    if not found:
        print(f"okf: {a.bundle} is clean")
        return 0
    for half in ("CONFORMANCE", "HOUSE"):
        rows = [f for f in found if f.half == half]
        if rows:
            print(f"{half} ({len(rows)}):")
            for f in rows:
                print(f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
