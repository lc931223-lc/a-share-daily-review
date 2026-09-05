from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any


def anomaly_labels(summary: dict[str, Any]) -> list[str]:
    score = summary.get("auction_volume_anomaly_score")
    ratio_20d = summary.get("auction_amount_ratio_20d")
    gap = summary.get("auction_gap_pct")
    if score is None or ratio_20d is None:
        return []

    labels: list[str] = []
    if score >= 16 and ratio_20d >= 3:
        labels.append("EXTREME_VOLUME_ANOMALY")
    if score >= 12 and ratio_20d >= 1.5 and gap is not None and gap >= 1:
        labels.append("STRONG_VOLUME_CONFIRMATION")
    if ratio_20d < 1 and gap is not None and gap >= 2:
        labels.append("PRICE_STRONG_VOLUME_WEAK")
    if score >= 12 and ratio_20d >= 1.5 and gap is not None and gap <= 0:
        labels.append("PRICE_WEAK_VOLUME_STRONG")
    return labels


def build_objective_analysis(
    watchlist: dict[str, Any],
    summaries: list[dict[str, Any]],
    previous_review: dict[str, Any],
) -> dict[str, Any]:
    stocks = {str(item.get("ts_code")): item for item in watchlist.get("stocks") or []}
    valid = [item for item in summaries if item.get("auction_price") is not None]
    gaps = [float(item["auction_gap_pct"]) for item in valid if item.get("auction_gap_pct") is not None]
    amounts = [float(item["auction_amount"]) for item in valid if item.get("auction_amount") is not None]
    market = {
        "status": "AVAILABLE" if valid else "UNAVAILABLE",
        "watchlist_count": len(summaries),
        "valid_auction_count": len(valid),
        "high_open_count": sum(value > 0 for value in gaps),
        "flat_open_count": sum(value == 0 for value in gaps),
        "low_open_count": sum(value < 0 for value in gaps),
        "median_gap_pct": statistics.median(gaps) if gaps else None,
        "total_auction_amount": sum(amounts) if amounts else None,
    }

    sector_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        for theme in stocks.get(str(summary.get("ts_code")), {}).get("themes") or []:
            sector_buckets[str(theme)].append(summary)
    sector_rows = [_aggregate_sector(name, rows) for name, rows in sector_buckets.items()]
    sector_rows.sort(key=lambda item: (
        -(item["average_anomaly_score"] if item["average_anomaly_score"] is not None else -1),
        -(item["median_gap_pct"] if item["median_gap_pct"] is not None else -999),
        item["name"],
    ))
    for rank, item in enumerate(sector_rows, 1):
        item["rank"] = rank

    stock_rows = [
        {
            "rank": 0,
            "ts_code": item.get("ts_code"),
            "stock_name": item.get("stock_name"),
            "themes": stocks.get(str(item.get("ts_code")), {}).get("themes") or [],
            "auction_gap_pct": item.get("auction_gap_pct"),
            "auction_amount_ratio_20d": item.get("auction_amount_ratio_20d"),
            "auction_amount_percentile_60d": item.get("auction_amount_percentile_60d"),
            "auction_volume_anomaly_score": item.get("auction_volume_anomaly_score"),
            "anomaly_labels": item.get("anomaly_labels") or [],
        }
        for item in summaries
    ]
    stock_rows.sort(key=lambda item: (
        -(item["auction_volume_anomaly_score"] if item["auction_volume_anomaly_score"] is not None else -1),
        -(item["auction_amount_ratio_20d"] if item["auction_amount_ratio_20d"] is not None else -1),
        str(item.get("ts_code") or ""),
    ))
    for rank, item in enumerate(stock_rows, 1):
        item["rank"] = rank

    mainline_validation = _previous_mainline_validation(previous_review, sector_rows)
    transitions = _transition_candidates(previous_review, summaries)
    return {
        "market_auction_environment": market,
        "previous_mainline_validation": mainline_validation,
        "sector_auction_ranking": sector_rows,
        "stock_auction_ranking": stock_rows,
        "weak_to_strong_candidates": transitions["weak_to_strong_candidates"],
        "strong_to_weak_candidates": transitions["strong_to_weak_candidates"],
        "transition_status": transitions["status"],
        "validation_conditions_0930_1000": _validation_conditions(),
    }


def build_compact_packet(packet: dict[str, Any]) -> dict[str, Any]:
    analysis = packet["objective_analysis"]
    return {
        "meta": packet["meta"] | {"schema_version": "auction_packet_compact.1"},
        "market_auction_environment": analysis["market_auction_environment"] | {
            "checkpoint_coverage": packet["market_auction_summary"].get("checkpoint_coverage"),
            "post_0920_checkpoint_coverage": packet["market_auction_summary"].get("post_0920_checkpoint_coverage"),
            "formal_opening_match_success_rate": packet["market_auction_summary"].get("formal_opening_match_success_rate"),
        },
        "previous_mainline_validation": analysis["previous_mainline_validation"],
        "sector_auction_ranking": analysis["sector_auction_ranking"][:20],
        "stock_auction_ranking": analysis["stock_auction_ranking"][:30],
        "volume_anomalies": [
            {
                "ts_code": item.get("ts_code"),
                "stock_name": item.get("stock_name"),
                "auction_gap_pct": item.get("auction_gap_pct"),
                "auction_amount_ratio_20d": item.get("auction_amount_ratio_20d"),
                "auction_volume_anomaly_score": item.get("auction_volume_anomaly_score"),
                "anomaly_labels": item.get("anomaly_labels") or [],
            }
            for item in packet["volume_anomaly_candidates"][:30]
        ],
        "weak_to_strong_candidates": analysis["weak_to_strong_candidates"][:20],
        "strong_to_weak_candidates": analysis["strong_to_weak_candidates"][:20],
        "transition_status": analysis["transition_status"],
        "validation_conditions_0930_1000": analysis["validation_conditions_0930_1000"],
        "data_quality": {
            "status": packet["data_quality"]["status"],
            "failed_checks": [item["name"] for item in packet["data_quality"]["checks"] if not item["passed"]],
            "conflict_count": len(packet["conflicts"]),
        },
    }


