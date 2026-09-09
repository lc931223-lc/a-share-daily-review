"""Publish only this workflow's failed manifests from an isolated clean worktree."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def git(root, *args):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=90,
    ).stdout.strip()


def failed_manifests(root, run_id, attempt):
    selected = []
    for path in (root / "data/daily_runs").glob("????-??-??.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if str(value.get("run_id")) != str(run_id) or str(value.get("workflow_run_attempt")) != str(
            attempt
        ):
            continue
        if value.get("status") not in {"FAILED", "BLOCKED", "MARKET_NOT_CLOSED", "NON_TRADING_DAY"}:
            continue
        if (
            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.get("date", ""))
            or value["date"] != path.stem
        ):
            raise ValueError("failure manifest date mismatch")
        if value.get("credential_health", {}).get("tushare_token") not in {"AVAILABLE", "MISSING"}:
            raise ValueError("invalid credential status")
        selected.append(path)
    return selected


def publish(root, run_id, attempt="1"):
    paths = failed_manifests(root, run_id, attempt)
    if not paths:
        raise RuntimeError("NO_CURRENT_RUN_FAILURE_MANIFEST")
    # Do not rebase a dirty producer checkout containing incomplete Market Packets.
    # Every retry starts from the latest remote and copies only allowlisted receipts.
    for retry in range(3):
        git(root, "fetch", "origin", "main")
        with tempfile.TemporaryDirectory(prefix="daily-failure-") as directory:
            temporary_root = Path(directory).resolve()
            checkout = temporary_root / "checkout"
            git(root, "worktree", "add", "--detach", str(checkout), "origin/main")
            try:
                git(checkout, "config", "user.name", "github-actions[bot]")
                git(
                    checkout,
                    "config",
                    "user.email",
                    "41898282+github-actions[bot]@users.noreply.github.com",
                )
                relative = []
                for source in paths:
                    name = source.relative_to(root).as_posix()
                    destination = checkout / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    relative.append(name)
                git(checkout, "add", "-f", "--", *relative)
                if not git(checkout, "diff", "--cached", "--name-only"):
                    return "UNCHANGED"
                git(checkout, "commit", "-m", "data: record failed daily close production")
                try:
                    git(checkout, "push", "origin", "HEAD:main")
                    return "PUSHED"
                except subprocess.CalledProcessError:
                    if retry == 2:
                        raise
            finally:
                if checkout.resolve().parent != temporary_root:
                    raise RuntimeError("unsafe temporary worktree path")
                git(root, "worktree", "remove", "--force", str(checkout))
    raise RuntimeError("FAILURE_MANIFEST_PUSH_FAILED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id", default=os.getenv("GITHUB_RUN_ID"), required=not os.getenv("GITHUB_RUN_ID")
    )
    args = parser.parse_args()
    try:
        result = publish(
            Path(__file__).resolve().parents[1], args.run_id, os.getenv("GITHUB_RUN_ATTEMPT", "1")
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Subprocess output/environment is deliberately not printed.
        print(f"FAILURE_MANIFEST_PUBLISH_FAILED: {type(exc).__name__}")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
