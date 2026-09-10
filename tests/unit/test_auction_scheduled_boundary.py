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


def test_historical_date_cannot_enable_live_collection(host):
    with pytest.raises(SystemExit):
        runner.main(["--stage", "live", "--dry-run-date", "2026-09-08"])
    assert not (host / "data/auction_runs/2026-09-09.json").exists()


def test_dry_run_date_is_isolated_from_production(host, monkeypatch):
    from tools import auction_preflight, probe_auction_host_source

    seen = []

    def preflight(root, *, now):
        seen.append(now.date())
        return {"status": "PASS", "previous_review_status": "READY"}

    monkeypatch.setattr(auction_preflight, "preflight", preflight)
    monkeypatch.setattr(
        probe_auction_host_source,
        "probe",
        lambda: {
            "connect_result": "PASS",
            "success_count": 15,
        },
    )
    assert runner.main(["--stage", "live", "--dry-run", "--dry-run-date", "2026-09-08"]) == 0
    assert seen == [date(2026, 9, 8)]
    assert not (host / "data/auction_packets").exists()
    assert not (host / "data/auction_runs/2026-09-08.json").exists()
    result = read(next((host / "data/auction_dry_runs").glob("*/result.json")))
    assert result["scope"] == "HOST_DIAGNOSTIC_NOT_LIVE_ACCEPTANCE"
    assert result["diagnostic_observed_at"].startswith("2026-09-09")


@pytest.mark.parametrize("review_ready,expected", [(False, "FAIL"), (True, "PASS")])
def test_preflight_requires_review_even_when_transport_connects(
    tmp_path, monkeypatch, review_ready, expected
):
    from types import SimpleNamespace
    from tools import auction_preflight

    monkeypatch.setattr(
        auction_preflight,
        "load_trading_calendar",
        lambda *a, **kw: [
            SimpleNamespace(cal_date=DAY, is_open=True),
        ],
    )
    monkeypatch.setattr(
        auction_preflight,
        "load_previous_context",
        lambda *a: {
            "previous_trade_date": "2026-09-08",
            "official_review_loaded": review_ready,
            "review_context_loaded": True,
            "market_packet_loaded": True,
            "report_status": "fixture",
        },
    )
    result = auction_preflight.preflight(
        tmp_path,
        now=datetime(2026, 9, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        source_factory=lambda: SimpleNamespace(connect=lambda: None, close=lambda: None),
    )
    assert result["status"] == expected
    assert ("PREVIOUS_FORMAL_REVIEW_UNAVAILABLE" in result["blockers"]) == (not review_ready)
