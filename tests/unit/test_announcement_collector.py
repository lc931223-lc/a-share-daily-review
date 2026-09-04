from __future__ import annotations

from datetime import date, datetime
import gzip
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.market_packet.announcement_collector import (
    AnnouncementCandidate,
    AnnouncementCollector,
    AnnouncementSourceAdapter,
    CninfoBatchAnnouncementAdapter,
    build_announcement_sections,
)


TZ = ZoneInfo("Asia/Shanghai")


def _collector(tmp_path: Path, rows: list[dict] | Exception) -> AnnouncementCollector:
    def fetcher(_code, _start, _end):
        if isinstance(rows, Exception):
            raise rows
        return pd.DataFrame(rows)

    return AnnouncementCollector(raw_root=tmp_path, fetcher=fetcher, max_stocks=1)


class Dataset:
    def __init__(self, rows):
        self.rows = rows


def _datasets():
    return {"limit_up": Dataset([{"代码": "000001", "名称": "平安银行"}])}


class StubAnnouncementAdapter(AnnouncementSourceAdapter):
    def __init__(self, source: str, rows: list[dict] | Exception, supported_prefix: str = ""):
        self.source = source
        self.rows = rows
        self.supported_prefix = supported_prefix

    def supports(self, code: str) -> bool:
        return code.startswith(self.supported_prefix)

    def fetch(self, code, start, end):
        if isinstance(self.rows, Exception):
            raise self.rows
        return self.rows


