from __future__ import annotations

from typing import Any


def apply_open_validation(
    summaries: list[dict[str, Any]],
    official_opens: dict[str, float],
    *,
    source: str,
    error_threshold_pct: float = 0.02,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for summary in summaries:
        code = str(summary.get("ts_code") or "")
        auction_price = summary.get("auction_price")
        official_open = official_opens.get(code)
        summary["open_price_validation_source"] = source if official_open is not None else None
        summary["official_open_price"] = official_open
        if auction_price is None or official_open is None or official_open == 0:
            summary["open_price_error_pct"] = None
            summary["conflict_status"] = "not_validated"
            continue
        error = abs(float(auction_price) - float(official_open)) / abs(float(official_open)) * 100
        summary["open_price_error_pct"] = error
        if error > error_threshold_pct:
            summary["conflict_status"] = "conflict"
            summary["quality_status"] = "INVALID"
            conflicts.append({
                "type": "open_price_conflict",
                "ts_code": code,
                "auction_final_price": float(auction_price),
                "official_open_price": float(official_open),
                "validation_source": source,
                "open_price_error_pct": error,
                "threshold_pct": error_threshold_pct,
            })
        else:
            summary["conflict_status"] = "none"
    return conflicts
