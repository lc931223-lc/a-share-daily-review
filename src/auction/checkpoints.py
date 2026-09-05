from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
CHECKPOINTS = ("09:15:00", "09:17:00", "09:19:00", "09:20:00", "09:21:00", "09:22:00", "09:23:00", "09:24:00", "09:25:00")


def map_checkpoints(
    trade_date: date,
    process_rows: list[dict[str, Any]],
    formal_row: dict[str, Any] | None,
    *,
    max_lag_seconds: int = 65,
    identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    ordered = sorted(process_rows, key=lambda row: _row_datetime(row, trade_date))
    template = formal_row or (ordered[-1] if ordered else identity or {})
    rows: list[dict[str, Any]] = []
    for checkpoint_text in CHECKPOINTS:
        target = datetime.combine(trade_date, time.fromisoformat(checkpoint_text), SHANGHAI_TZ)
        selected = formal_row if checkpoint_text == "09:25:00" and formal_row else None
        if selected is None and checkpoint_text != "09:25:00":
            eligible = [row for row in ordered if _row_datetime(row, trade_date) <= target]
            candidate = eligible[-1] if eligible else None
            if candidate is not None:
                lag = (target - _row_datetime(candidate, trade_date)).total_seconds()
                selected = candidate if 0 <= lag <= max_lag_seconds else None
        if selected is None:
            row = _missing_row(template, trade_date, checkpoint_text)
        else:
            row = dict(selected)
            row["checkpoint_time"] = checkpoint_text
            row["checkpoint_lag_ms"] = max(0, int((target - _row_datetime(selected, trade_date)).total_seconds() * 1000))
            row["observation_kind"] = "checkpoint"
            row["content_hash"] = _hash_row(row)
        rows.append(row)
    return rows


def _missing_row(template: dict[str, Any], trade_date: date, checkpoint_text: str) -> dict[str, Any]:
    row = {
        "trade_date": trade_date.isoformat(),
        "ts_code": template.get("ts_code"),
        "stock_name": template.get("stock_name"),
        "snapshot_time": None,
        "checkpoint_time": checkpoint_text,
        "match_price": None,
        "matched_volume": None,
        "matched_amount": None,
        "unmatched_signed_volume": None,
        "unmatched_direction_raw": None,
        "unmatched_buy": None,
        "unmatched_sell": None,
        "raw_matched_volume": None,
        "raw_volume_unit": None,
        "matched_amount_value_kind": None,
        "source": template.get("source", "eltdx"),
        "source_batch_id": template.get("source_batch_id"),
        "retrieved_at": template.get("retrieved_at"),
        "source_data_time": None,
        "checkpoint_lag_ms": None,
        "is_formal_opening_match": False,
        "quality_status": "UNAVAILABLE",
        "schema_version": "auction_snapshot.1",
        "observation_kind": "checkpoint",
    }
    row["content_hash"] = _hash_row(row)
    return row


def _row_datetime(row: dict[str, Any], trade_date: date) -> datetime:
    value = row.get("source_data_time") or row.get("snapshot_time")
    if value:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=SHANGHAI_TZ)
    return datetime.combine(trade_date, time(0), SHANGHAI_TZ)


def _hash_row(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key not in {"content_hash", "source_batch_id", "retrieved_at"}}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
