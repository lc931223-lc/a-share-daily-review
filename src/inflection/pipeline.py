from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator

from src.inflection.features import compute_stock_features
from src.inflection.fundamentals import load_fundamental_features
from src.inflection.history import DailyHistoryRepository
from src.inflection.scoring import score_features
from src.inflection.storage import persist_inflection_run
from src.storage.fact_store import FactStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_STATUSES = {"INFLECTION_WATCH", "INFLECTION_CANDIDATE", "INFLECTION_CONFIRMED", "TREND_CONFIRMED", "MAIN_UPTREND", "DISTRIBUTION_WARNING", "TREND_BROKEN"}


class InflectionPipeline:
    def __init__(self, root: Path = PROJECT_ROOT, *, history_repository: DailyHistoryRepository | None = None):
        self.root = root
        self.fact_store = FactStore(root / "data" / "facts")
        self.history = history_repository or DailyHistoryRepository(root, fact_store=self.fact_store)
        self.database_path = root / "data" / "a_share_review.db"

    def run(self, target: date, *, scan_limit: int | None = None, ensure_history: bool = True) -> dict[str, Any]:
        history_status = self.history.ensure_history(target) if ensure_history else {"requested_dates": 0, "cached_dates": 0, "loaded_dates": 0, "failed_dates": []}
        start = target - timedelta(days=550)
        target_rows = self.history.query(target, target)
        if target_rows.empty:
            raise RuntimeError("stock_daily_ohlcv history is unavailable")
        target_rows = _latest_partition_rows(target_rows)
        target_rows = target_rows[target_rows["trade_date"] == target.isoformat()].copy()
        target_rows = target_rows[pd.to_numeric(target_rows["vol"], errors="coerce").fillna(0) > 0]
        codes = sorted(target_rows["ts_code"].astype(str).unique())
        if scan_limit:
            codes = codes[:scan_limit]
        frame = self.history.query(start, target, codes=codes)
        frame = _latest_partition_rows(frame)
        frame = frame[frame["trade_date"] <= target.isoformat()].copy()
        metadata = self.history.stock_metadata(target)
        fundamentals, fundamental_status = load_fundamental_features(self.root, target)
        previous = self._previous_scores(target)
        rows = []
        excluded = {"insufficient_history": 0, "no_valid_daily": 0}
        for code in codes:
            stock_frame = frame[frame["ts_code"] == code].copy()
            if stock_frame.empty:
                excluded["no_valid_daily"] += 1
                continue
            meta = metadata.get(code, {})
            for key, value in meta.items():
                stock_frame[key] = [value] * len(stock_frame)
            features = compute_stock_features(stock_frame)
            if features.get("history_observation_count", 0) < 60:
                excluded["insufficient_history"] += 1
                continue
            fundamental = fundamentals.get(code)
            if fundamental is None and fundamental_status["status"] == "AVAILABLE":
                fundamental = {
                    "fundamental_inflection_score": 0,
                    "score_components": {"earnings": 0, "price_supply": 0, "order_customer_capacity": 0, "policy_capital": 0},
                    "main_catalyst": None, "catalyst_stage": None, "evidence_level": None,
                }
            scored = score_features(features, fundamental)
            row = features | scored
            row.update({
                "main_catalyst": (fundamental or {}).get("main_catalyst"),
                "catalyst_stage": (fundamental or {}).get("catalyst_stage"),
                "evidence_level": (fundamental or {}).get("evidence_level"),
                "previous_status": previous.get(code, {}).get("status"),
                "score_change_1d": _difference(row["trend_inflection_score"], previous.get(code, {}).get("score_1d")),
                "score_change_5d": _difference(row["trend_inflection_score"], previous.get(code, {}).get("score_5d")),
                "score_change_20d": _difference(row["trend_inflection_score"], previous.get(code, {}).get("score_20d")),
            })
            row["status_change"] = f"{row['previous_status']}->{row['status']}" if row["previous_status"] and row["previous_status"] != row["status"] else None
            row["quality_status"] = "PASS" if row["score_component_coverage"]["ratio"] == 1 else "PARTIAL"
            row["why_selected"] = _why_selected(row)
            row["schema_version"] = "inflection_daily.1"
            rows.append(row)

        rows.sort(key=lambda item: (-(item.get("score_change_1d") or 0), -item["trend_inflection_score"], item["ts_code"]))
        candidates = [row for row in rows if row["status"] in CANDIDATE_STATUSES]
        checks = _quality_checks(rows, history_status, fundamental_status)
        status = "PASS" if all(item["passed"] for item in checks) else "PARTIAL"
        if not rows:
            status = "FAIL"
        persist_inflection_run(target, rows, checks, status, fact_store=self.fact_store, database_path=self.database_path)
        packet = {
            "meta": {"schema_version": "inflection_packet.1", "trade_date": target.isoformat(), "as_of": f"{target.isoformat()}T15:05:00+08:00", "final_judgement_owner": "chatgpt"},
            "scan_summary": {"scanned_count": len(rows), "candidate_count": len(candidates), "excluded": excluded, "history": history_status},
            "candidates": candidates,
            "data_quality": {
                "status": status, "checks": checks, "fundamental_source": fundamental_status,
                "known_gaps": [
                    "turnover_rate history unavailable because Tushare daily_basic is unavailable",
                    "adjustment-factor history unavailable; price structure uses raw daily prices",
                    "capacity_confirmation and breadth_confirmation are deferred to Phase I6",
                    "positive_catalyst_fatigue requires multiple historical catalyst-response windows",
                ],
            },
        }
        compact = _compact(packet)
        output_dir = self.root / "data" / "inflection"
        output_dir.mkdir(parents=True, exist_ok=True)
        full_path = output_dir / f"{target.isoformat()}.json"
        compact_path = output_dir / f"{target.isoformat()}_compact.json"
        full_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
        Draft202012Validator(_schema("inflection_packet.schema.json")).validate(packet)
        Draft202012Validator(_schema("inflection_compact.schema.json")).validate(compact)
        return {"packet": packet, "compact": compact, "paths": {"full": str(full_path), "compact": str(compact_path)}}

    def _previous_scores(self, target: date) -> dict[str, dict[str, Any]]:
        dataset_root = self.fact_store.root / "dataset=inflection_daily"
        dates = sorted(
            path.name.split("=", 1)[1]
            for path in dataset_root.glob("trade_date=*")
            if path.name.split("=", 1)[1] < target.isoformat()
        )
        if not dates:
            return {}
        offsets = {1: dates[-1] if dates else None, 5: dates[-5] if len(dates) >= 5 else None, 20: dates[-20] if len(dates) >= 20 else None}
        result: dict[str, dict[str, Any]] = {}
        for horizon, date_text in offsets.items():
            if date_text is None:
                continue
            rows = self.fact_store.read_dataset("inflection_daily", date.fromisoformat(date_text))
            for row in rows:
                code = str(row.get("ts_code"))
                item = result.setdefault(code, {})
                if horizon == 1:
                    item["status"] = row.get("status")
                item[f"score_{horizon}d"] = row.get("trend_inflection_score")
        return result