def test_announcement_normal_return(tmp_path):
    collector = _collector(tmp_path, [{"公告标题": "关于重大合同的公告", "公告时间": "2026-09-02 10:00:00", "公告链接": "finalpage/2026-09-02/a.PDF"}])
    result = collector.collect(date(2026, 9, 2), _datasets(), as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records[0]["category"] == "contract"
    assert result.records[0]["evidence_level"] == "A"
    assert result.quality == "PASS"
    batch = tmp_path / "2026-09-02" / "announcements" / "source_records.jsonl.gz"
    with gzip.open(batch, "rt", encoding="utf-8") as stream:
        archived = [json.loads(line) for line in stream]
    assert len(archived) == 1
    assert archived[0]["content_hash"]
    assert not list(batch.parent.glob("000001-*.json"))


def test_announcement_timeout_is_fail_without_fake_empty_values(tmp_path):
    collector = _collector(tmp_path, TimeoutError("slow"))
    result = collector.collect(date(2026, 9, 2), _datasets(), as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records == []
    assert result.failed_sources
    assert result.quality == "FAIL"


def test_announcement_failed_aggregate_respects_retry_ttl(tmp_path):
    first = _collector(tmp_path, TimeoutError("slow"))
    first.collect(date(2026, 9, 2), _datasets(), as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    calls = {"count": 0}

    def succeeds(*_args):
        calls["count"] += 1
        return pd.DataFrame([{"公告标题": "关于重大合同的公告", "公告时间": "2026-09-02"}])

    second = AnnouncementCollector(raw_root=tmp_path, fetcher=succeeds, max_stocks=1)
    result = second.collect(date(2026, 9, 2), _datasets(), as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.quality == "FAIL"
    assert calls["count"] == 0


def test_announcement_exchange_adapter_fallback_after_cninfo_failure(tmp_path):
    collector = AnnouncementCollector(
        raw_root=tmp_path,
        adapters=[
            StubAnnouncementAdapter("巨潮资讯", TimeoutError("slow")),
            StubAnnouncementAdapter("深交所", [{"公告标题": "关于签署重大合同的公告", "公告时间": "2026-09-02", "公告链接": "/disc/a.pdf"}], "0"),
        ],
        max_stocks=1,
    )

    result = collector.collect(date(2026, 9, 2), _datasets(), as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))

    assert result.records[0]["source"] == "深交所"
    assert result.records[0]["evidence_level"] == "A"
    assert result.coverage_rate == 1
    assert result.quality == "PARTIAL"


def test_cninfo_batch_adapter_queries_by_date_not_by_stock(tmp_path):
    class Response:
        def json(self):
            return {"announcements": [
                {"secCode": "000001", "announcementTitle": "关于重大合同的公告", "announcementTime": "2026-09-02", "adjunctUrl": "finalpage/a.pdf"},
                {"secCode": "600000", "announcementTitle": "关于回购股份的公告", "announcementTime": "2026-09-02", "adjunctUrl": "finalpage/b.pdf"},
            ]}

    class Client:
        def __init__(self):
            self.calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            return Response()

    client = Client()
    adapter = CninfoBatchAnnouncementAdapter(lambda *_: pd.DataFrame(), client)
    collector = AnnouncementCollector(raw_root=tmp_path, adapters=[adapter], max_stocks=2)
    datasets = {"limit_up": Dataset([{"代码": "000001", "名称": "平安银行"}, {"代码": "600000", "名称": "浦发银行"}])}
    result = collector.collect(date(2026, 9, 2), datasets, as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert client.calls == 1
    assert len(result.records) == 2
    assert result.coverage_rate == 1


def test_cninfo_batch_adapter_fetches_all_reported_pages():
    class Response:
        def __init__(self, page):
            self.page = page

        def json(self):
            return {
                "totalpages": 2,
                "totalAnnouncement": 2,
                "announcements": [{
                    "secCode": "000001",
                    "announcementTitle": f"第{self.page}页公告",
                    "announcementTime": "2026-09-02",
                    "adjunctUrl": f"finalpage/{self.page}.pdf",
                }],
            }

    class Client:
        def __init__(self):
            self.pages = []

        def post(self, *_args, **kwargs):
            page = kwargs["data"]["pageNum"]
            self.pages.append(page)
            return Response(page)

    client = Client()
    adapter = CninfoBatchAnnouncementAdapter(lambda *_: pd.DataFrame(), client)
    rows = adapter.fetch_many(["000001"], date(2026, 9, 2), date(2026, 9, 2))

    assert client.pages == [1, 2]
    assert len(rows) == 2


def test_announcement_failed_sources_are_disabled_for_remaining_stock_pool(tmp_path):
    class FailingAdapter(AnnouncementSourceAdapter):
        def __init__(self, source, *, batch=False):
            self.source = source
            self.calls = 0
            self.batch = batch

        def fetch_many(self, *_args):
            if not self.batch:
                raise AssertionError("not a batch adapter")
            self.calls += 1
            raise TimeoutError("source unavailable")

        def fetch(self, *_args):
            self.calls += 1
            raise TimeoutError("source unavailable")

    batch = FailingAdapter("巨潮资讯", batch=True)
    exchange = FailingAdapter("深交所")
    collector = AnnouncementCollector(raw_root=tmp_path, adapters=[batch, exchange], max_stocks=3)
    datasets = {"limit_up": Dataset([
        {"代码": "000001", "名称": "平安银行"},
        {"代码": "000002", "名称": "万科A"},
        {"代码": "300001", "名称": "特锐德"},
    ])}

    result = collector.collect(date(2026, 9, 2), datasets, as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))

    assert batch.calls == 1
    assert exchange.calls == 1
    assert result.quality == "FAIL"


def test_announcement_duplicate_and_multi_source_prefers_official(tmp_path):
    collector = AnnouncementCollector(raw_root=tmp_path, fetcher=lambda *_: pd.DataFrame(), max_stocks=1)
    official = collector.normalize_announcement(AnnouncementCandidate("000001", "平安银行", "巨潮资讯", {"公告标题": "关于重大合同的公告", "公告时间": "2026-09-02"}))
    media = dict(official)
    media["source"] = "权威媒体"
    media["source_type"] = "media"
    media["is_official"] = False
    media["evidence_level"] = "B"
    result = collector.deduplicate_announcements([media, official])
    assert len(result) == 1
    assert result[0]["source"] == "巨潮资讯"
    assert result[0]["supplemental_sources"] == ["权威媒体"]


def test_announcement_future_pollution_is_filtered(tmp_path):
    collector = _collector(tmp_path, [{"公告标题": "关于重大合同的公告", "公告时间": "2026-09-05 09:00:00"}])
    result = collector.collect(date(2026, 9, 4), _datasets(), as_of_time=datetime(2026, 9, 4, 15, 30, tzinfo=TZ))
    assert result.records == []


@pytest.mark.parametrize(
    ("title", "category", "field", "expected"),
    [
        ("关于尚未形成订单的风险提示公告", "risk_warning", "clarification_flags", "尚未形成订单"),
        ("关于股东减持计划的公告", "decrease_holding", "risk_flags", "减持"),
        ("2026年半年度业绩预告", "earnings", "category", "earnings"),
        ("关于签署重大合同的公告", "contract", "category", "contract"),
    ],
)
def test_announcement_key_phrase_classification(tmp_path, title, category, field, expected):
    collector = AnnouncementCollector(raw_root=tmp_path, fetcher=lambda *_: pd.DataFrame(), max_stocks=1)
    item = collector.normalize_announcement(AnnouncementCandidate("000001", "平安银行", "巨潮资讯", {"公告标题": title, "公告时间": "2026-09-02"}))
    assert item["category"] == category
    if field == "category":
        assert item[field] == expected
    else:
        assert expected in item[field]


def test_announcement_sections_group_records(tmp_path):
    records = [
        {"category": "contract", "risk_flags": [], "clarification_flags": []},
        {"category": "risk_warning", "risk_flags": ["风险提示"], "clarification_flags": []},
        {"category": "earnings", "risk_flags": [], "clarification_flags": []},
    ]
    sections = build_announcement_sections(records)
    assert len(sections["orders_contracts"]) == 1
    assert len(sections["risk_announcements"]) == 1
    assert len(sections["earnings_updates"]) == 1
