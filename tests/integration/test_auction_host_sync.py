"""Real local bare-Git integration; no market network calls."""

import hashlib
import json
from datetime import date

import pytest

from src.auction import git_sync as sync
from src.auction.host_lock import AlreadyRunning, auction_lock
from src.auction.production import read, update_run, write

DAY = date(2026, 9, 9)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "_proxy", lambda: None)
    remote = tmp_path / "remote.git"
    remote.mkdir()
    sync.git(remote, "init", "--bare", "--initial-branch=main")
    root = tmp_path / "working copy"
    root.mkdir()
    sync.git(root, "init", "--initial-branch=main")
    sync.git(root, "config", "user.email", "fixture@example.invalid")
    sync.git(root, "config", "user.name", "Fixture")
    (root / ".gitattributes").write_text("data/auction_packets/*.json -text\n", encoding="utf-8")
    sync.git(root, "add", ".gitattributes")
    sync.git(root, "commit", "--allow-empty", "-m", "fixture base")
    sync.git(root, "remote", "add", "origin", str(remote))
    sync.git(root, "push", "-u", "origin", "main")
    for folder, suffix in (
        ("auction_packets", ""),
        ("auction_packets", "_compact"),
        ("auction_raw_frozen", ""),
    ):
        write(root / "data" / folder / f"{DAY}{suffix}.json", {"scope": "FIXTURE_ONLY"})
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    update_run(
        root,
        DAY,
        "REPORT_READY",
        packet_sha256=digest(root / f"data/auction_packets/{DAY}.json"),
        compact_sha256=digest(root / f"data/auction_packets/{DAY}_compact.json"),
        raw_sha256=digest(root / f"data/auction_raw_frozen/{DAY}.json"),
    )
    return root, remote


def test_pushes_report_and_success_receipt_without_raw_mutation(repos):
    root, remote = repos
    digest = sync.verify_frozen(root, DAY)
    assert sync.persist(root, DAY, require_frozen=True) == "PUSHED"
    published = json.loads(sync.git(remote, "show", f"main:data/auction_runs/{DAY}.json"))
    assert published["status"] == "PUSHED"
    assert sync.verify_frozen(root, DAY) == digest
    assert "auction_raw_frozen" not in sync.git(remote, "ls-tree", "-r", "--name-only", "main")


def test_failed_push_can_retry_existing_commit_without_collection(repos, monkeypatch):
    root, remote = repos
    real_git = sync.git

    def failing(root, *args, **kwargs):
        if args[0] == "push":
            raise RuntimeError("FIXTURE_PUSH_OFFLINE")
        return real_git(root, *args, **kwargs)

    monkeypatch.setattr(sync, "git", failing)
    with pytest.raises(RuntimeError, match="OFFLINE"):
        sync.persist(root, DAY, require_frozen=True)
    assert read(root / f"data/auction_runs/{DAY}.json")["status"] == "GIT_SYNC_FAILED"
    assert sync.verify_frozen(root, DAY)
    monkeypatch.setattr(sync, "git", real_git)
    assert sync.persist(root, DAY, require_frozen=True) == "PUSHED"
    assert (
        json.loads(real_git(remote, "show", f"main:data/auction_runs/{DAY}.json"))["status"]
        == "PUSHED"
    )


@pytest.mark.parametrize(
    "folder,suffix",
    [("auction_packets", ""), ("auction_packets", "_compact"), ("auction_raw_frozen", "")],
)
def test_retry_rejects_tampering_before_push(repos, folder, suffix):
    root, remote = repos
    before = sync.git(remote, "rev-parse", "main")
    write(root / "data" / folder / f"{DAY}{suffix}.json", {"tampered": True})
    with pytest.raises(ValueError):
        sync.persist(root, DAY, require_frozen=True)
    assert sync.git(remote, "rev-parse", "main") == before


def test_preexisting_staged_work_not_committed(repos):
    root, remote = repos
    write(root / "unrelated.json", {"user": True})
    sync.git(root, "add", "unrelated.json")
    with pytest.raises(RuntimeError, match="STAGED"):
        sync.persist(root, DAY)
    assert sync.git(root, "diff", "--cached", "--name-only") == "unrelated.json"
    assert "unrelated" not in sync.git(remote, "ls-tree", "-r", "--name-only", "main")


def test_remote_advance_rebases_only_local_data_commit(repos):
    root, remote = repos
    other = root.parent / "other"
    sync.git(root.parent, "clone", str(remote), str(other))
    sync.git(other, "config", "user.email", "fixture@example.invalid")
    sync.git(other, "config", "user.name", "Fixture")
    sync.git(other, "commit", "--allow-empty", "-m", "remote advance")
    sync.git(other, "push", "origin", "main")
    assert sync.persist(root, DAY) == "PUSHED"
    assert "remote advance" in sync.git(remote, "log", "--format=%s")


def test_os_lock_prevents_duplicate_and_releases(tmp_path):
    with auction_lock(tmp_path, DAY), pytest.raises(AlreadyRunning), auction_lock(tmp_path, DAY):
        pytest.fail("duplicate collector")
    with auction_lock(tmp_path, DAY):
        pass


def test_stage_history_survives_failure(tmp_path):
    for stage in (
        "SCHEDULER_STARTED",
        "PREFLIGHT_RUNNING",
        "SOURCE_CONNECTED",
        "COLLECTING",
        "COLLECTION_FAILED",
    ):
        update_run(tmp_path, DAY, stage)
    receipt = read(tmp_path / f"data/auction_runs/{DAY}.json")
    assert [row["event"] for row in receipt["stage_history"]] == [
        "SCHEDULER_STARTED",
        "PREFLIGHT_RUNNING",
        "SOURCE_CONNECTED",
        "COLLECTING",
        "COLLECTION_FAILED",
    ]
    assert len((tmp_path / f"data/auction_logs/{DAY}/live.log").read_text().splitlines()) == 5


def test_crlf_frozen_bytes_survive_windows_autocrlf(repos):
    root, remote = repos
    sync.git(root, "config", "core.autocrlf", "true")
    (root / ".gitattributes").write_text("data/auction_packets/*.json -text\n", encoding="utf-8")
    sync.git(root, "add", ".gitattributes")
    sync.git(root, "commit", "--allow-empty", "-m", "fixture attributes")
    sync.git(root, "push", "origin", "main")
    packet = root / f"data/auction_packets/{DAY}.json"
    packet.write_bytes(b'{\r\n  "fixture": true\r\n}')
    update_run(
        root, DAY, "REPORT_READY", packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest()
    )
    assert sync.persist(root, DAY) == "PUSHED"
    assert sync.git(remote, "rev-parse", f"main:data/auction_packets/{DAY}.json") == sync.git(
        root, "hash-object", "--no-filters", str(packet)
    )


def test_filter_mismatch_blocks_commit(repos):
    root, remote = repos
    (root / ".gitattributes").write_text("data/auction_packets/*.json text\n", encoding="utf-8")
    sync.git(root, "config", "core.autocrlf", "true")
    before = sync.git(remote, "rev-parse", "main")
    packet = root / f"data/auction_packets/{DAY}.json"
    packet.write_bytes(b'{\r\n  "fixture": true\r\n}')
    update_run(
        root, DAY, "REPORT_READY", packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="FILTER_CHANGED"):
        sync.persist(root, DAY)
    assert sync.git(remote, "rev-parse", "main") == before
