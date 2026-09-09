"""Offline real Git publication test, with deliberately incomplete producer files."""

import json
from pathlib import Path

import yaml

from tools.publish_daily_close_failure import git, publish


def test_failure_publication_excludes_incomplete_market_packet(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    root = tmp_path / "producer checkout"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    tracked = root / "tracked.txt"
    tracked.write_text("base", encoding="utf-8")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-m", "fixture base")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "origin", "main")
    tracked.write_text("uncommitted producer change", encoding="utf-8")
    folder = root / "data/daily_runs"
    folder.mkdir(parents=True)
    receipt = {
        "date": "2026-09-09",
        "run_id": "fixture-run",
        "workflow_run_attempt": "1",
        "status": "FAILED",
        "credential_health": {"tushare_token": "MISSING"},
        "blockers": [{"error": "MISSING_TUSHARE_TOKEN"}],
    }
    (folder / "2026-09-09.json").write_text(json.dumps(receipt), encoding="utf-8")
    (folder / "2026-09-08.json").write_text(
        json.dumps(receipt | {"date": "2026-09-08", "run_id": "older-run"}), encoding="utf-8"
    )
    packet = root / "data/market_packets/2026-09-09.json"
    packet.parent.mkdir(parents=True)
    packet.write_text('{"INCOMPLETE_FIXTURE": true}', encoding="utf-8")
    assert publish(root, "fixture-run") == "PUSHED"
    files = git(remote, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert files == ["data/daily_runs/2026-09-09.json", "tracked.txt"]
    assert json.loads(git(remote, "show", "main:data/daily_runs/2026-09-09.json")) == receipt
    assert tracked.read_text(encoding="utf-8") == "uncommitted producer change"
    assert packet.exists()
    assert publish(root, "fixture-run") == "UNCHANGED"


def test_workflow_failure_path_preserves_red_result_and_diagnostics():
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/daily-close.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["daily-close"]["steps"]
    close = next(row for row in steps if row.get("id") == "close")
    assert not close.get("continue-on-error", False)
    assert '[[ "$code" == "3" ]] && exit 3' in close["run"]
    failure = next(
        row for row in steps if row.get("name") == "Commit failed daily close manifest only"
    )
    assert "always()" in failure["if"] and "steps.close.outcome == 'failure'" in failure["if"]
    assert failure["run"] == "python tools/publish_daily_close_failure.py"
    upload = next(row for row in steps if row.get("name") == "Upload failure diagnostics")
    assert upload["if"] == "failure()"
    assert upload["with"]["path"].strip() == "data/daily_runs/"
