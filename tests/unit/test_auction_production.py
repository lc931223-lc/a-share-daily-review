import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from src.auction.conditions import evaluate
from src.auction.pipeline import AuctionPipeline
from src.auction.production import save_post_open, timeliness, update_run, resume_report, write
from src.auction.score_rules import catalyst_component, market_component
from src.auction.scoring import score_stock
from src.formal_review.delivery import update_queue
from src.market_packet.trading_calendar import TradingCalendarDay

TZ = ZoneInfo("Asia/Shanghai")
DAY = date(2026, 9, 9)


@pytest.mark.parametrize(
    "text,negative",
    [
        ("业绩增长", False),
        ("业绩预增", False),
        ("扭亏为盈", False),
        ("业绩预减", True),
        ("净利润同比下降", True),
    ],
)
def test_negative_earnings_semantics(text, negative):
    result = score_stock(
        {"ts_code": "000001.SZ", "quality_status": "PASS"},
        {},
        {},
        None,
        [{"stock_code": "000001.SZ", "title": text}],
    )
    risks = [r for r in result["risks"] if r["risk_type"] == "EARNINGS_RISK"]
    assert bool(risks) == negative
    if risks:
        assert risks[0]["risk_rule_id"] and risks[0]["matched_evidence"]


def test_a_level_is_not_automatically_fifteen():
    base = dict(
        evidence_level="A",
        stock_code="000001.SZ",
        published_at="2026-09-09T08:00:00+08:00",
        as_of="2026-09-09T09:25:00+08:00",
    )
    assert catalyst_component(None, None, [base | {"event_type": "ROUTINE"}])["score"] == 10
    assert catalyst_component(None, None, [base | {"event_type": "ORDER_MAJOR"}])["score"] == 15
    assert (
        catalyst_component(
            None, None, [base | {"evidence_level": "D", "event_type": "ORDER_MAJOR"}]
        )["score"]
        == 0
    )
    assert catalyst_component(None, None, [base])["available_max_score"] == 10


def test_market_score_is_shared_global_sample_not_sector():
    previous = {
        "market": {"operability": 50},
        "auction_market": {"sample_size": 20, "positive_gap_ratio": 0.8},
    }
    score = market_component(previous)
    assert score["available_max_score"] == 3.8
    assert (
        score_stock({}, {}, previous, {"positive_gap_ratio": 0.1}, [])["components"][
            "market_environment"
        ]
        == score_stock({}, {}, previous, {"positive_gap_ratio": 0.9}, [])["components"][
            "market_environment"
        ]
    )


@pytest.mark.parametrize(
    "metric,field,value",
    [
        ("auction_gap_pct", "auction_gap_pct", 2),
        ("auction_amount_percentile", "auction_amount_percentile_20d", 80),
        ("post_0920_price_change", "price_change_0920_0925_pct", 2),
        ("sector_positive_ratio", "positive_gap_ratio", 0.8),
        ("leader_strength", "leader_strength", 60),
        ("capacity_strength", "capacity_strength", 60),
    ],
)
def test_structured_condition_executes(metric, field, value):
    check = {"metric": metric, "operator": ">=", "threshold": value, "time_window": "auction"}
    assert evaluate(check, {field: value})[0] == "confirmed"
    assert evaluate(check, {field: value - 1})[0] == "invalidated"
    assert (
        evaluate({"description": "continue stronger"}, {field: value})[1] == "UNSUPPORTED_CONDITION"
    )


def test_relative_and_post_open_and_direction_contract():
    assert (
        evaluate(
            {"metric": "relative_strength", "operator": ">=", "threshold": 1},
            {"auction_gap_pct": 3},
            {"auction_gap_pct": 1},
        )[0]
        == "confirmed"
    )
    check = {
        "metric": "holds_previous_close",
        "operator": "==",
        "threshold": True,
        "time_window": "post_open",
    }
    assert evaluate(check, {"holds_previous_close": True}, window="post_open")[0] == "confirmed"
    assert evaluate(check, {"holds_previous_close": True})[0] == "unverified"
    check = {"metric": "post_0920_order_growth", "operator": ">=", "threshold": 0}
    assert evaluate(check, {"post_0920_order_growth": 0.5})[1] == "ORDER_DIRECTION_UNAVAILABLE"


def test_live_timeliness_late_start_never_passes():
    stats = {
        "collection_start_time": "2026-09-09T09:17:00+08:00",
        "auction_frozen_at": "2026-09-09T09:25:03+08:00",
    }
    result = timeliness(
        DAY,
        stats,
        datetime(2026, 9, 9, 9, 25, 5, tzinfo=TZ),
        [{"snapshot_time": "2026-09-09T09:25:00+08:00"}],
    )
    assert result["status"] == "FAIL"


def test_frozen_resume_and_independent_incremental_post_open(tmp_path):
    packet = tmp_path / "data/auction_packets" / f"{DAY}.json"
    write(packet, {"original_score": 21})
    write(packet.with_name(f"{DAY}_compact.json"), {"original_score": 21})
    before = packet.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    update_run(tmp_path, DAY, "REPORT_READY", packet_sha256=digest)
    assert resume_report(tmp_path, DAY)["reused"]
    for minute, hour in ((35, 9), (0, 10)):
        now = datetime(2026, 9, 9, hour, minute, tzinfo=TZ)
        result = save_post_open(
            tmp_path,
            DAY,
            {
                "observed_at": now.isoformat(),
                "stocks": [{"holds_previous_close": True}],
                "coverage": 1,
            },
            now,
        )
    assert len(result["snapshots"]) == 2
    assert packet.read_bytes() == before
    write(packet, {"original_score": 999})
    with pytest.raises(ValueError, match="hash mismatch"):
        resume_report(tmp_path, DAY)


def test_non_trading_live_skips_without_source_or_packet(tmp_path):
    target = date(2026, 9, 12)
    pipe = AuctionPipeline(
        root=tmp_path,
        calendar_loader=lambda _: [TradingCalendarDay(target, False)],
        source_factory=lambda: pytest.fail("source must not run"),
    )
    result = pipe.run_live(target, now=lambda: datetime(2026, 9, 12, 9, 12, tzinfo=TZ))
    assert result["status"] == "SKIPPED_NON_TRADING_DAY"
    assert not (tmp_path / "data/auction_packets").exists()


def test_queue_waiting_without_fabricated_official(tmp_path):
    queue = update_queue(tmp_path, DAY)
    assert queue["status"] == "WAITING_FOR_CHATGPT_REVIEW"
    assert not (tmp_path / "data/official_reviews" / f"{DAY}.json").exists()


def test_historical_post_open_rejected_before_source(tmp_path):
    pipe = AuctionPipeline(root=tmp_path)
    with pytest.raises(ValueError, match="today"):
        pipe.run_post_open(date(2026, 9, 4), now=datetime(2026, 9, 9, 9, 35, tzinfo=TZ))
