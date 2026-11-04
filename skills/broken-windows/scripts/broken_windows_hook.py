#!/usr/bin/env python3
"""Ask for /broken-windows when an agent session changes enough code.

SessionStart: save the session base.
Stop: block when code changed since the base is big or has a workaround marker.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MIN_LINES = 30
# shortcut: a bigger untracked file turns the hook off, because hashing it takes longer than the 10 s timeout and fills .git.
MAX_UNTRACKED_BYTES = 50 * 1024 * 1024
CODE_FILE = re.compile(rb"\.(?:go|rb|py|js|mjs|ts|tsx|jsx|html|css|sh|rs|java|kt|swift|c|h|cpp|sql)\Z")
TEST_FILE = re.compile(rb"(?:_test\.go|\.test\.|\.spec\.|_spec\.rb|(?:\A|/)(?:test|tests|spec|testdata)/)")
# Literal words only: a model call does not fit the 10 s hook timeout.
WORKAROUND_MARKER = re.compile(rb"\b(?:workaround|work around|hack|hacky|kludge|quick fix|temp fix|temporary|fixme|for now)\b", re.I)
STATE_OBJECT_ID = re.compile(rb"[0-9a-f]{40,64}")
STATE_DIR = os.environ.get("BROKEN_WINDOWS_STATE_DIR", os.path.expanduser("~/.cache/claude-broken-windows"))


# Bytes: file names and code can have any encoding.
def git(cwd, *args, index=None):
    env = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
    if index:
        env["GIT_INDEX_FILE"] = index
    result = subprocess.run(["git", "-C", cwd, *args], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return result.stdout if result.returncode == 0 else None


def is_code(path):
    return bool(CODE_FILE.search(path)) and not TEST_FILE.search(path)


def head_or_empty(cwd):
    head = git(cwd, "rev-parse", "--verify", "-q", "HEAD")
    return (head if head is not None else git(cwd, "hash-object", "-t", "tree", os.devnull)).decode().strip()


def save_state(state, value):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state, "w") as file:
        file.write(value)


def read_state(state):
    try:
        with open(state, "rb") as file:
            content = file.read().strip()
    except OSError:
        return ""
    return content.decode() if STATE_OBJECT_ID.fullmatch(content) else ""


def file_size(path):
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def has_big_untracked_file(top):
    untracked = git(top, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked is None:
        return False
    return any(file_size(os.path.join(top, path)) > MAX_UNTRACKED_BYTES for path in untracked.split(b"\0") if path)


# A copy of the real index keeps its stat cache, so git hashes only the changed files.
def snapshot_tree(top):
    index_path = git(top, "rev-parse", "--git-path", "index")
    if index_path is None:
        return None
    source = os.fsdecode(os.path.join(top, index_path[:-1]))
    with tempfile.TemporaryDirectory() as folder:
        index = os.path.join(folder, "index")
        if os.path.exists(source):
            shutil.copyfile(source, index)
        # --ignore-errors: one unreadable file must not hide the other changes.
        git(top, "add", "-A", "--ignore-errors", index=index)
        tree = git(top, "write-tree", index=index)
    return tree.decode().strip() if tree is not None else None


def changed_code(top, base, tree):
    numstat = git(top, "diff", "--numstat", "-z", "--no-renames", base, tree)
    if numstat is None:
        return []
    changes = []
    for record in numstat.split(b"\0"):
        fields = record.split(b"\t", 2)
        if len(fields) == 3 and is_code(fields[2]):
            added, deleted, path = fields
            changes.append((path, sum(int(count) for count in (added, deleted) if count.isdigit())))
    return changes


def adds_workaround(top, base, tree, paths):
    patch = git(top, "diff", "-U0", "--no-renames", "--no-color", "--no-ext-diff", base, tree, "--", *paths)
    if patch is None:
        return False
    in_hunk = False
    for line in patch.split(b"\n"):
        if line.startswith(b"diff --git "):
            in_hunk = False
        elif line.startswith(b"@@"):
            in_hunk = True
        elif in_hunk and line.startswith(b"+") and WORKAROUND_MARKER.search(line):
            return True
    return False


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
    except ValueError:
        return
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return

    session = re.sub(r"[^\w-]", "", str(data.get("session_id") or ""), flags=re.ASCII)
    cwd = str(data.get("cwd") or "")
    if not session or not cwd or git(cwd, "rev-parse", "--git-dir") is None:
        return

    state = os.path.join(STATE_DIR, session)

    if data.get("hook_event_name") == "SessionStart":
        if not os.path.exists(state):
            save_state(state, head_or_empty(cwd))
        return

    toplevel = git(cwd, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return
    top = toplevel[:-1]
    if has_big_untracked_file(top):
        return

    base = read_state(state)
    if not base or git(top, "cat-file", "-e", f"{base}^{{tree}}") is None:
        base = head_or_empty(top)
        save_state(state, base)
    tree = snapshot_tree(top)
    if tree is None:
        return

    changes = changed_code(top, base, tree)
    if not changes:
        return
    lines = sum(count for _, count in changes)
    if lines < MIN_LINES and not adds_workaround(top, base, tree, [path for path, _ in changes]):
        return

    save_state(state, tree)
    print(json.dumps({
        "decision": "block",
        "reason": f"Run /broken-windows on `git diff {base} {tree}` before you finish. Report only, do not apply fixes.",
    }))


if __name__ == "__main__":
    main()
