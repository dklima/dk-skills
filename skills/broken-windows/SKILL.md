---
name: broken-windows
description: Review a diff for "broken windows", code or comments that a later agent will copy as a reference and so spread bad code. Use when the user asks if a change introduced broken windows, bad precedents, patterns the next agent will imitate, or says /broken-windows. Reads the diff and the code around it, changes nothing.
---

# Broken Windows Review

An agent that edits a file reads the code around the edit and copies its shape.
One bad pattern in the tree becomes the template for the next ten changes.
This review finds the patterns in a change that a later agent will copy.

## Scope

- Review what the user names. Nothing named: the uncommitted changes. No uncommitted changes: the last commit.
- Read the diff, then the code each hunk touches: the surrounding function, its callers, the helpers it calls.
- Read the project CLAUDE.md. Its conventions decide what "bad" means in this repo.

## Step 1: Separate new from existing

For each suspect pattern, grep the repo for it before you report it.

- The pattern exists already, the diff follows it, and it passes Step 2: it is convention. Name it in one line under "Follows existing pattern" and move on.
- The pattern exists already, the diff follows it, and it fails Step 2: the diff spreads an existing window. Report it under **Nice to have** with the count of copies. Following a bad pattern is how every window breaks.
- The diff is the first or second use: report it. The first copy is the one that sets the precedent. This is most dangerous where the area has no good example yet.
- The diff copies a pattern the project CLAUDE.md bans: report it, even if older code does it too.

## Step 2: Look for these

1. **Duplicated rule.** The diff copies logic that already lives in a helper, so two copies must change together. Name both paths and lines.
2. **State through strings.** The diff formats a value into a string only for other code to parse it back.
3. **False comment.** A comment states a fact that the code does not do. Open the code it names and confirm each claim (handler behavior, side effects, "same as X"). A false comment is the worst window: an agent trusts it over the code.
4. **Narrating comment.** A comment repeats what the code says, or a label (ticket id, phase code) with no why. It teaches the next agent to add comment noise.
5. **Naming drift.** A new name for a concept that already has a name (`On` next to `Enabled`). One concept, one name.
6. **Swallowed error.** `_ =`, `if err == nil {}` with no else, `catch(){}`, or one catch that reports the wrong failure, for example "Failed" after the write succeeded.
7. **Test that cannot fail.** A test that would still pass if the logic broke, or that covers only the easy case of a new branch.
8. **Hack.** A workaround, double call or magic number. With no one-line reason, it is always a finding. With a reason, it is still a finding when a later agent will copy it to a place where the reason does not apply.
9. **Global or shared state.** A new global, singleton or mutable package variable.
10. **Cost that adds up.** A query, network call, file read or full scan inside a loop or a hot path. One copy is cheap. One hundred copies are slow.
11. **Race condition.** Two paths read and then write the same state with no lock, transaction or atomic operation. Check-then-act on files, rows or caches.

## Step 3: Check each finding

- Apply this test to each pattern: "What if 100 more agents do this exact same thing everywhere?" If the answer is bugs, slow code or confused agents, it is a window.
- Every finding needs a concrete case: "an agent that adds X here will copy Y and produce Z", or an input that gives a wrong result.
- Re-read the lines. Confirm the duplicate exists, the comment is false, the error is lost.
- No case: no finding. No style taste.

## Output

Write in the language the user writes in. Use short sentences and plain words.

Start with `What this change does:` in two sentences.
Then answer the question directly: did the diff add broken windows, yes or no.
Then `Follows existing pattern:` with one line for each pattern you cleared in Step 1, and why it is fine.

List findings in **Should fix** and **Nice to have** (use **Must fix** for a real bug), numbered across groups. Each finding has:

- **What this is:** the code and where (`path:line`).
- **Problem:** what goes wrong, and what the next agent will copy.
- **Fix:** the smallest change. Prefer a change that deletes code.
- **If we skip it:** the cost.

End with `Verdict:` (ship, or which numbers to fix first) and `Not checked:` in one line.

This skill reports only. It changes no code until the user asks for the fixes.
