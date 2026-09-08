from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.auction.post_open import PostOpenQuoteRouter, evaluate_post_open
from src.auction.previous_context import load_previous_context
from src.auction.scoring import score_stock
from src.auction.verification import validate_tomorrow_checks
from src.market_packet.trading_calendar import TradingCalendarDay

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _calendar(*values: tuple[str, bool]) -> list[TradingCalendarDay]:
    return [
        TradingCalendarDay(cal_date=date.fromisoformat(day), is_open=is_open)
        for day, is_open in values
    ]


def _summary(**overrides):
    result = {
        "ts_code": "000001.SZ",
        "auction_gap_pct": 1.5,
        "post_0920_price_stability": 0.9,
        "auction_amount_percentile_20d": 80.0,
        "post_0920_order_growth": 0.3,
        "post_0920_order_decay": 0.0,
        "last_1min_order_growth": 0.2,
        "unmatched_direction": "unavailable",
        "unmatched_stability": 0.9,
        "quality_status": "PASS",
        "similar_history_sample_size": 0,
        "similar_history_outcome_count": 0,
    }
    result.update(overrides)
    return result


def _context(level="A"):
    factor = {"factor_id": 21, "name": "订单", "evidence_level": level}
    return {
        "stocks": [
            {
                "ts_code": "000001.SZ",
                "theme": "测试主题",
                "role": "中军",
                "factors": [factor],
            }
        ],
        "mainlines": [
            {
                "mainline_name": "测试主题",
                "mainline_score": 80,
                "factors": [factor],
            }
        ],
    }


def _sector(ratio=0.8):
    return {
        "positive_gap_ratio": ratio,
        "post_0920_positive_ratio": ratio,
        "structure_status": "LEADER_CAPACITY_RESONANCE",
    }


def test_previous_context_uses_exact_previous_open_day_and_never_older_fallback(tmp_path):
    official_dir = tmp_path / "data" / "official_reviews"
    official_dir.mkdir(parents=True)
    (official_dir / "2026-09-04.json").write_text(
        json.dumps({"date": "2026-09-04", "data_kind": "real"}), encoding="utf-8"
    )
    days = _calendar(
        ("2026-09-04", True),
        ("2026-09-05", False),
        ("2026-09-06", False),
        ("2026-09-07", True),
        ("2026-09-08", True),
    )

    result = load_previous_context(tmp_path, date(2026, 9, 8), days)

    assert result["previous_trade_date"] == "2026-09-07"
    assert result["official_review_loaded"] is False
    assert result["source_paths"]["official_review"] is None
    assert result["report_status"] == "degraded"


def test_simulated_official_review_is_rejected(tmp_path):
    path = tmp_path / "data" / "official_reviews"
    path.mkdir(parents=True)
    (path / "2026-09-07.json").write_text(
        json.dumps({"date": "2026-09-07", "data_kind": "real", "note": "fixture"}),
        encoding="utf-8",
    )
    result = load_previous_context(
        tmp_path,
        date(2026, 9, 8),
        _calendar(("2026-09-07", True), ("2026-09-08", True)),
    )
    assert result["official_review_status"] == "SIMULATED_REJECTED"
    assert result["official_review_loaded"] is False


def test_high_gap_with_order_decay_does_not_beat_stable_small_gap():
    high_gap = score_stock(
        _summary(
            auction_gap_pct=8,
            post_0920_price_stability=0.2,
            auction_amount_percentile_20d=30,
            post_0920_order_growth=-0.6,
            post_0920_order_decay=0.6,
            last_1min_order_growth=-0.5,
            unmatched_stability=0.2,
        ),
        {"ts_code": "000001.SZ", "themes": ["测试主题"]},
        _context(),
        _sector(0.2),
        [],
    )
    stable = score_stock(
        _summary(),
        {"ts_code": "000001.SZ", "themes": ["测试主题"]},
        _context(),
        _sector(0.8),
        [],
    )
    assert high_gap["components"]["auction_strength"]["subcomponents"]["price_performance"][
        "max_score"
    ] == 5
    assert stable["final_score"] > high_gap["final_score"]
    assert any(row["risk_type"] == "ORDER_DECAY" for row in high_gap["risks"])


def test_d_level_evidence_scores_zero_and_is_deducted():
    score = score_stock(
        _summary(),
        {"ts_code": "000001.SZ", "themes": ["测试主题"]},
        _context("D"),
        _sector(),
        [],
    )
    assert score["components"]["catalyst_credibility"]["score"] == 0
    assert any(row["risk_type"] == "RUMOR_DRIVEN" for row in score["risks"])
    assert score["final_score"] == score["gross_score"] - score["risk_deduction"]


def test_unsupported_order_fields_remain_na_and_reduce_available_max():
    score = score_stock(
        _summary(
            post_0920_order_growth=None,
            last_1min_order_growth=None,
            unmatched_stability=None,
        ),
        {"ts_code": "000001.SZ", "themes": ["测试主题"]},
        _context(),
        _sector(),
        [],
    )
    assert score["components"]["order_structure"]["score"] is None
    assert "order_structure" in score["missing_score_components"]
    assert score["available_max_score"] == 75


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.8, "confirmed"), (0.5, "partially_confirmed"), (0.3, "weakened"), (0.1, "invalidated")],
)
def test_tomorrow_check_has_machine_readable_status(ratio, expected):
    context = {
        "tomorrow_checks": [
            {"entity_type": "theme", "entity_key": "测试主题", "description": "核心股承接"}
        ]
    }
    result = validate_tomorrow_checks(
        context,
        [],
        [{"name": "测试主题", "positive_gap_ratio": ratio, "post_0920_positive_ratio": ratio}],
    )
    assert result[0]["validation_status"] == expected


def test_post_open_router_rejects_historical_date_and_evaluates_real_fields():
    router = PostOpenQuoteRouter(tencent_loader=lambda _: [], eastmoney_loader=lambda _: [])
    with pytest.raises(ValueError, match="historical"):
        router.load(
            date(2026, 9, 4),
            ["000001.SZ"],
            now=datetime(2026, 9, 8, 9, 35, tzinfo=SHANGHAI),
        )

    result = evaluate_post_open(
        [{"ts_code": "000001.SZ", "auction_price": 10.0, "prev_close": 9.8}],
        [
            {
                "ts_code": "000001.SZ",
                "last_price": 10.2,
                "low_price": 10.0,
                "observed_at": "2026-09-08T09:35:00+08:00",
            }
        ],
        "fixture_source",
    )
    assert result[0]["status"] == "confirmed"
    assert result[0]["holds_auction_price"] is True
