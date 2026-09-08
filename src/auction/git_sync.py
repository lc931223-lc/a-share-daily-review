"""Bounded, explicit data-only synchronization for the local scheduler."""

import subprocess


def git(root, *args):
    result = subprocess.run(
        ["git", "-c", "http.version=HTTP/1.1", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=25,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        raise RuntimeError("GIT_SYNC_FAILED")
    return result.stdout.strip()


def refresh(root):
    if git(root, "status", "--porcelain"):
        return "SKIPPED_DIRTY_WORKTREE"
    git(root, "fetch", "origin", "main")
    git(root, "merge", "--ff-only", "origin/main")
    return "UPDATED"


def persist(root, day):
    if git(root, "diff", "--cached", "--name-only"):
        return "SKIPPED_PREEXISTING_STAGED_CHANGES"
    if git(root, "rev-parse", "HEAD") != git(root, "rev-parse", "origin/main"):
        return "SKIPPED_LOCAL_COMMITS_REQUIRE_REVIEW"
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
    ]
    if not paths:
        return "NO_ARTIFACTS"
    git(root, "add", "-f", "--", *paths)
    if not git(root, "diff", "--cached", "--name-only"):
        return "UNCHANGED"
    git(root, "commit", "-m", f"data: persist scheduled auction {day}")
    # No force push or automatic conflict resolution. Local data remains recoverable.
    git(root, "push", "origin", "HEAD:main")
    return "PUSHED"
