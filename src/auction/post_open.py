from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from src.auction.realtime_open import (
    EASTMONEY_URL,
    TENCENT_URL,
    _chunks,
    _eastmoney_secid,
    _vendor_code,
    _with_suffix,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class PostOpenQuoteRouter:
    def __init__(
        self,
        *,
        tencent_loader: Callable[[list[str]], list[dict[str, Any]]] | None = None,
        eastmoney_loader: Callable[[list[str]], list[dict[str, Any]]] | None = None,
    ):
        self.tencent_loader = tencent_loader or load_tencent_quotes
        self.eastmoney_loader = eastmoney_loader or load_eastmoney_quotes

    def load(
        self, trade_date: date, codes: list[str], *, now: datetime | None = None
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        current = (now or datetime.now(SHANGHAI_TZ)).astimezone(SHANGHAI_TZ)
        if current.date() != trade_date:
            raise ValueError("current-only post-open quotes cannot be written to a historical date")
        if not (9 * 60 + 30 <= current.hour * 60 + current.minute <= 10 * 60):
            raise ValueError("post-open validation is restricted to 09:30-10:00 Asia/Shanghai")
        fallbacks: list[dict[str, Any]] = []
        try:
            rows = self.tencent_loader(codes)
            _validate_rows(trade_date, rows, current)
            if rows:
                return "tencent_realtime", rows, fallbacks
        except Exception as exc:
            fallbacks.append(
                {
                    "primary_source": "tencent_realtime",
                    "fallback_source": "eastmoney_realtime",
                    "reason": type(exc).__name__,
                }
            )
        rows = self.eastmoney_loader(codes)
        _validate_rows(trade_date, rows, current)
        return "eastmoney_realtime", rows, fallbacks


def load_tencent_quotes(codes: list[str]) -> list[dict[str, Any]]:
    rows = []
    for chunk in _chunks(codes, 50):
        response = requests.get(
            TENCENT_URL + ",".join(_vendor_code(code) for code in chunk), timeout=8
        )
        response.raise_for_status()
        response.encoding = "gbk"
        for line in response.text.split(";"):
            if '="' not in line:
                continue
            parts = line.split('="', 1)[1].rstrip('"').split("~")
            if len(parts) <= 34 or not parts[2] or not parts[3] or len(str(parts[30])) < 14:
                continue
            observed = datetime.strptime(str(parts[30])[:14], "%Y%m%d%H%M%S").replace(
                tzinfo=SHANGHAI_TZ
            )
            rows.append(
                {
                    "ts_code": _with_suffix(parts[2]),
                    "last_price": float(parts[3]),
                    "open_price": _number(parts[5]),
                    "high_price": _number(parts[33]),
                    "low_price": _number(parts[34]),
                    "observed_at": observed.isoformat(),
                }
            )
    return rows


def load_eastmoney_quotes(codes: list[str]) -> list[dict[str, Any]]:
    rows = []
    for chunk in _chunks(codes, 50):
        response = requests.get(
            EASTMONEY_URL,
            params={
                "secids": ",".join(_eastmoney_secid(code) for code in chunk),
                "fields": "f12,f13,f2,f15,f16,f17,f124",
                "fltt": 2,
            },
            timeout=8,
        )
        response.raise_for_status()
        for row in (response.json().get("data") or {}).get("diff") or []:
            if row.get("f2") in {None, "-"} or not row.get("f124"):
                continue
            rows.append(
                {
                    "ts_code": _with_suffix(str(row.get("f12") or "")),
                    "last_price": float(row["f2"]),
                    "open_price": _number(row.get("f17")),
                    "high_price": _number(row.get("f15")),
                    "low_price": _number(row.get("f16")),
                    "observed_at": datetime.fromtimestamp(
                        int(row["f124"]), SHANGHAI_TZ
                    ).isoformat(),
                }
            )
    return rows


def evaluate_post_open(
    summaries: list[dict[str, Any]], rows: list[dict[str, Any]], source: str
) -> list[dict[str, Any]]:
    quotes = {str(row.get("ts_code")): row for row in rows}
    results = []
    for summary in summaries:
        quote = quotes.get(str(summary.get("ts_code")))
        if not quote:
            results.append(
                {
                    "ts_code": summary.get("ts_code"),
                    "status": "unverified",
                    "reason_codes": ["POST_OPEN_QUOTE_UNAVAILABLE"],
                    "source": source,
                }
            )
            continue
        auction = summary.get("auction_price")
        previous = summary.get("prev_close")
        last = quote.get("last_price")
        low = quote.get("low_price")
        holds_auction = low is not None and auction is not None and low >= auction
        holds_previous = last is not None and previous is not None and last >= previous
        status = (
            "confirmed"
            if holds_auction and holds_previous
            else "partially_confirmed"
            if holds_previous
            else "weakened"
        )
        results.append(
            {
                **quote,
                "status": status,
                "holds_auction_price": holds_auction,
                "holds_previous_close": holds_previous,
                "reason_codes": [
                    "HOLDS_AUCTION_PRICE" if holds_auction else "LOST_AUCTION_PRICE",
                    "HOLDS_PREVIOUS_CLOSE" if holds_previous else "LOST_PREVIOUS_CLOSE",
                ],
                "source": source,
            }
        )
    return results


def _validate_rows(expected: date, rows: list[dict[str, Any]], now=None) -> None:
    dates = {datetime.fromisoformat(str(row["observed_at"])).date() for row in rows}
    if dates != {expected}:
        raise ValueError(f"source date mismatch: expected {expected.isoformat()}, observed {dates}")
    for row in rows:
        observed = datetime.fromisoformat(str(row['observed_at']))
        if observed.tzinfo is None or (now is not None and (observed > now or (now-observed).total_seconds()>120)):
            raise ValueError('post-open observation is future or stale')
        local=observed.astimezone(SHANGHAI_TZ)
        if not 570 <= local.hour*60+local.minute <= 600:
            raise ValueError('post-open observation outside validation window')


def _number(value: Any) -> float | None:
    return None if value in {None, "", "-"} else float(value)
