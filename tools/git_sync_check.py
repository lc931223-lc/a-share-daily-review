from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


EXPECTED_REMOTE = "github.com/lc931223-lc/a-share-daily-review"
SENSITIVE_PATH_PATTERNS = (
    ".env",
    ".env.",
    ".key",
    ".pem",
    ".token",
    "credentials",
    "secrets",
    "data/cache/",
    "data/raw/",
    "tmp/",
    "logs/",
    "output/",
)
SENSITIVE_TEXT_PATTERNS = ("TUSHARE_TOKEN", "IWENCAI_API_KEY", "API_KEY", "SECRET", "TOKEN", "PASSWORD")


class CommandRunner(Protocol):
    def run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        ...


class SubprocessRunner:
    def run(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


@dataclass(frozen=True)
class SyncResult:
    timestamp: str
    repository: str
    branch: str | None
    local_head: str | None
    origin_main: str | None
    working_tree_clean: bool
    sync_status: str
    push_result: str
    return_code: int
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "repository": self.repository,
            "branch": self.branch,
            "local_head": self.local_head,
            "origin_main": self.origin_main,
            "working_tree_clean": self.working_tree_clean,
            "sync_status": self.sync_status,
            "push_result": self.push_result,
            "return_code": self.return_code,
            "message": self.message,
        }


def run_git_sync_check(repo: Path, *, runner: CommandRunner | None = None, dry_run: bool = False) -> SyncResult:
    runner = runner or SubprocessRunner()
    timestamp = datetime.now().isoformat(timespec="seconds")
    repository = "unknown"
    branch: str | None = None
    local_head: str | None = None
    origin_main: str | None = None
    working_tree_clean = True

    try:
        repository = _git(["remote", "get-url", "origin"], repo, runner).strip()
        if EXPECTED_REMOTE not in repository:
            return _result(timestamp, repository, None, None, None, True, "GIT_ERROR", "NOT_ATTEMPTED", 5, "unexpected origin remote")

        branch = _git(["branch", "--show-current"], repo, runner).strip()
        local_head = _git(["rev-parse", "HEAD"], repo, runner).strip()
        origin_main = _git(["rev-parse", "origin/main"], repo, runner).strip()
        _git(["fetch", "origin"], repo, runner)
        porcelain = _git(["status", "--porcelain"], repo, runner)
        working_tree_clean = not porcelain.strip()
        origin_main = _git(["rev-parse", "origin/main"], repo, runner).strip()

        if not working_tree_clean:
            sensitive = find_sensitive_paths(porcelain)
            message = "存在未提交修改，未自动同步。"
            if sensitive:
                message += " 检测到敏感或生成类路径，禁止自动提交。"
            return _result(timestamp, repository, branch, local_head, origin_main, False, "DIRTY_WORKTREE", "NOT_ATTEMPTED", 1, message)

        if branch != "main":
            status = _ahead_status(repo, runner)
            return _result(
                timestamp,
                repository,
                branch,
                local_head,
                origin_main,
                True,
                "NON_MAIN_BRANCH" if status == "LOCAL_AHEAD" else status,
                "NOT_ATTEMPTED",
                0,
                "当前不在 main 分支，兜底任务不会自动 push 到 origin/main。",
            )

        status = _ahead_status(repo, runner)
        if status == "SYNCED":
            return _result(timestamp, repository, branch, local_head, origin_main, True, "SYNCED", "NOT_NEEDED", 0, "已经同步，无需操作。")
        if status == "REMOTE_AHEAD":
            return _result(timestamp, repository, branch, local_head, origin_main, True, "REMOTE_AHEAD", "NOT_ATTEMPTED", 2, "远程存在新提交，需要人工或 Codex 处理。")
        if status == "DIVERGED":
            return _result(timestamp, repository, branch, local_head, origin_main, True, "DIVERGED", "NOT_ATTEMPTED", 3, "本地与远程分叉，需要人工处理。")

        if dry_run:
            return _result(timestamp, repository, branch, local_head, origin_main, True, "LOCAL_AHEAD", "DRY_RUN", 0, "本地 main 领先，dry-run 未 push。")

        push = runner.run(["git", "push", "origin", "main"], repo)
        if push.returncode != 0:
            return _result(timestamp, repository, branch, local_head, origin_main, True, "LOCAL_AHEAD", "FAILED", 4, _clean_error(push.stderr or push.stdout))
        pushed_origin = _git(["rev-parse", "origin/main"], repo, runner).strip()
        return _result(timestamp, repository, branch, local_head, pushed_origin, True, "SYNCED", "SUCCESS", 0, "本地 main 已推送到 origin/main。")
    except RuntimeError as exc:
        return _result(timestamp, repository, branch, local_head, origin_main, working_tree_clean, "GIT_ERROR", "FAILED", 5, _clean_error(str(exc)))


def write_log(result: SyncResult, repo: Path) -> Path:
    log_dir = repo / "logs" / "git_sync"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now().date().isoformat()}.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return log_path


def find_sensitive_paths(status_porcelain: str) -> list[str]:
    found: list[str] = []
    for line in status_porcelain.splitlines():
        path = line[3:].replace("\\", "/").lower() if len(line) > 3 else ""
        if any(pattern in path for pattern in SENSITIVE_PATH_PATTERNS):
            found.append(line[3:])
    return found


def _ahead_status(repo: Path, runner: CommandRunner) -> str:
    local_head = _git(["rev-parse", "HEAD"], repo, runner).strip()
    origin_main = _git(["rev-parse", "origin/main"], repo, runner).strip()
    if local_head == origin_main:
        return "SYNCED"
    remote_ancestor = runner.run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], repo).returncode == 0
    local_ancestor = runner.run(["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], repo).returncode == 0
    if remote_ancestor and not local_ancestor:
        return "LOCAL_AHEAD"
    if local_ancestor and not remote_ancestor:
        return "REMOTE_AHEAD"
    return "DIVERGED"


def _git(args: list[str], repo: Path, runner: CommandRunner) -> str:
    completed = runner.run(["git", *args], repo)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout or f"git {' '.join(args)} failed")
    return completed.stdout


def _result(
    timestamp: str,
    repository: str,
    branch: str | None,
    local_head: str | None,
    origin_main: str | None,
    clean: bool,
    sync_status: str,
    push_result: str,
    return_code: int,
    message: str,
) -> SyncResult:
    return SyncResult(timestamp, repository, branch, local_head, origin_main, clean, sync_status, push_result, return_code, message)


def _clean_error(value: str) -> str:
    cleaned = value
    for pattern in SENSITIVE_TEXT_PATTERNS:
        cleaned = cleaned.replace(pattern, "<redacted-key-name>")
    return cleaned.strip()[:500]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely push committed local main changes to origin/main.")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    result = run_git_sync_check(args.repo.resolve(), dry_run=args.dry_run)
    log_path = write_log(result, args.repo.resolve())
    payload = result.as_dict()
    payload["log_path"] = str(log_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return result.return_code


if __name__ == "__main__":
    sys.exit(main())
