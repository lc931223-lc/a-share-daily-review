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

    def connect(self):
        pass

    def close(self):
        self.closed = True

    def collect_live_process(self, stocks, trade_date):
        self.polls += 1
        row = {"ts_code": stocks[0]["ts_code"], "content_hash": f"row-{self.polls}"}
        return AuctionCollection([row], [], [], {})

    def collect_live_formal(self, stocks, trade_date):
        return AuctionCollection([], [{"ts_code": stocks[0]["ts_code"]}], [], {})

    def _stats(self, completed, total):
        return {
            "request_count": self.polls + 1,
            "success_count": completed,
            "failure_count": total - completed,
            "reconnect_count": 0,
            "median_latency_ms": 1.0,
            "p95_latency_ms": 2.0,
            "stock_completion_rate": completed / total,
        }


def test_live_runner_returns_at_formal_match_without_waiting_for_open():
    current = [datetime(2026, 9, 7, 9, 14, 50, tzinfo=TZ)]

    def now():
        return current[0]

    def sleeper(seconds):
        current[0] = current[0].fromtimestamp(current[0].timestamp() + seconds, TZ)

    source = FakeLiveSource()
    result = LiveAuctionRunner(source, now=now, sleeper=sleeper).collect(
        date(2026, 9, 7),
        [{"ts_code": "000001.SZ", "stock_name": "平安银行"}],
    )
    assert source.polls == 21
    assert result.stats["checkpoint_poll_count"] == 21
    assert current[0].time().isoformat() == "09:25:02"
    assert source.closed is True


def test_live_runner_rejects_late_start_instead_of_mislabeling_replay_as_live():
    current = datetime(2026, 9, 7, 9, 30, 1, tzinfo=TZ)
    source = FakeLiveSource()

    with pytest.raises(ValueError, match="after market open"):
        LiveAuctionRunner(source, now=lambda: current).collect(
            date(2026, 9, 7),
            [{"ts_code": "000001.SZ", "stock_name": "平安银行"}],
        )

    assert source.polls == 0
    assert source.closed is False


@pytest.mark.parametrize(
    "seconds,status", [(5, "PASS"), (6, "PARTIAL"), (60, "PARTIAL"), (61, "FAIL")]
)
def test_start_acceptance_boundaries(seconds, status):
    from datetime import timedelta

    current = [datetime(2026, 9, 7, 9, 15, tzinfo=TZ) + timedelta(seconds=seconds)]
    events = []
    runner = LiveAuctionRunner(
        FakeLiveSource(),
        now=lambda: current[0],
        sleeper=lambda s: current.__setitem__(0, current[0] + timedelta(seconds=s)),
        progress=lambda stage, details: events.append((stage, details)),
    )
    runner.collect(date(2026, 9, 7), [{"ts_code": "000001.SZ"}])
    assert (
        next(details["start_acceptance"] for _, details in events if "start_acceptance" in details)
        == status
    )


def test_formal_retries_missing_codes_only():
    from datetime import timedelta

    class Delayed(FakeLiveSource):
        def __init__(self):
            super().__init__()
            self.calls = []

        def collect_live_formal(self, stocks, trade_date):
            self.calls.append([row["ts_code"] for row in stocks])
            return AuctionCollection([], [{"ts_code": stocks[0]["ts_code"]}], [], {})

    current = [datetime(2026, 9, 7, 9, 24, tzinfo=TZ)]
    source = Delayed()
    result = LiveAuctionRunner(
        source,
        now=lambda: current[0],
        sleeper=lambda s: current.__setitem__(0, current[0] + timedelta(seconds=s)),
    ).collect(date(2026, 9, 7), [{"ts_code": "000001.SZ"}, {"ts_code": "600519.SH"}])
    assert source.calls == [["000001.SZ", "600519.SH"], ["600519.SH"]]
    assert len(result.formal_rows) == 2
    assert current[0].time().isoformat() == "09:25:04"


def test_source_failure_closes_and_leaves_connect_started():
    class Broken(FakeLiveSource):
        def connect(self):
            raise TimeoutError("fixture source failure")

    source = Broken()
    events = []
    with pytest.raises(TimeoutError):
        LiveAuctionRunner(
            source,
            now=lambda: datetime(2026, 9, 7, 9, 12, tzinfo=TZ),
            progress=lambda stage, details: events.append((stage, details)),
        ).collect(date(2026, 9, 7), [])
    assert source.closed
    assert events[-1][0] == "PREFLIGHT_FAILED"
    assert events[-1][1]["source_connect_result"] == "FAIL"
