from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
TENCENT_URL = "https://qt.gtimg.cn/q="
EASTMONEY_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"


class RealtimeOpenRouter:
    def __init__(
        self,
        *,
        tencent_loader: Callable[[list[str]], tuple[dict[str, float], set[date]]] | None = None,
        eastmoney_loader: Callable[[list[str]], tuple[dict[str, float], set[date]]] | None = None,
    ):
        self.tencent_loader = tencent_loader or load_tencent_opens
        self.eastmoney_loader = eastmoney_loader or load_eastmoney_opens

    def load(self, trade_date: date, codes: list[str], *, now: datetime | None = None) -> tuple[str, dict[str, float], list[dict[str, Any]]]:
        current = (now or datetime.now(SHANGHAI_TZ)).astimezone(SHANGHAI_TZ)
        if current.date() != trade_date:
            raise ValueError("current-only open sources cannot be written to a historical trade date")
        fallbacks: list[dict[str, Any]] = []
        try:
            values, dates = self.tencent_loader(codes)
            _validate_dates(trade_date, dates)
            if values:
                return "tencent_realtime", values, fallbacks
        except Exception as exc:
            fallbacks.append({"primary_source": "tencent_realtime", "fallback_source": "eastmoney_realtime", "reason": type(exc).__name__})
        values, dates = self.eastmoney_loader(codes)
        _validate_dates(trade_date, dates)
        return "eastmoney_realtime", values, fallbacks


def load_tencent_opens(codes: list[str]) -> tuple[dict[str, float], set[date]]:
    result: dict[str, float] = {}
    observed_dates: set[date] = set()
    for chunk in _chunks(codes, 50):
        symbols = [_vendor_code(code) for code in chunk]
        response = requests.get(TENCENT_URL + ",".join(symbols), timeout=8)
        response.raise_for_status()
        response.encoding = "gbk"
        for line in response.text.split(";"):
            if '="' not in line:
                continue
            parts = line.split('="', 1)[1].rstrip('"').split("~")
            if len(parts) <= 30 or not parts[2] or not parts[5]:
                continue
            code = _with_suffix(parts[2])
            result[code] = float(parts[5])
            stamp = str(parts[30])
            if len(stamp) >= 8 and stamp[:8].isdigit():
                observed_dates.add(datetime.strptime(stamp[:8], "%Y%m%d").date())
    return result, observed_dates


def load_eastmoney_opens(codes: list[str]) -> tuple[dict[str, float], set[date]]:
    result: dict[str, float] = {}
    observed_dates: set[date] = set()
    for chunk in _chunks(codes, 50):
        response = requests.get(EASTMONEY_URL, params={
            "secids": ",".join(_eastmoney_secid(code) for code in chunk),
            "fields": "f12,f13,f17,f124", "fltt": 2,
        }, timeout=8)
        response.raise_for_status()
        rows = (response.json().get("data") or {}).get("diff") or []
        for row in rows:
            code = _with_suffix(str(row.get("f12") or ""))
            if row.get("f17") not in {None, "-"}:
                result[code] = float(row["f17"])
            if row.get("f124"):
                observed_dates.add(datetime.fromtimestamp(int(row["f124"]), SHANGHAI_TZ).date())
    return result, observed_dates


def _validate_dates(expected: date, observed: set[date]) -> None:
    if observed != {expected}:
        raise ValueError(f"source date mismatch: expected {expected.isoformat()}, observed {sorted(observed)}")


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _vendor_code(code: str) -> str:
    digits, exchange = code.split(".", 1)
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}[exchange] + digits


def _eastmoney_secid(code: str) -> str:
    digits, exchange = code.split(".", 1)
    return f"{1 if exchange == 'SH' else 0}.{digits}"


def _with_suffix(code: str) -> str:
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("8", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"
