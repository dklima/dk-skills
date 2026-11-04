#!/usr/bin/env python3
"""Check broken_windows_hook.py against real throwaway git repos."""
import json
import os
import re
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broken_windows_hook.py")


def check(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def sh(cwd, *args):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_raw(home, payload, **env):
    result = subprocess.run([sys.executable, HOOK], input=payload, stdout=subprocess.PIPE,
                            env={**os.environ, "BROKEN_WINDOWS_STATE_DIR": os.path.join(home, "state"), **env})
    return result


def run_hook(home, cwd, session, event, stop_active=False):
    payload = json.dumps({"session_id": session, "cwd": cwd, "hook_event_name": event, "stop_hook_active": stop_active})
    result = run_raw(home, payload.encode())
    check(result.returncode == 0, f"hook exits 0 on {event}")
    return result.stdout.decode()


def write_lines(repo, name, count, line="x = 1"):
    path = os.path.join(repo, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as file:
        file.write(f"{line}\n" * count)


def blocked(out):
    return bool(out) and json.loads(out)["decision"] == "block"


def stop(home, repo, session, **options):
    return blocked(run_hook(home, repo, session, "Stop", **options))


def new_repo(home, name="repo", seed=True):
    repo = os.path.join(home, name)
    os.makedirs(repo)
    sh(repo, "init", "-q")
    if seed:
        write_lines(repo, "seed.rb", 1)
        sh(repo, "add", "-A")
        sh(repo, "commit", "-qm", "seed")
    return repo


def commit(repo):
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "work")


def test_small_clean_diff(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 3)
    check(not stop(home, repo, "s"), "small clean diff passes")
    status = subprocess.run(["git", "-C", repo, "-c", "color.ui=false", "status", "--short"], stdout=subprocess.PIPE)
    check(b"?? a.rb" in status.stdout, "real index stays unchanged")


def test_marker(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 2, "sleep 1 # workaround")
    check(stop(home, repo, "s"), "small diff with a workaround marker blocks")


def test_tests_and_docs_do_not_block(home):
    repo = new_repo(home)
    write_lines(repo, "spec/a_spec.rb", 2, "# hack")
    write_lines(repo, "notes.md", 50)
    check(not stop(home, repo, "s"), "test and doc files do not block")


def test_repeat_covers_only_new_work(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    check(not stop(home, repo, "s", stop_active=True), "stop_hook_active never blocks")
    check(stop(home, repo, "s"), "big diff blocks")
    check(not stop(home, repo, "s"), "same diff does not block twice")
    write_lines(repo, "b.rb", 30)
    second = run_hook(home, repo, "s", "Stop")
    check(blocked(second), "a new diff in the same session blocks again")
    revisions = re.search(r"`git diff (.+?)`", json.loads(second)["reason"]).group(1).split()
    names = subprocess.run(["git", "-C", repo, "diff", "--name-only", *revisions], stdout=subprocess.PIPE)
    check(names.stdout.split() == [b"b.rb"], "second review covers only the new file")


def test_committed_work(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    commit(repo)
    check(stop(home, repo, "s"), "committed work blocks")


def test_resume_keeps_base(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    commit(repo)
    run_hook(home, repo, "s", "SessionStart")
    check(stop(home, repo, "s"), "resume keeps the first base")


def test_missing_base_uses_head(home):
    repo = new_repo(home)
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "missing base falls back to HEAD")


def test_glob_and_non_ascii_paths(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "app/[id]/página.tsx", 2, "// hack")
    check(stop(home, repo, "s"), "glob and non-ASCII paths block")


def test_pathspec_magic_is_literal(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, ":x.rb", 2, "# hack")
    check(stop(home, repo, "s"), "pathspec magic in a file name is literal")


def test_latin1_path(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    with open(os.path.join(os.fsencode(repo), b"caf\xe9.rb"), "wb") as file:
        file.write(b"# hack\n")
    check(stop(home, repo, "s"), "Latin-1 file name does not crash")


def test_subfolder_cwd(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "lib/deep/a.rb", 2, "# hack")
    check(stop(home, os.path.join(repo, "lib"), "s"), "cwd in a subfolder finds the marker")


def test_color_and_external_diff(home):
    repo = new_repo(home)
    sh(repo, "config", "color.ui", "always")
    sh(repo, "config", "diff.external", "false")
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 2, "# hack")
    check(stop(home, repo, "s"), "color and external diff config do not hide the marker")


def test_line_that_starts_with_plus_plus(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.c", 2, "++i; // hack")
    check(stop(home, repo, "s"), "added line that starts with ++ is not a header")


def test_marker_in_file_name(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "hack.rb", 2)
    check(not stop(home, repo, "s"), "marker word in a file name does not block")


def test_deleted_lines_count(home):
    repo = new_repo(home)
    write_lines(repo, "big.rb", 30)
    commit(repo)
    run_hook(home, repo, "s", "SessionStart")
    os.remove(os.path.join(repo, "big.rb"))
    check(stop(home, repo, "s"), "deleted lines count")


def test_unreadable_file(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "secret.rb", 1)
    os.chmod(os.path.join(repo, "secret.rb"), 0)
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "unreadable file does not hide other changes")
    os.chmod(os.path.join(repo, "secret.rb"), 0o600)


def test_missing_base_object(home):
    repo = new_repo(home)
    os.makedirs(os.path.join(home, "state"))
    with open(os.path.join(home, "state", "s"), "w") as file:
        file.write("0" * 40)
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "missing base object falls back to HEAD")


def test_first_stop_saves_base(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "Stop")
    write_lines(repo, "a.rb", 10)
    check(not stop(home, repo, "s"), "small work without a saved base passes")
    commit(repo)
    write_lines(repo, "b.rb", 25)
    check(stop(home, repo, "s"), "first Stop saves the base, so later work adds up")


def test_big_untracked_file(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    dump = os.path.join(repo, "dump.bin")
    with open(dump, "wb") as file:
        file.truncate(51 * 1024 * 1024)
    check(not stop(home, repo, "s"), "big untracked file skips the snapshot")
    os.remove(dump)
    check(stop(home, repo, "s"), "hook works again without the big file")


def test_non_ascii_under_c_locale(home):
    repo = new_repo(home, "repó")
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    payload = json.dumps({"session_id": "s", "cwd": repo, "hook_event_name": "Stop"}, ensure_ascii=False)
    result = run_raw(home, payload.encode(), LC_ALL="C")
    check(blocked(result.stdout.decode()), "non-ASCII stdin and cwd under LC_ALL=C work")


def test_outside_git(home):
    plain = os.path.join(home, "plain")
    write_lines(plain, "a.rb", 30)
    check(not stop(home, plain, "s"), "folder outside git with code does not block")
    check(not os.path.exists(os.path.join(home, "state", "s")), "folder outside git saves no state")


def test_repo_with_no_commits(home):
    repo = new_repo(home, seed=False)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "repo with no commits blocks")


def test_bad_input(home):
    repo = new_repo(home)
    write_lines(repo, "a.rb", 30)
    bad_sessions = (json.dumps({"session_id": value, "cwd": repo}).encode() for value in ("!!!", None, ""))
    for payload in (b"not json", b"[]", *bad_sessions):
        result = run_raw(home, payload)
        check(result.returncode == 0 and not result.stdout, f"bad input passes: {payload!r}")
    check(not os.path.exists(os.path.join(home, "state")), "bad input saves no state")


def test_line_threshold(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 29)
    check(not stop(home, repo, "s"), "29 lines pass")
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "30 lines block")


def test_marker_word_rules(home):
    for number, (line, expected) in enumerate((("# HACK", True), ("hackathon", False), ("shack", False), ("++ hack", True))):
        repo = new_repo(home, f"repo{number}")
        session = f"s{number}"
        run_hook(home, repo, session, "SessionStart")
        write_lines(repo, "a.rb", 2, line)
        check(stop(home, repo, session) == expected, f"marker rule for {line!r}")


def test_deleted_marker_does_not_block(home):
    repo = new_repo(home)
    write_lines(repo, "a.rb", 2, "# hack")
    commit(repo)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 1, "x = 1")
    check(not stop(home, repo, "s"), "removing a marker line does not block")


