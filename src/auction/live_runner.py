from __future__ import annotations

from datetime import datetime, time, timedelta
from time import sleep
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.auction.checkpoints import CHECKPOINTS
from src.auction.eltdx_source import AuctionCollection


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class LiveAuctionRunner:
    def __init__(
        self,
        source: Any,
        *,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = sleep,
    ):
        self.source = source
        self.now = now or (lambda: datetime.now(SHANGHAI_TZ))
        self.sleeper = sleeper

    def collect(self, trade_date, stocks: list[dict[str, Any]]) -> AuctionCollection:
        current = self.now().astimezone(SHANGHAI_TZ)
        if current.date() != trade_date:
            raise ValueError("live auction collection requires the current Asia/Shanghai trade date")
        if current.time() > time(9, 15):
            raise ValueError("live auction collection must start by 09:15 Asia/Shanghai")
        self.source.connect()
        unique_rows: dict[str, dict[str, Any]] = {}
        failures: dict[str, dict[str, str]] = {}
        polled = 0
        try:
            for checkpoint_text in CHECKPOINTS:
                target = datetime.combine(trade_date, time.fromisoformat(checkpoint_text), SHANGHAI_TZ)
                self._wait_until(target)
                result = self.source.collect_live_process(stocks, trade_date)
                polled += 1
                for row in result.process_rows:
                    unique_rows[str(row["content_hash"])] = row
                for failure in result.failures:
                    failures[str(failure["ts_code"])] = failure
            self._wait_until(datetime.combine(trade_date, time(9, 25), SHANGHAI_TZ) + timedelta(seconds=2))
            formal = self.source.collect_live_formal(stocks, trade_date)
            formal_by_code = {str(row["ts_code"]): row for row in formal.formal_rows}
            successful_codes = {str(row["ts_code"]) for row in unique_rows.values()} & set(formal_by_code)
            failures = {code: item for code, item in failures.items() if code not in successful_codes}
            for item in formal.failures:
                if str(item["ts_code"]) not in successful_codes:
                    failures[str(item["ts_code"])] = item
            stats = self.source._stats(len(successful_codes), len(stocks))
            stats["checkpoint_poll_count"] = polled
            self._wait_until(datetime.combine(trade_date, time(9, 30, 5), SHANGHAI_TZ))
            return AuctionCollection(
                process_rows=list(unique_rows.values()), formal_rows=list(formal_by_code.values()),
                failures=list(failures.values()), stats=stats,
            )
        finally:
            self.source.close()

    def _wait_until(self, target: datetime) -> None:
        seconds = (target - self.now().astimezone(SHANGHAI_TZ)).total_seconds()
        if seconds > 0:
            self.sleeper(seconds)
