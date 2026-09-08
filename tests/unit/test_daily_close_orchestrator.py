from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.daily_close.orchestrator import ARTIFACTS, DailyCloseOrchestrator
from src.market_packet.trading_calendar import TradingCalendarDay

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _schemas(root: Path):
    folder = root / "schemas"
    folder.mkdir()
    for _, schema in ARTIFACTS.values():
        (folder / schema).write_text('{"type":"object"}', encoding="utf-8")
    source = Path(__file__).resolve().parents[2] / "schemas" / "daily_run_manifest.schema.json"
    (folder / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _calendar():
    return [
        TradingCalendarDay(date(2026, 9, 4), True),
        TradingCalendarDay(date(2026, 9, 5), False),
        TradingCalendarDay(date(2026, 9, 6), False),
        TradingCalendarDay(date(2026, 9, 7), True),
        TradingCalendarDay(date(2026, 9, 8), True),
    ]


def _write_artifact(root, name, target, *, source_date=None, quality="PASS"):
    folder, _ = ARTIFACTS[name]
    path = root / "data" / folder / f"{target.isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"trade_date": (source_date or target).isoformat()},
        "data_quality": {"status": quality},
    }
    if name == "market_packet":
        payload["data_quality"] |= {
            "checks": [{"item": "全市场日线", "status": "PASS"}],
            "sources": [],
        }
    if name == "review_context":
        payload["source_manifest"] = {
            key: {"data_date": target.isoformat(), "status": "AVAILABLE"}
            for key in (
                "market_packet",
                "review_intelligence",
                "inflection_scanner",
                "capital_preference",
            )
        } | {"auction_packet": {"status": "UNAVAILABLE", "data_date": None}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _runners(root, calls, fail_market_once=False):
    failed = {"done": False}

    def runner(name):
        def run(target):
            calls.append((name, target.isoformat()))
            if name == "market_packet" and fail_market_once and not failed["done"]:
                failed["done"] = True
                raise RuntimeError("temporary source failure")
            _write_artifact(root, name, target)

        return run

    output = {name: runner(name) for name in ARTIFACTS}
    output["feedback"] = lambda target: {
        "status": "PASS",
        "as_of": target.isoformat(),
        "pending_count": 0,
        "newly_validated_count": 0,
        "still_waiting_count": 0,
        "validated_count": 1,
        "cycles": [],
    }
    return output


def test_non_trading_day_and_market_not_closed_do_not_run_steps(tmp_path):
    _schemas(tmp_path)
    calls = []
    weekend = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    ).run_date(date(2026, 9, 6))
    assert weekend["status"] == "NON_TRADING_DAY"
    before_close = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 14, 59, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    ).run_date(date(2026, 9, 8))
    assert before_close["status"] == "MARKET_NOT_CLOSED"
    assert calls == []


def test_normal_run_retries_and_rerun_reuses_same_date_artifacts(tmp_path):
    _schemas(tmp_path)
    calls = []
    pipeline = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls, fail_market_once=True),
    )
    first = pipeline.run_date(date(2026, 9, 8))
    first_call_count = len(calls)
    second = pipeline.run_date(date(2026, 9, 8))
    assert first["status"] == "PASS"
    assert first["steps"]["market_packet"]["retry_count"] == 1
    assert second["steps"]["review_context"]["reused"] is True
    assert len(calls) == first_call_count


def test_stale_artifact_is_rejected_and_regenerated(tmp_path):
    _schemas(tmp_path)
    calls = []
    _write_artifact(
        tmp_path,
        "market_packet",
        date(2026, 9, 8),
        source_date=date(2026, 9, 7),
    )
    pipeline = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    )
    result = pipeline.run_date(date(2026, 9, 8))
    assert result["status"] == "PASS"
    assert ("market_packet", "2026-09-08") in calls
    assert result["steps"]["market_packet"]["source_date"] == "2026-09-08"


def test_future_dated_market_source_is_rejected_and_regenerated(tmp_path):
    _schemas(tmp_path)
    calls = []
    _write_artifact(tmp_path, "market_packet", date(2026, 9, 8))
    path = tmp_path / "data/market_packets/2026-09-08.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data_quality"]["sources"] = [
        {"dataset": "bad_source", "data_date": "2026-09-09"}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    ).run_date(date(2026, 9, 8))
    assert result["status"] == "PASS"
    assert ("market_packet", "2026-09-08") in calls


def test_plaintext_secret_scan_is_a_hard_failure(tmp_path):
    _schemas(tmp_path)
    calls = []
    source = tmp_path / "src"
    source.mkdir()
    (source / "bad.py").write_text(
        'api_key = "' + ("x" * 32) + '"', encoding="utf-8"
    )
    result = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    ).run_date(date(2026, 9, 8))
    assert result["status"] == "FAILED"
    assert result["blockers"][0]["step"] == "production_readiness"


def test_backfill_runs_missing_trading_days_in_order(tmp_path):
    _schemas(tmp_path)
    calls = []
    _write_artifact(tmp_path, "review_context", date(2026, 9, 4))
    pipeline = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 8, 16, tzinfo=SHANGHAI),
        calendar_loader=lambda _: _calendar(),
        runners=_runners(tmp_path, calls),
    )
    results = pipeline.run_latest(backfill_missing=True)
    assert [row["date"] for row in results] == ["2026-09-07", "2026-09-08"]
    assert all(row["status"] == "PASS" for row in results)