def _compact(packet: dict[str, Any]) -> dict[str, Any]:
    rows = packet["candidates"]
    upward_statuses = {"INFLECTION_WATCH", "INFLECTION_CANDIDATE", "INFLECTION_CONFIRMED", "TREND_CONFIRMED", "MAIN_UPTREND"}
    changed = [
        row for row in rows
        if row["status"] in upward_statuses
        and ((row.get("score_change_1d") or 0) > 0 or row.get("status_change"))
    ]
    base = {"meta": packet["meta"] | {"schema_version": "inflection_compact.1"}, "data_quality": packet["data_quality"]}
    selectors = {
        "top_new_inflections": changed,
        "top_confirmed_inflections": [row for row in rows if row["status"] == "INFLECTION_CONFIRMED"],
        "trend_confirmed": [row for row in rows if row["status"] == "TREND_CONFIRMED"],
        "main_uptrend_candidates": [row for row in rows if row["status"] == "MAIN_UPTREND"],
        "distribution_warnings": [row for row in rows if row["status"] == "DISTRIBUTION_WARNING"],
        "trend_broken": [row for row in rows if row["status"] == "TREND_BROKEN"],
        "fundamental_catalyst_candidates": [row for row in rows if row.get("fundamental_inflection_score")],
        "volume_breakout_candidates": [row for row in rows if row.get("breakout_type") and row.get("breakout_volume_confirmation") == "HIGH_VOLUME_CONFIRMED"],
        "weekly_breakout_candidates": [row for row in rows if row.get("weekly_breakout_type")],
        "capacity_confirmed_candidates": [row for row in rows if row.get("capacity_confirmation") == "PASS"],
    }
    for key, selected in selectors.items():
        base[key] = [_compact_row(row) for row in selected[:15]]
    return base