def _aggregate_sector(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [float(item["auction_gap_pct"]) for item in rows if item.get("auction_gap_pct") is not None]
    scores = [float(item["auction_volume_anomaly_score"]) for item in rows if item.get("auction_volume_anomaly_score") is not None]
    return {
        "rank": 0,
        "name": name,
        "stock_count": len(rows),
        "valid_count": len(gaps),
        "median_gap_pct": statistics.median(gaps) if gaps else None,
        "positive_gap_ratio": sum(value > 0 for value in gaps) / len(gaps) if gaps else None,
        "average_anomaly_score": statistics.fmean(scores) if scores else None,
        "extreme_volume_count": sum("EXTREME_VOLUME_ANOMALY" in (item.get("anomaly_labels") or []) for item in rows),
        "total_auction_amount": sum(float(item["auction_amount"]) for item in rows if item.get("auction_amount") is not None),
    }


def _previous_mainline_validation(review: dict[str, Any], sector_rows: list[dict[str, Any]]) -> dict[str, Any]:
    themes = review.get("main_themes") or []
    if not themes:
        return {
            "status": "UNAVAILABLE",
            "reason": "previous official_review main_themes unavailable",
            "themes": [],
        }
    ranked = {str(item["name"]): item for item in sector_rows}
    rows = []
    for theme in themes:
        name = str(theme.get("name") or "")
        objective = ranked.get(name)
        rows.append({
            "name": name,
            "previous_rank": theme.get("rank_no") or theme.get("rank"),
            "previous_stage": theme.get("stage"),
            "auction_observation_status": "AVAILABLE" if objective else "UNAVAILABLE",
            "auction_rank": objective.get("rank") if objective else None,
            "median_gap_pct": objective.get("median_gap_pct") if objective else None,
            "positive_gap_ratio": objective.get("positive_gap_ratio") if objective else None,
            "average_anomaly_score": objective.get("average_anomaly_score") if objective else None,
        })
    return {"status": "AVAILABLE", "reason": None, "themes": rows}


def _transition_candidates(review: dict[str, Any], summaries: list[dict[str, Any]]) -> dict[str, Any]:
    review_stocks = review.get("stocks") or []
    if not review_stocks:
        return {"status": "UNAVAILABLE", "weak_to_strong_candidates": [], "strong_to_weak_candidates": []}
    prior = {_digits(item.get("code") or item.get("stock_code")): item for item in review_stocks}
    weak_to_strong = []
    strong_to_weak = []
    for summary in summaries:
        previous = prior.get(_digits(summary.get("ts_code")))
        if not previous:
            continue
        role = _normalize_role(previous.get("role"))
        gap = summary.get("auction_gap_pct")
        labels = summary.get("anomaly_labels") or []
        row = {
            "ts_code": summary.get("ts_code"),
            "stock_name": summary.get("stock_name"),
            "previous_role": previous.get("role"),
            "auction_gap_pct": gap,
            "auction_volume_anomaly_score": summary.get("auction_volume_anomaly_score"),
            "anomaly_labels": labels,
        }
        if role == "catch_up" and gap is not None and gap >= 1 and "STRONG_VOLUME_CONFIRMATION" in labels:
            weak_to_strong.append(row)
        if role in {"leader", "capacity"} and gap is not None and gap < 0:
            strong_to_weak.append(row)
    return {"status": "AVAILABLE", "weak_to_strong_candidates": weak_to_strong, "strong_to_weak_candidates": strong_to_weak}


def _validation_conditions() -> list[dict[str, Any]]:
    return [
        {"id": "hold_auction_price", "status": "PENDING", "field": "low_0930_1000", "operator": ">=", "reference": "auction_price"},
        {"id": "hold_previous_close", "status": "PENDING", "field": "last_price_1000", "operator": ">=", "reference": "prev_close"},
        {"id": "sector_breadth_confirm", "status": "PENDING", "field": "sector_advancer_ratio_1000", "operator": ">=", "value": 0.5},
        {"id": "opening_conflict_clear", "status": "PENDING", "field": "conflict_status", "operator": "==", "value": "none"},
    ]


def _digits(value: Any) -> str:
    return str(value or "").split(".", 1)[0].zfill(6)


def _normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    aliases = {
        "龙头": "leader", "核心龙头": "leader",
        "中军": "capacity", "容量": "capacity", "容量核心": "capacity",
        "补涨": "catch_up", "补涨股": "catch_up",
    }
    return aliases.get(role, role)
