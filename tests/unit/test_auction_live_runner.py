from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.auction.eltdx_source import AuctionCollection
from src.auction.live_runner import LiveAuctionRunner


TZ = ZoneInfo("Asia/Shanghai")


class FakeLiveSource:
    def __init__(self):
        self.polls = 0
        self.closed = False

    def connect(self): pass
    def close(self): self.closed = True

    def collect_live_process(self, stocks, trade_date):
        self.polls += 1
        row = {"ts_code": stocks[0]["ts_code"], "content_hash": f"row-{self.polls}"}
        return AuctionCollection([row], [], [], {})

    def collect_live_formal(self, stocks, trade_date):
        return AuctionCollection([], [{"ts_code": stocks[0]["ts_code"]}], [], {})

    def _stats(self, completed, total):
        return {"request_count": self.polls + 1, "success_count": completed, "failure_count": total - completed,
                "reconnect_count": 0, "median_latency_ms": 1.0, "p95_latency_ms": 2.0,
                "stock_completion_rate": completed / total}


def test_live_runner_polls_all_checkpoints_and_waits_until_open_validation():
    current = [datetime(2026, 9, 7, 9, 14, 50, tzinfo=TZ)]
    def now(): return current[0]
    def sleeper(seconds): current[0] = current[0].fromtimestamp(current[0].timestamp() + seconds, TZ)
    source = FakeLiveSource()
    result = LiveAuctionRunner(source, now=now, sleeper=sleeper).collect(
        date(2026, 9, 7), [{"ts_code": "000001.SZ", "stock_name": "平安银行"}],
    )
    assert source.polls == 9
    assert result.stats["checkpoint_poll_count"] == 9
    assert current[0].time().isoformat() == "09:30:05"
    assert source.closed is True


def test_live_runner_rejects_late_start_instead_of_mislabeling_replay_as_live():
    current = datetime(2026, 9, 7, 9, 15, 1, tzinfo=TZ)
    source = FakeLiveSource()

    with pytest.raises(ValueError, match="must start by 09:15"):
        LiveAuctionRunner(source, now=lambda: current).collect(
            date(2026, 9, 7), [{"ts_code": "000001.SZ", "stock_name": "平安银行"}],
        )

    assert source.polls == 0
    assert source.closed is False
