from __future__ import annotations

from typing import Any

import numpy as np


def number(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if np.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return min(high, max(low, value))


def mean(values: list[Any]) -> float | None:
    valid = [item for value in values if (item := number(value)) is not None]
    return sum(valid) / len(valid) if valid else None


def ratio(numerator: Any, denominator: Any, *, scale: float = 1.0) -> float | None:
    left, right = number(numerator), number(denominator)
    return left / right * scale if left is not None and right not in (None, 0) else None


def stock_code(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    if "." in raw and len(raw.split(".", 1)[0]) == 6:
        return raw
    code = raw.split(".", 1)[0]
    if len(code) != 6 or not code.isdigit():
        return None
    suffix = "SH" if code.startswith(("5", "6")) else "BJ" if code.startswith(("4", "8", "9")) else "SZ"
    return f"{code}.{suffix}"


def percentile_rank(values: list[Any], value: Any) -> float | None:
    target = number(value)
    valid = sorted(item for raw in values if (item := number(raw)) is not None)
    if target is None or not valid:
        return None
    return 100.0 * sum(item <= target for item in valid) / len(valid)
