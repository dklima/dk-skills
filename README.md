# dk-skills

Skills for Claude Code, aimed at one problem: documentation that quietly stops
being true.

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

## Agentic friendly

Nothing here assumes a particular agent, or an agent at all.

- **Progressive disclosure.** `SKILL.md` is 146 lines and names the reference
  file for each job. The agent reads one of them when it needs it, so the four
  references stay out of the context window until they earn a place in it.
- **One script, no install.** The validator is a single file on the standard
  library plus PyYAML. No config file, no network call, no state on disk.
- **Read-only by default.** Only `--init` writes, and it refuses a directory
  that already holds files.
- **Machine-readable results.** Exit 0 when clean, 1 when anything is reported,
  2 on bad usage. Findings print one per line, grouped by half:
  ```
  HOUSE (1):
    [HOUSE] architecture/example.md: reference '../nope/missing.md' does not resolve (from knowledge/architecture)
  ```
- **Verifiable before it is trusted.** `--self-test` breaks a scaffold 18 ways
  and reports which breaks were caught. An agent can prove the gate works, then
  believe the green run.
- **Plain text end to end.** Bundle, skill and references are markdown in git.
  An agent with a file reader and a shell has everything it needs.

## Licence

MIT.
