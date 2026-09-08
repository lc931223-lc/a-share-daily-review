from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo

from src.auction.eltdx_source import AuctionCollection

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
POLL_TIMES = tuple(time(9, minute, second) for minute in range(15, 25) for second in (0, 30)) + (
    time(9, 25),
)


class LiveAuctionRunner:
    def __init__(
        self,
        source: Any,
        *,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = sleep,
        progress: Callable[[str, dict], None] | None = None,
    ):
        self.source = source
        self.now = now or (lambda: datetime.now(SHANGHAI_TZ))
        self.sleeper = sleeper
        self.progress = progress or (lambda stage, details: None)

    def collect(self, trade_date, stocks: list[dict[str, Any]]) -> AuctionCollection:
        current = self.now().astimezone(SHANGHAI_TZ)
        if current.date() != trade_date:
            raise ValueError(
                "live auction collection requires the current Asia/Shanghai trade date"
            )
        if current.time() >= time(9, 30):
            raise ValueError("live auction collection cannot start after market open")
        late = current.time() > time(9, 15)
        self.progress("COLLECTING", {"collection_start_time": current.isoformat(), "late_start": late})
        self.source.connect()
        unique_rows: dict[str, dict[str, Any]] = {}
        failures: dict[str, dict[str, str]] = {}
        polled = 0
        try:
            for poll_time in POLL_TIMES:
                target = datetime.combine(trade_date, poll_time, SHANGHAI_TZ)
                if target < current or self.now().astimezone(SHANGHAI_TZ).time() >= time(9, 25):
                    continue
                self._wait_until(target)
                self.source.collection_deadline = datetime.combine(trade_date, time(9, 25), SHANGHAI_TZ)
                result = self.source.collect_live_process(stocks, trade_date)
                polled += 1
                for row in result.process_rows:
                    unique_rows[str(row["content_hash"])] = row
                for failure in result.failures:
                    failures[str(failure["ts_code"])] = failure
            self._wait_until(
                datetime.combine(trade_date, time(9, 25), SHANGHAI_TZ) + timedelta(seconds=2)
            )
            self.progress("FORMAL_MATCH_PENDING", {})
            formal = self.source.collect_live_formal(stocks, trade_date)
            formal_by_code = {str(row["ts_code"]): row for row in formal.formal_rows}
            successful_codes = {str(row["ts_code"]) for row in unique_rows.values()} & set(
                formal_by_code
            )
            failures = {
                code: item for code, item in failures.items() if code not in successful_codes
            }
            for item in formal.failures:
                if str(item["ts_code"]) not in successful_codes:
                    failures[str(item["ts_code"])] = item
            stats = self.source._stats(len(successful_codes), len(stocks))
            stats["checkpoint_poll_count"] = polled
            stats["formal_match_times"] = [row.get("snapshot_time") for row in formal.formal_rows]
            stats.update(collection_start_time=current.isoformat(), auction_frozen_at=self.now().astimezone(SHANGHAI_TZ).isoformat(), late_start=late)
            self.progress("AUCTION_FROZEN", {"auction_frozen_at": stats["auction_frozen_at"]})
            return AuctionCollection(
                process_rows=list(unique_rows.values()),
                formal_rows=list(formal_by_code.values()),
                failures=list(failures.values()),
                stats=stats,
            )
        finally:
            self.source.close()

    def _wait_until(self, target: datetime) -> None:
        seconds = (target - self.now().astimezone(SHANGHAI_TZ)).total_seconds()
        if seconds > 0:
            self.sleeper(seconds)
