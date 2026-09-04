from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ResolvedObservation:
    field: str
    selected_value: Any
    selected_source: str
    candidates: dict[str, Any]
    conflict: dict[str, Any] | None


def normalize_ts_code(code: str) -> str:
    normalized = code.strip().upper()
    if normalized.startswith(("SH", "SZ", "BJ")):
        prefix = normalized[:2]
        digits = normalized[2:]
        return f"{digits}.{prefix}"
    if "." in normalized:
        digits, exchange = normalized.split(".", 1)
        if _valid_code_exchange(digits, exchange):
            return f"{digits}.{exchange}"
    if len(normalized) == 6 and normalized.isdigit():
        if normalized.startswith(("60", "68")):
            return f"{normalized}.SH"
        if normalized.startswith(("00", "30")):
            return f"{normalized}.SZ"
        if normalized.startswith(("43", "83", "87", "88", "92")):
            return f"{normalized}.BJ"
    raise ValueError(f"无法识别证券代码：{code}")


def normalize_trade_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text)


def normalize_turnover_to_yi(value: float | int, unit: str) -> float:
    if unit == "yuan":
        return float(value) / 100_000_000
    if unit == "thousand_yuan":
        return float(value) / 100_000
    if unit == "yi_yuan":
        return float(value)
    raise ValueError(f"未知成交额单位：{unit}")


def resolve_observations(
    *,
    primary: Any,
    supplement: Any,
    field: str,
    primary_source: str = "primary",
    supplement_source: str = "supplement",
) -> ResolvedObservation:
    candidates = {primary_source: primary, supplement_source: supplement}
    conflict = None
    if primary != supplement:
        conflict = {
            "field": field,
            "selected_source": primary_source,
            "candidate_sources": candidates,
        }
    return ResolvedObservation(
        field=field,
        selected_value=primary,
        selected_source=primary_source,
        candidates=candidates,
        conflict=conflict,
    )


def _valid_code_exchange(digits: str, exchange: str) -> bool:
    return len(digits) == 6 and digits.isdigit() and exchange in {"SH", "SZ", "BJ"}
