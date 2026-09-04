from __future__ import annotations

import subprocess
from pathlib import Path

from tools.git_sync_check import find_sensitive_paths, run_git_sync_check


class FakeGitRunner:
    def __init__(self, *, branch="main", local="local", remote="local", dirty="", push_return=0, fetch_return=0):
        self.branch = branch
        self.local = local
        self.remote = remote
        self.dirty = dirty
        self.push_return = push_return
        self.fetch_return = fetch_return
        self.commands: list[list[str]] = []

    def run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        self.commands.append(args)
        command = args[1:]
        if command == ["remote", "get-url", "origin"]:
            return self._ok("https://github.com/lc931223-lc/a-share-daily-review.git\n")
        if command == ["branch", "--show-current"]:
            return self._ok(f"{self.branch}\n")
        if command == ["fetch", "origin"]:
            return self._ok("") if self.fetch_return == 0 else self._fail("fetch failed")
        if command == ["status", "--porcelain"]:
            return self._ok(self.dirty)
        if command == ["rev-parse", "HEAD"]:
            return self._ok(f"{self.local}\n")
        if command == ["rev-parse", "origin/main"]:
            return self._ok(f"{self.remote}\n")
        if command == ["merge-base", "--is-ancestor", "origin/main", "HEAD"]:
            return self._ok("") if self.remote in {self.local, "base"} else self._fail()
        if command == ["merge-base", "--is-ancestor", "HEAD", "origin/main"]:
            return self._ok("") if self.local in {self.remote, "base"} else self._fail()
        if command == ["push", "origin", "main"]:
            if self.push_return == 0:
                self.remote = self.local
            return self._ok("") if self.push_return == 0 else subprocess.CompletedProcess(args, self.push_return, "", "push failed")
        return self._fail("unexpected command")

    def _ok(self, stdout: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git"], 0, stdout, "")

    def _fail(self, stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git"], 1, "", stderr)


def test_git_sync_does_nothing_when_synced(tmp_path):
    runner = FakeGitRunner(local="same", remote="same")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.sync_status == "SYNCED"
    assert result.push_result == "NOT_NEEDED"
    assert ["git", "push", "origin", "main"] not in runner.commands


def test_git_sync_pushes_clean_local_main_when_ahead(tmp_path):
    runner = FakeGitRunner(local="local", remote="base")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 0
    assert result.push_result == "SUCCESS"
    assert ["git", "push", "origin", "main"] in runner.commands


def test_git_sync_dirty_worktree_does_not_commit_or_push(tmp_path):
    runner = FakeGitRunner(local="local", remote="base", dirty=" M src/file.py\n")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 1
    assert result.sync_status == "DIRTY_WORKTREE"
    assert ["git", "push", "origin", "main"] not in runner.commands


def test_git_sync_remote_ahead_does_not_pull(tmp_path):
    runner = FakeGitRunner(local="base", remote="remote")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 2
    assert result.sync_status == "REMOTE_AHEAD"
    assert ["git", "pull", "--rebase", "origin", "main"] not in runner.commands


def test_git_sync_diverged_does_not_auto_resolve(tmp_path):
    runner = FakeGitRunner(local="local", remote="remote")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 3
    assert result.sync_status == "DIVERGED"
    assert ["git", "push", "origin", "main"] not in runner.commands


def test_git_sync_push_failure_returns_error(tmp_path):
    runner = FakeGitRunner(local="local", remote="base", push_return=1)
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 4
    assert result.push_result == "FAILED"


def test_git_sync_non_main_branch_does_not_push_to_main(tmp_path):
    runner = FakeGitRunner(branch="codex/work", local="local", remote="base")
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 0
    assert result.sync_status == "NON_MAIN_BRANCH"
    assert ["git", "push", "origin", "main"] not in runner.commands


def test_sensitive_paths_are_detected_for_commit_safety():
    status = "?? .env\nA  data/raw/market_packets/a.json\nM  src/app.py\n"
    assert find_sensitive_paths(status) == [".env", "data/raw/market_packets/a.json"]


def test_git_error_preserves_known_local_state(tmp_path):
    runner = FakeGitRunner(branch="main", local="local", remote="remote", fetch_return=1)
    result = run_git_sync_check(tmp_path, runner=runner)
    assert result.return_code == 5
    assert result.branch == "main"
    assert result.local_head == "local"
    assert result.origin_main == "remote"
