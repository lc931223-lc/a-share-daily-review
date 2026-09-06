from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.capital_preference.features import build_stock_statistics_for_dates
from src.capital_preference.pipeline import CapitalPreferencePipeline
from src.inflection.history import DailyHistoryRepository
from src.review_intelligence.helpers import mean, number


def run_replay(root: Path, start: date, end: date) -> dict[str, Any]:
    history = DailyHistoryRepository(root)
    full_history = history.query(start - timedelta(days=550), end)
    folder = root / "data" / "review_intelligence"
    dates = sorted(
        date.fromisoformat(path.stem)
        for path in folder.glob("????-??-??.json")
        if start.isoformat() <= path.stem <= end.isoformat()
    )
    pipeline = CapitalPreferencePipeline(root, history_repository=history)
    metadata = history.stock_metadata(end)
    statistics_by_date = build_stock_statistics_for_dates(
        full_history, [target.isoformat() for target in dates], metadata
    )
    daily_results = []
    for target in dates:
        target_timestamp = pd.Timestamp(target)
        history_window = full_history[
            (full_history["trade_date"] <= target_timestamp)
            & (full_history["trade_date"] >= target_timestamp - timedelta(days=550))
        ]
        result = pipeline.run(
            target,
            daily_history=history_window,
            stock_statistics=statistics_by_date[target.isoformat()],
            metadata=metadata,
            persist_outputs=False,
        )
        themes = result["packet"]["theme_capital_preference"]
        strengths = [number(row.get("source_theme_strength")) for row in themes]
        strengths = sorted(value for value in strengths if value is not None)
        high_cut = strengths[max(int(len(strengths) * 0.8) - 1, 0)] if strengths else None
        low_cut = (
            strengths[min(int(len(strengths) * 0.2), len(strengths) - 1)] if strengths else None
        )
        strong = [
            row
            for row in themes
            if high_cut is not None
            and number(row.get("source_theme_strength")) is not None
            and row["source_theme_strength"] >= high_cut
        ]
        weak = [
            row
            for row in themes
            if low_cut is not None
            and number(row.get("source_theme_strength")) is not None
            and row["source_theme_strength"] <= low_cut
        ]
        daily_results.append(
            {
                "trade_date": target.isoformat(),
                "source_reference": "OBJECTIVE_REVIEW_INTELLIGENCE_STRENGTH_PROXY",
                "high_strength_theme_count": len(strong),
                "high_strength_capital_preference_average": mean(
                    [row.get("capital_preference_score") for row in strong]
                ),
                "all_theme_capital_preference_average": mean(
                    [row.get("capital_preference_score") for row in themes]
                ),
                "weak_theme_count": len(weak),
                "weak_low_capacity_rate": _rate(
                    weak, lambda row: (row["capital_capacity"].get("normalized_score") or 0) < 40
                ),
                "weak_high_crowding_rate": _rate(
                    weak, lambda row: row.get("crowding_status") in {"ELEVATED", "EXTREME"}
                ),
                "weak_low_style_match_rate": _rate(
                    weak, lambda row: (row["style_match"].get("normalized_score") or 0) < 40
                ),
                "quality_status": result["packet"]["data_quality"]["status"],
            }
        )
    report = {
        "schema_version": "capital_preference_replay.1",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "trading_day_count": len(daily_results),
        "validation_basis": "OBJECTIVE_REVIEW_INTELLIGENCE_STRENGTH_PROXY",
        "high_strength_capital_preference_average": mean(
            [row["high_strength_capital_preference_average"] for row in daily_results]
        ),
        "all_theme_capital_preference_average": mean(
            [row["all_theme_capital_preference_average"] for row in daily_results]
        ),
        "weak_theme_low_capacity_rate": mean(
            [row["weak_low_capacity_rate"] for row in daily_results]
        ),
        "weak_theme_high_crowding_rate": mean(
            [row["weak_high_crowding_rate"] for row in daily_results]
        ),
        "weak_theme_low_style_match_rate": mean(
            [row["weak_low_style_match_rate"] for row in daily_results]
        ),
        "daily_results": daily_results,
        "limitations": [
            "No real historical official_review series exists, so objective Review Intelligence strength is used only as a labeled comparison proxy.",
            "The replay does not infer or declare historical mainlines.",
            "Missing market-cap, news, institution, policy, auction, and concept-membership history remains null or lowers quality status.",
        ],
    }
    output = (
        root
        / "data"
        / "capital_preference"
        / "backtests"
        / f"{start.isoformat()}_to_{end.isoformat()}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": report, "path": str(output)}


def _rate(rows, predicate):
    return sum(predicate(row) for row in rows) / len(rows) if rows else None