def test_marker_in_test_file_beside_code(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "spec/a_spec.rb", 2, "# hack")
    write_lines(repo, "a.rb", 2)
    check(not stop(home, repo, "s"), "marker in a test file beside clean code does not block")


def test_rename_counts_both_sides(home):
    repo = new_repo(home)
    write_lines(repo, "old.rb", 20)
    commit(repo)
    run_hook(home, repo, "s", "SessionStart")
    os.rename(os.path.join(repo, "old.rb"), os.path.join(repo, "new.rb"))
    check(stop(home, repo, "s"), "rename counts deleted and added lines")


def test_big_ignored_file_keeps_hook_on(home):
    repo = new_repo(home)
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, ".gitignore", 1, "dump.bin")
    with open(os.path.join(repo, "dump.bin"), "wb") as file:
        file.truncate(51 * 1024 * 1024)
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "big ignored file does not turn the hook off")


def test_session_cannot_leave_state_dir(home):
    repo = new_repo(home)
    run_hook(home, repo, "../escape", "SessionStart")
    check(os.listdir(os.path.join(home, "state")) == ["escape"], "session id cannot leave the state folder")


def test_session_start_outside_git(home):
    plain = os.path.join(home, "plain")
    write_lines(plain, "a.rb", 1)
    run_hook(home, plain, "s", "SessionStart")
    check(not os.path.exists(os.path.join(home, "state", "s")), "SessionStart outside git saves no state")


def test_corrupt_state_uses_head(home):
    repo = new_repo(home)
    os.makedirs(os.path.join(home, "state"))
    with open(os.path.join(home, "state", "s"), "wb") as file:
        file.write(b"\xff\x00junk")
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "corrupt state falls back to HEAD")


def test_non_utf8_cwd(home):
    repo = os.fsdecode(os.path.join(os.fsencode(home), b"caf\xe9"))
    os.makedirs(repo)
    sh(repo, "init", "-q")
    write_lines(repo, "a.rb", 30)
    payload = b'{"session_id":"s","hook_event_name":"Stop","cwd":"' + os.fsencode(repo) + b'"}'
    check(blocked(run_raw(home, payload).stdout.decode()), "non-UTF-8 byte in cwd works")


def test_newline_in_repo_name(home):
    repo = new_repo(home, "repo\n")
    run_hook(home, repo, "s", "SessionStart")
    write_lines(repo, "a.rb", 30)
    check(stop(home, repo, "s"), "repo name that ends in a newline works")


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        with tempfile.TemporaryDirectory() as home:
            test(home)
    print(f"broken-windows hook: {len(tests)} checks passed")


if __name__ == "__main__":
    main()
