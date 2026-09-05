from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from src.feedback.backtest import ERROR_TYPES, run_as_of_backtest
from src.feedback.tracker import (
    persist_predictions,
    persist_validations,
    prediction_from_official_review,
    prediction_from_review_context,
)
from src.inflection.history import DailyHistoryRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WARMUP_START = date(2024, 10, 1)


class FeedbackPipeline:
    def __init__(self, root: Path = PROJECT_ROOT, *, history: DailyHistoryRepository | None = None):
        self.root = root
        self.history = history or DailyHistoryRepository(root)
        self.database_path = root / "data" / "a_share_review.db"

    def run(self, start: date, end: date, *, ensure_history: bool = True) -> dict[str, Any]:
        history_status = (
            self.history.ensure_range(WARMUP_START, end)
            if ensure_history
            else {"requested_dates": 0, "cached_dates": 0, "loaded_dates": 0, "failed_dates": []}
        )
        daily = self.history.query(WARMUP_START, end)
        metadata = self.history.stock_metadata(end)
        backtest = run_as_of_backtest(daily, metadata, start=start.isoformat(), end=end.isoformat())
        formal_predictions = self._formal_predictions(start, end)
        persistence = {
            "proxy_predictions": persist_predictions(self.database_path, backtest["predictions"]),
            "formal_predictions": persist_predictions(self.database_path, formal_predictions),
        }
        persistence["validations"] = persist_validations(
            self.database_path, backtest["validations"]
        )
        inflection_metrics = self._inflection_metrics(start, end)
        backtest["metrics"].update(inflection_metrics)
        backtest["history_status"] = history_status
        backtest["formal_prediction_records"] = formal_predictions
        backtest["persistence"] = persistence

        backtest_dir = self.root / "data" / "as_of_backtests"
        backtest_dir.mkdir(parents=True, exist_ok=True)
        backtest_path = backtest_dir / f"{start.isoformat()}_to_{end.isoformat()}.json"
        backtest_path.write_text(
            json.dumps(backtest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = self._report(end, backtest, formal_predictions)
        report_dir = self.root / "research_feedback"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"{end.isoformat()}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "backtest": backtest,
            "report": report,
            "paths": {"backtest": str(backtest_path), "feedback": str(report_path)},
        }

    def _formal_predictions(self, start: date, end: date) -> list[dict[str, Any]]:
        results = []
        sources = (
            (self.root / "data" / "official_reviews", prediction_from_official_review),
            (self.root / "data" / "review_context", prediction_from_review_context),
        )
        for folder, parser in sources:
            for path in sorted(folder.glob("????-??-??.json")):
                try:
                    trade_date = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                if start <= trade_date <= end:
                    results.append(parser(_read(path), path))
        return results

    def _inflection_metrics(self, start: date, end: date) -> dict[str, Any]:
        records = []
        for path in sorted((self.root / "data" / "inflection" / "backtests").glob("*.json")):
            payload = _read(path)
            for row in payload.get("records") or []:
                day = str(row.get("trade_date") or "")[:10]
                if start.isoformat() <= day <= end.isoformat():
                    records.append(row)
        records = list(
            {
                (row.get("trade_date"), row.get("ts_code"), row.get("status")): row
                for row in records
            }.values()
        )
        confirmed = [row for row in records if row.get("status") == "INFLECTION_CONFIRMED"]
        warnings = [row for row in records if row.get("status") == "DISTRIBUTION_WARNING"]
        return {
            "inflection_confirmed_performance": {
                f"return_{horizon}d": _mean([row.get(f"return_{horizon}d") for row in confirmed])
                for horizon in (5, 10, 20)
            }
            | {"sample_count": len(confirmed)},
            "distribution_warning_drawdown_probability": {
                "value": _ratio(
                    sum((row.get("max_drawdown_20d") or 0) <= -0.10 for row in warnings),
                    len(warnings),
                ),
                "threshold": -0.10,
                "sample_count": len(warnings),
                "definition": "Probability that a DISTRIBUTION_WARNING candidate reaches a raw-price drawdown of at least 10% within 20 trading days.",
            },
        }

    @staticmethod
    def _report(
        end: date, backtest: dict[str, Any], formal: list[dict[str, Any]]
    ) -> dict[str, Any]:
        predictions = backtest["predictions"]
        validations = backtest["validations"]
        previous = (
            predictions[-2] if len(predictions) >= 2 else predictions[-1] if predictions else None
        )
        validation_by_date = {row["prediction_date"]: row for row in validations}
        previous_validation = validation_by_date.get((previous or {}).get("prediction_date"))
        complete = [
            row
            for row in validations
            if any(
                value is not None
                for value in row.get("theme_return_20d", {}).get("predicted", {}).values()
            )
        ]
        latest_complete = complete[-1] if complete else None
        errors = Counter(error for row in validations for error in row.get("error_type") or [])
        incorrect = []
        correct = []
        if latest_complete:
            if latest_complete["theme_return_5d"].get("predicted_top1_is_actual_top1"):
                correct.append("Latest complete sample matched the five-day top industry at Top1.")
            if latest_complete["theme_return_5d"].get("actual_top1_in_predicted_top3"):
                correct.append("Latest complete sample covered the five-day top industry in Top3.")
            incorrect = [
                error for error in latest_complete["error_type"] if error != "DATA_LIMITATION"
            ]
        previous_actual = previous_validation or {
            "status": "PENDING_FORWARD_WINDOW",
            "reason": "The previous prediction does not yet have a complete 5/10/20 trading-day result window.",
        }
        return {
            "meta": {
                "schema_version": "research_feedback.1",
                "report_date": end.isoformat(),
                "purpose": "RESEARCH_EVALUATION_ONLY",
                "auto_model_change": False,
                "auto_weight_change": False,
            },
            "previous_judgement": previous,
            "actual_result": previous_actual,
            "latest_completed_validation": latest_complete,
            "correct_parts": correct,
            "incorrect_parts": incorrect,
            "error_reasons": [
                {"error_type": key, "count": errors.get(key, 0)}
                for key in sorted(ERROR_TYPES, key=lambda key: (-errors.get(key, 0), key))
            ],
            "aggregate_metrics": backtest["metrics"],
            "evaluation_coverage": {
                "market_review": "PROXY_HISTORY; no real historical official_review series",
                "review_intelligence": "2026-09-04 objective context frozen; forward validation pending",
                "inflection_scanner": "Historical scanner records evaluated where stored; confirmed/warning sample counts reported without substitution",
                "auction": "2026-09-04 packet frozen in review_context; historical process snapshots unavailable and not reconstructed",
            },
            "formal_review_tracking": {
                "record_count": len(formal),
                "real_official_review_count": sum(
                    row.get("record_kind") == "FORMAL_OFFICIAL_REVIEW" for row in formal
                ),
                "simulated_official_review_count": sum(
                    row.get("record_kind") == "SIMULATED_OFFICIAL_REVIEW" for row in formal
                ),
                "objective_context_count": sum(
                    row.get("record_kind") == "OBJECTIVE_REVIEW_CONTEXT" for row in formal
                ),
                "records": formal,
                "validation_status": "PENDING_FORWARD_WINDOW" if formal else "NO_REVIEW_RECORD",
            },
            "data_quality": {
                "status": "PARTIAL",
                "strict_as_of": True,
                "history_fetch_failures": backtest["history_status"].get("failed_dates") or [],
                "limitations": backtest["data_limitations"],
            },
        }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mean(values: list[Any]) -> dict[str, Any]:
    usable = [float(value) for value in values if value is not None]
    return {
        "value": round(sum(usable) / len(usable), 8) if usable else None,
        "sample_count": len(usable),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None
