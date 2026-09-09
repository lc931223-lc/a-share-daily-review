"""Data-only Git distribution. A failed push never removes local frozen facts."""

import hashlib
import os
import re
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from src.auction.production import TZ, log_event, read, resume_report, update_run


def _proxy():
    explicit = os.getenv("AUCTION_GIT_PROXY")
    if explicit:
        return explicit
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
                server = winreg.QueryValueEx(key, "ProxyServer")[0]
            if enabled and re.fullmatch(r"(?:127\.0\.0\.1|localhost):\d+", server):
                return "http://" + server
        except OSError:
            pass
    return None


def _redact(text):
    return re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", text)


def git(root, *args, day=None):
    configured = read(root / "data/auction_host_config.json", {}).get("git_executable")
    executable = configured or shutil.which("git")
    if not executable or not Path(executable).is_file():
        raise FileNotFoundError(
            "GIT_EXECUTABLE_UNAVAILABLE: reinstall auction tasks from a shell with Git"
        )
    command = [executable, "-c", "http.version=HTTP/1.1"]
    proxy = _proxy()
    if proxy:
        command += ["-c", f"http.proxy={proxy}"]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    try:
        result = subprocess.run(
            command + list(args),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=45,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
    except Exception as exc:
        if day:
            log_event(root, day, "git_command", arguments=list(args), error_type=type(exc).__name__)
        raise
    if day:
        log_event(
            root,
            day,
            "git_command",
            arguments=list(args),
            returncode=result.returncode,
            stdout=_redact(result.stdout)[-12000:],
            stderr=_redact(result.stderr)[-12000:],
        )
    if result.returncode:
        raise RuntimeError(f"GIT_SYNC_FAILED {args[0]}: {_redact(result.stderr)[-2000:]}")
    return result.stdout.strip()


def refresh(root):
    # A new local run receipt must not prevent fetching the prior formal review.
    # Git's ff-only merge itself refuses to overwrite conflicting untracked files.
    if git(root, "diff", "--name-only") or git(root, "diff", "--cached", "--name-only"):
        return "SKIPPED_DIRTY_WORKTREE"
    git(root, "fetch", "origin", "main")
    git(root, "merge", "--ff-only", "origin/main")
    return "UPDATED"


def verify_frozen(root, day):
    if not resume_report(root, day):
        raise ValueError("NO_FROZEN_REPORT")
    receipt = read(root / "data/auction_runs" / f"{day}.json", {})
    compact = root / "data/auction_packets" / f"{day}_compact.json"
    if (
        not receipt.get("compact_sha256")
        or hashlib.sha256(compact.read_bytes()).hexdigest() != receipt["compact_sha256"]
    ):
        raise ValueError("compact SHA missing or mismatch")
    raw = root / "data/auction_raw_frozen" / f"{day}.json"
    if not raw.exists():
        raise ValueError("NO_LOCAL_RAW_FREEZE")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    if receipt.get("raw_sha256") and receipt["raw_sha256"] != digest:
        raise ValueError("raw SHA mismatch")
    return digest


def persist(root, day, *, require_frozen=False):
    def run(*args):
        return git(root, *args, day=day)

    try:
        receipt = read(root / "data/auction_runs" / f"{day}.json", {})
        raw_sha = (
            verify_frozen(root, day) if require_frozen or receipt.get("packet_sha256") else None
        )
        update_run(
            root,
            day,
            "GIT_SYNC_PENDING",
            status="GIT_SYNC_PENDING",
            git_sync_started_at=datetime.now(TZ).isoformat(),
            local_report_status="LOCAL_REPORT_READY" if raw_sha else "UNAVAILABLE",
            **({"raw_sha256": raw_sha} if raw_sha else {}),
        )
        run("status", "--short", "--branch")
        run("remote", "-v")
        run("branch", "--show-current")
        if run("diff", "--cached", "--name-only"):
            raise RuntimeError("PREEXISTING_STAGED_CHANGES")
        run("fetch", "origin", "main")
        # Only retry our own data commits. Never publish unrelated local work.
        ahead = run("log", "origin/main..HEAD", "--format=%s")
        if any(
            not line.startswith("data: persist scheduled auction ") for line in ahead.splitlines()
        ):
            raise RuntimeError("LOCAL_COMMITS_REQUIRE_REVIEW")
        ahead_paths = run("diff", "--name-only", "origin/main...HEAD")
        allowed = re.compile(
            r"^data/auction_(?:packets|runs|post_open|eod|preflight)/\d{4}-\d{2}-\d{2}(?:_compact)?\.json$"
        )
        if any(not allowed.fullmatch(path) for path in ahead_paths.splitlines()):
            raise RuntimeError("NON_DATA_LOCAL_COMMITS_REQUIRE_REVIEW")
        folders = (
            "auction_packets",
            "auction_runs",
            "auction_post_open",
            "auction_eod",
            "auction_preflight",
        )
        paths = [
            f"data/{folder}/{day}{suffix}.json"
            for folder in folders
            for suffix in ("", "_compact")
            if (root / f"data/{folder}/{day}{suffix}.json").exists()
            and (folder != "auction_packets" or raw_sha)
        ]

        def commit_paths():
            run("add", "-f", "--", *paths)
            staged = run("diff", "--cached", "--name-only")
            if set(staged.splitlines()) - set(paths):
                raise RuntimeError("UNEXPECTED_STAGED_CHANGES")
            if staged:
                run("commit", "-m", f"data: persist scheduled auction {day}")

        def push():
            for attempt in range(2):
                try:
                    run("push", "origin", "HEAD:main")
                    return
                except RuntimeError:
                    if attempt:
                        raise
                    run("fetch", "origin", "main")
                    try:
                        run("rebase", "origin/main")
                    except Exception:
                        # Abort only the rebase just started by this function.
                        if (root / ".git/rebase-merge").exists() or (
                            root / ".git/rebase-apply"
                        ).exists():
                            run("rebase", "--abort")
                        raise

        commit_paths()
        push()
        pushed_sha = run("rev-parse", "HEAD")
        update_run(
            root,
            day,
            "PUSHED",
            status="PUSHED",
            sync_status="PUSHED",
            git_sync_result="PASS",
            push_result="PASS",
            distributed_commit=pushed_sha,
            git_sync_completed_at=datetime.now(TZ).isoformat(),
        )
        # Publish the successful distribution receipt too. It refers to the first
        # acknowledged commit, not to its own self-referential hash.
        commit_paths()
        push()
        return "PUSHED"
    except Exception as exc:
        update_run(
            root,
            day,
            "GIT_SYNC_FAILED",
            status="GIT_SYNC_FAILED",
            sync_status="GIT_SYNC_FAILED",
            git_sync_result="FAIL",
            push_result="FAILED_OR_NOT_ATTEMPTED",
            sync_exception_type=type(exc).__name__,
            sync_exception_traceback=traceback.format_exc(),
        )
        raise
