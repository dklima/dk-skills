# dk-skills

Skills for Claude Code, aimed at code and documentation that quietly get worse:
documentation that stops being true, and bad patterns that coding agents copy.

## Install

### As a Claude Code plugin

```
/plugin marketplace add dklima/dk-skills
/plugin install skills@dk-skills
```

### Standalone, one skill only

A skill is a directory. Copy the one you want and nothing else runs.

```sh
git clone https://github.com/dklima/dk-skills /tmp/dk-skills
cp -r /tmp/dk-skills/skills/okf-bundle ~/.claude/skills/okf-bundle
```

Use `.claude/skills/` inside a repository instead of `~/.claude/skills/` when
the skill belongs to that project and its collaborators.

### Other agents that read `~/.agents/skills`

Agents that follow the shared skills directory read `~/.agents/skills`. Same
copy, different target:

```sh
mkdir -p ~/.agents/skills
cp -r /tmp/dk-skills/skills/okf-bundle ~/.agents/skills/okf-bundle
```

To keep one copy on disk, symlink instead:

```sh
ln -s ~/.claude/skills/okf-bundle ~/.agents/skills/okf-bundle
```

The skill body is plain markdown and the validator is plain Python 3, so nothing
in it depends on Claude Code. An agent that cannot load `SKILL.md` can still run
the gate directly:

```sh
python3 ~/.agents/skills/okf-bundle/scripts/okf_validate.py --init knowledge
python3 ~/.agents/skills/okf-bundle/scripts/okf_validate.py knowledge
python3 ~/.agents/skills/okf-bundle/scripts/okf_validate.py --self-test
```

## What is in here

### `okf-bundle`

Builds an [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format)
v0.2 bundle for a codebase (markdown with YAML frontmatter, versioned next to
the code) and wires a gate that fails the build when the two drift apart.

The format is the easy half. The gate is the point:

- a block that copies names out of the code is pinned to the file it came from,
  so a rename in the source breaks the document that describes it;
- every relative link has to resolve;
- an author cannot sign off their own document, so "human-reviewed" always means
  two people;
- a re-read date that passes fails the build until somebody else reads it.

Every rule also states what it does **not** prove. A green build that implies
"reviewed and correct" is worse than no build, because it stops people looking.

The validator is language-agnostic and ships with a `--self-test` that breaks a
bundle 18 ways and confirms each break is caught, plus 6 pieces of legitimate
but awkward markdown that must stay green. That second half matters as much as
the first: a gate that fails on correct input gets deleted.

Requires Python 3 and PyYAML.

**Invoke it** by asking for the outcome, not the file: "create an OKF bundle for
this service", "put the project knowledge under version control", "add a CI gate
that fails when the docs drift". The skill also covers validating, extending or
porting a bundle that already exists.

**Reference material** lives beside the skill and is read on demand, not up
front:

| File | Covers |
|---|---|
| `references/spec-v0.2.md` | The format itself. |
| `references/authoring.md` | What goes in each file, and in what order. |
| `references/conventions.md` | Actors, naming, link style. |
| `references/gate-traps.md` | The ways a gate goes green while checking nothing. Read this before porting the rules to Go, Node or Rust. |

### `broken-windows`

Reviews a diff for "broken windows": code or comments that a later agent will
read, treat as the reference, and copy. One passable workaround becomes the
template for the next ten changes. Based on
[The broken windows theory of coding agents](https://www.manager.dev/newsletter/the-broken-windows-theory-of-coding-agents).

The test for each pattern: what if 100 more agents do this exact same thing
everywhere? The skill greps the repo to tell a new window from an existing
convention, and still reports a diff that spreads a bad pattern that exists
already.

It reports only. It changes no code until you ask for the fixes.

**Invoke it** with `/broken-windows`, or ask "did this change add broken
windows?" or "what will the next agent copy from this diff?". With no target,
it reviews the uncommitted changes, then the last commit.

## For an agent reading this repo

Start at `skills/okf-bundle/SKILL.md`. It is the entry point, and each step
names the one reference file that step needs. Read a reference when you reach
the step that cites it. Do not load all four up front.

```
skills/okf-bundle/
  SKILL.md                  the workflow, in order, plus what not to do
  scripts/okf_validate.py   the gate. Run it, do not reimplement it
  references/               spec, conventions, authoring, gate traps
```

- **Asked to build a bundle?** Follow the workflow in `SKILL.md` from step 1.
  The gate is wired at step 3, before any prose gets written.
- **Asked to change or port the validator?** Read `references/gate-traps.md`
  first. It is the list of ways a gate reports success while checking nothing.
- **Before you report a green run**, run `--self-test`. It breaks a scaffold 18
  ways and tells you which breaks were caught.
- **Read the output, not the exit code alone.** Exit 0 is clean, 1 is findings,
  2 is bad usage. Findings print one per line, grouped by half:
  ```
  HOUSE (1):
    [HOUSE] architecture/example.md: reference '../nope/missing.md' does not resolve (from knowledge/architecture)
  ```
- **Do not sign your own work.** Leave `verified` absent. `SKILL.md` closes with
  three more traps of the same kind. Read that section before you finish.
- **Asked to review a diff for patterns the next agent will copy?** Start at
  `skills/broken-windows/SKILL.md`. It is one file, with no scripts or
  references.

The skill is markdown and the validator is one Python 3 file on the standard
library plus PyYAML. Nothing here needs Claude Code, a network call, or a
config file.

## Licence

MIT.