def _compact_row(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "ts_code", "stock_name", "industry", "themes", "trend_inflection_score",
        "fundamental_inflection_score", "price_volume_score", "daily_structure_score",
        "weekly_trend_score", "chip_structure_score", "status", "previous_status",
        "score_change_1d", "score_change_5d", "main_catalyst", "catalyst_stage",
        "evidence_level", "amount_ratio_20d", "amount_percentile_120d",
        "pullback_volume_ratio", "breakout_type", "breakout_hold_days",
        "weekly_breakout_type", "capacity_confirmation", "risk_flags", "why_selected",
    )
    return {key: row.get(key) for key in fields}


def _why_selected(row: dict[str, Any]) -> list[str]:
    reasons = []
    if row.get("amount_ratio_20d") is not None:
        reasons.append(f"当日成交额为此前20日均值的{row['amount_ratio_20d']:.2f}倍")
    if row.get("breakout_type"):
        reasons.append(f"收盘价形成{row['breakout_type']}，站稳天数{row.get('breakout_hold_days') or 0}")
    if row.get("weekly_breakout_type"):
        reasons.append(f"周线形成{row['weekly_breakout_type']}")
    if row.get("pullback_volume_ratio") is not None:
        reasons.append(f"最近回调/上涨段成交额比{row['pullback_volume_ratio']:.2f}")
    if row.get("distribution_warning"):
        reasons.append("高成交分位、高换手/波动与上影线组合触发筹码恶化观察")
    return reasons


def _quality_checks(rows: list[dict[str, Any]], history: dict[str, Any], fundamentals: dict[str, Any]) -> list[dict[str, Any]]:
    count = len(rows)
    full_history = sum(row.get("history_observation_count", 0) >= 250 for row in rows) / count if count else 0
    core = sum(row.get("amount_ratio_20d") is not None and row.get("ma60") is not None and row.get("wma20") is not None for row in rows) / count if count else 0
    turnover = sum(row.get("turnover_percentile_60d") is not None for row in rows) / count if count else 0
    score_change = sum(row.get("score_change_1d") is not None for row in rows) / count if count else 0
    score_change_5d = sum(row.get("score_change_5d") is not None for row in rows) / count if count else 0
    score_change_20d = sum(row.get("score_change_20d") is not None for row in rows) / count if count else 0
    return [
        {"name": "scanner_nonempty", "actual": count, "threshold": 1, "passed": count > 0},
        {"name": "core_feature_coverage", "actual": core, "threshold": 0.9, "passed": core >= 0.9},
        {"name": "full_250d_history_coverage", "actual": full_history, "threshold": 0.9, "passed": full_history >= 0.9},
        {"name": "turnover_feature_coverage", "actual": turnover, "threshold": 0.9, "passed": turnover >= 0.9, "reason": "daily_basic unavailable" if turnover < 0.9 else ""},
        {"name": "score_change_1d_coverage", "actual": score_change, "threshold": 0.9, "passed": score_change >= 0.9, "reason": "previous scan coverage is incomplete" if score_change < 0.9 else ""},
        {"name": "score_change_5d_coverage", "actual": score_change_5d, "threshold": 0.9, "passed": score_change_5d >= 0.9, "reason": "five-day full-market scan history is incomplete" if score_change_5d < 0.9 else ""},
        {"name": "score_change_20d_coverage", "actual": score_change_20d, "threshold": 0.9, "passed": score_change_20d >= 0.9, "reason": "twenty-day full-market scan history is incomplete" if score_change_20d < 0.9 else ""},
        {"name": "history_fetch_failures", "actual": len(history.get("failed_dates") or []), "threshold": 0, "passed": not history.get("failed_dates")},
        {"name": "fundamental_source_available", "actual": fundamentals["status"], "threshold": "AVAILABLE", "passed": fundamentals["status"] == "AVAILABLE", "reason": "existing announcement facts unavailable" if fundamentals["status"] != "AVAILABLE" else ""},
    ]


def _latest_partition_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    result["trade_date"] = result["trade_date"].astype(str).str[:10]
    return result.drop_duplicates(subset=["trade_date", "ts_code"], keep="last")


def _difference(current: Any, previous: Any) -> float | None:
    return float(current) - float(previous) if current is not None and previous is not None and not pd.isna(previous) else None


def _schema(name: str) -> dict[str, Any]:
    return json.loads((PROJECT_ROOT / "schemas" / name).read_text(encoding="utf-8"))
