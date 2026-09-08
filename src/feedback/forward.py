from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.feedback.integrated import (
    build_correction_record,
    build_review_record,
    validate_integrated_prediction,
)
from src.feedback.tracker import persist_predictions, persist_validations, prediction_from_review_context
from src.inflection.history import DailyHistoryRepository
from src.formal_review.persistence import load_previous_formal
from src.formal_review.support import validate_formal_hypotheses


def advance_feedback(root: Path, as_of: date) -> dict[str, Any]:
    history = DailyHistoryRepository(root)
    daily = history.query(date(2024, 10, 1), as_of)
    waiting_before = 0
    newly_validated = 0
    validated = 0
    still_waiting = 0
    cycles = []
    for context_path in sorted((root / "data" / "review_context").glob("????-??-??.json")):
        prediction_date = date.fromisoformat(context_path.stem)
        if prediction_date > as_of:
            continue
        folder = root / "data" / "feedback_records" / context_path.stem
        prediction_path = folder / "prediction.json"
        validation_path = folder / "validation.json"
        old_status = None
        old_validation = None
        old_horizons: set[int] = set()
        if validation_path.is_file():
            old_validation = _read(validation_path)
            old_meta = old_validation.get("meta") or {}
            old_status = old_meta.get("status")
            old_horizons = set(old_meta.get("available_horizons") or [])
            waiting_before += old_status == "WAITING_FOR_MARKET_DATA"
        prediction = _read(prediction_path) if prediction_path.is_file() else _context_prediction(root, context_path)
        validation = validate_integrated_prediction(root, prediction, daily)
        formal_eligible = prediction["meta"].get("official_review_kind") == "FORMAL_OFFICIAL_REVIEW"
        validation["meta"]["hypothesis_kind"] = "FORMAL_REVIEW_HYPOTHESIS" if formal_eligible else "OBJECTIVE_SUPPORT_HYPOTHESIS"
        validation["meta"]["formal_hit_rate_eligible"] = formal_eligible
        new_horizons = set((validation.get("meta") or {}).get("available_horizons") or [])
        if old_validation is not None and not old_horizons.issubset(new_horizons):
            validation = old_validation
            validation_path.write_text(
                json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            new_horizons = old_horizons
        validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
        review = build_review_record(root, prediction, validation)
        correction = build_correction_record(root, prediction, validation, review)
        status = validation["meta"]["status"]
        if len(new_horizons) > len(old_horizons):
            newly_validated += 1
        if status == "WAITING_FOR_MARKET_DATA":
            still_waiting += 1
        else:
            validated += 1
        normalized = prediction["normalized_prediction_record"]
        persist_predictions(root / "data" / "a_share_review.db", [normalized])
        stored = _validation_for_storage(prediction, validation)
        if stored:
            persist_validations(root / "data" / "a_share_review.db", [stored])
        cycles.append(
            {
                "prediction_date": prediction_date.isoformat(),
                "previous_status": old_status,
                "validation_status": status,
                "available_horizons": validation["meta"]["available_horizons"],
                "review_status": review["meta"]["status"],
                "correction_status": correction["meta"]["status"],
            }
        )
    formal_feedback = None
    market_path = root / "data/market_packets" / f"{as_of}.json"
    if market_path.exists():
        formal, provenance = load_previous_formal(root, as_of)
        formal_feedback = validate_formal_hypotheses(formal, provenance, _read(market_path))
        folder = root / "research_feedback/formal"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{as_of}.json").write_text(json.dumps(formal_feedback, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "status": "PASS",
        "as_of": as_of.isoformat(),
        "pending_count": waiting_before,
        "newly_validated_count": newly_validated,
        "still_waiting_count": still_waiting,
        "validated_count": validated,
        "cycles": cycles,
        "formal_review_validation": formal_feedback,
    }


def _context_prediction(root: Path, context_path: Path) -> dict[str, Any]:
    context = _read(context_path)
    normalized = prediction_from_review_context(context, context_path)
    target = date.fromisoformat(normalized["prediction_date"])
    market_path = root / "data" / "market_packets" / f"{target.isoformat()}.json"
    market = _read(market_path) if market_path.is_file() else {}
    source_review = normalized["source_review"]
    packet = {
        "meta": {
            "schema_version": "integrated_prediction.1",
            "prediction_date": target.isoformat(),
            "status": "OBJECTIVE_CONTEXT_ONLY",
            "source_review": source_review,
            "official_review_kind": "UNAVAILABLE",
            "final_judgement_owner": "chatgpt",
            "new_analysis_generated": False,
        },
        "source_manifest": {
            "review_context": {
                "trade_date": target.isoformat(),
                "path": context_path.relative_to(root).as_posix(),
            }
        },
        "market_baseline": {
            "market_overview": market.get("market_overview") or {},
            "market_breadth": market.get("market_breadth") or {},
            "liquidity": market.get("liquidity") or {},
            "limit_up_down": market.get("limit_up_down") or {},
        },
        "official_review": {"record_kind": "UNAVAILABLE"},
        "review_intelligence": {},
        "inflection": {"candidates": context.get("inflection_candidates") or []},
        "auction": {
            "market_auction_summary": {},
            "stock_auction_summary": [],
            "volume_anomaly_candidates": [],
            "objective_analysis": {},
            "conflicts": [],
        },
        "normalized_prediction_record": normalized,
    }
    folder = root / "data" / "feedback_records" / target.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "prediction.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return packet


def _validation_for_storage(prediction, validation):
    validation_date = validation["meta"].get("validation_date")
    if validation_date is None:
        return None
    return {
        "prediction_date": prediction["meta"]["prediction_date"],
        "source_review": prediction["meta"]["source_review"],
        "validation_date": validation_date,
        "actual_market_state": validation["actual_market_state"],
        "actual_theme_result": validation["actual_theme_result"],
        "theme_return_5d": validation["theme_return_5d"],
        "theme_return_10d": validation["theme_return_10d"],
        "theme_return_20d": validation["theme_return_20d"],
        "leader_result": validation["leader_result"],
        "stock_result": validation["stock_result"],
        "max_gain": validation["max_gain"],
        "max_drawdown": validation["max_drawdown"],
        "error_type": validation["error_type"],
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
