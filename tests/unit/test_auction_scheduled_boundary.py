from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.auction import git_sync
from src.auction.production import read, update_run
from tools import run_auction_scheduled as runner

DAY = date(2026, 9, 9)


@pytest.fixture
def host(tmp_path, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 9, 9, 13, tzinfo=ZoneInfo("Asia/Shanghai"))

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "datetime", Clock)
    monkeypatch.setattr(git_sync, "git", lambda *args, **kwargs: "fixture")
    return tmp_path


def test_watchdog_launches_once_and_receipt_precedes_preflight(host, monkeypatch):
    calls = []

    def execute(args, root, day):
        assert read(root / f"data/auction_runs/{day}.json")["stage"] == "SCHEDULER_STARTED"
        calls.append(args.stage)
        update_run(root, day, "COLLECTING")
        return 0

    monkeypatch.setattr(runner, "execute", execute)
    assert runner.main(["--stage", "watchdog"]) == 0
    assert runner.main(["--stage", "watchdog"]) == 0
    assert calls == ["live"]


def test_preflight_exception_is_durable_before_0915(host, monkeypatch):
    def fail(*args):
        raise ValueError("fixture missing review")

    monkeypatch.setattr(runner, "execute", fail)
    assert runner.main(["--stage", "live"]) == 1
    record = read(host / f"data/auction_runs/{DAY}.json")
    assert record["status"] == "PREFLIGHT_FAILED"
    assert "fixture missing review" in record["exception_traceback"]
    assert record["stage_history"][0]["event"] == "SCHEDULER_STARTED"


def test_unavailable_git_does_not_block_local_collection(host, monkeypatch):
    def fail(*args, **kwargs):
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(git_sync, "git", fail)
    calls = []
    monkeypatch.setattr(runner, "execute", lambda *args: calls.append(True) or 0)
    assert runner.main(["--stage", "live"]) == 0
    assert calls == [True]
    assert "repository_metadata_unavailable" in (
        host / f"data/auction_logs/{DAY}/live.log"
    ).read_text(encoding="utf-8")
