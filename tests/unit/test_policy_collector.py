from __future__ import annotations

from datetime import date, datetime
import gzip
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from src.market_packet.policy_collector import (
    BsePolicyAdapter,
    CsrcPolicyAdapter,
    MiitPolicyAdapter,
    NeaPolicyAdapter,
    PolicyCollector,
    build_policy_sections,
    media_policy_record,
)


TZ = ZoneInfo("Asia/Shanghai")


def _html(title: str, published: str = "2026-09-02") -> str:
    return f"<html><body><ul><li><span>{published}</span><a href='/policy.html'>{title}</a></li></ul></body></html>"


def _collector(tmp_path: Path, outcomes: list[str | Exception]) -> PolicyCollector:
    state = {"i": 0}

    def fetcher(_source):
        outcome = outcomes[min(state["i"], len(outcomes) - 1)]
        state["i"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return PolicyCollector(raw_root=tmp_path, source_fetcher=fetcher)


def test_policy_normal_return(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持人工智能产业发展的通知")])
    result = collector.collect(date(2026, 9, 2), [{"theme_name": "AI"}], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records
    assert result.records[0]["evidence_level"] == "A"
    assert result.records[0]["is_official"] is True
    batch = tmp_path / "2026-09-02" / "policies" / "source_records.jsonl.gz"
    with gzip.open(batch, "rt", encoding="utf-8") as stream:
        archived = [json.loads(line) for line in stream]
    assert archived
    assert all(item["content_hash"] for item in archived)
    assert len({item["content_hash"] for item in archived}) == len(archived)
    assert not list(batch.parent.glob("[0-9a-f]*.json"))


def test_policy_official_original_preferred_over_media(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持机器人产业发展的通知")])
    official = collector.collect(date(2026, 9, 2), [{"theme_name": "机器人"}], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ)).records[0]
    media = media_policy_record(official["title"], "权威媒体")
    result = collector.deduplicate_policies([media, official])
    assert result[0]["source_type"] == "official"
    assert result[0]["evidence_level"] == "A"


def test_policy_media_reprint_is_b_level():
    item = media_policy_record("媒体转述政策", "权威媒体")
    assert item["evidence_level"] == "B"
    assert item["is_official"] is False


def test_policy_duplicate(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持消费的通知")])
    item = collector.normalize_policy({"title": "关于支持消费的通知", "published_at": "2026-09-02", "url": "https://www.gov.cn/a.html"}, {"agency": "中国政府网", "policy_level": "national"}, date(2026, 9, 2), [])
    assert len(collector.deduplicate_policies([item, dict(item)])) == 1


def test_policy_future_pollution_is_filtered(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持半导体产业发展的通知", "2026-09-05")])
    result = collector.collect(date(2026, 9, 4), [{"theme_name": "半导体"}], as_of_time=datetime(2026, 9, 4, 15, 30, tzinfo=TZ))
    assert result.records == []


def test_policy_without_date_is_rejected(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持半导体产业发展的通知", "")])
    result = collector.collect(date(2026, 9, 2), [], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records == []
    assert any(item["reason"] == "missing_published_at" for item in result.rejected_records)


def test_old_policy_is_background_not_daily_event(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持半导体产业发展的通知", "2026-08-20")])
    result = collector.collect(date(2026, 9, 2), [], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records == []
    assert result.background_reference
    assert result.background_reference[0]["data_date"] == "2026-08-20"


def test_navigation_and_mojibake_titles_are_rejected(tmp_path):
    html = "<html><body><span>2026-09-02</span><a href='/policy.html'>友情链接</a><a href='/policy/b.html'>ÃÂåæç通知</a></body></html>"
    collector = _collector(tmp_path, [html])
    result = collector.collect(date(2026, 9, 2), [], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records == []
    assert {item["reason"] for item in result.rejected_records} >= {"navigation_title", "mojibake_title"}


def test_successful_empty_official_scan_is_empty_valid(tmp_path):
    collector = _collector(tmp_path, ["<html><body>no policy documents</body></html>"])
    result = collector.collect(date(2026, 9, 2), [], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records == []
    assert result.quality == "EMPTY_VALID"


def test_policy_no_related_content_is_allowed_as_official_scan(tmp_path):
    collector = _collector(tmp_path, [_html("关于公共服务事项的通知")])
    result = collector.collect(date(2026, 9, 2), [{"theme_name": "机器人"}], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.records
    assert result.records[0]["related_themes"] == []


def test_policy_partial_source_failure(tmp_path):
    collector = _collector(tmp_path, [_html("关于支持农业的通知"), TimeoutError("slow")])
    result = collector.collect(date(2026, 9, 2), [{"theme_name": "农业"}], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))
    assert result.failed_sources
    assert result.quality == "PARTIAL"


def test_policy_dedicated_adapters_use_official_source_headers():
    adapters = [MiitPolicyAdapter(), CsrcPolicyAdapter(), BsePolicyAdapter(), NeaPolicyAdapter()]
    assert [adapter.agency for adapter in adapters] == ["工信部", "证监会", "北交所", "国家能源局"]
    for adapter in adapters:
        headers = adapter.headers()
        assert "User-Agent" in headers
        assert headers["Referer"].startswith("https://")


def test_policy_collector_accepts_dedicated_adapter(tmp_path):
    adapter = MiitPolicyAdapter()

    def fetcher(source):
        assert source["agency"] == "工信部"
        return _html("关于支持智能制造发展的通知")

    collector = PolicyCollector(raw_root=tmp_path, source_fetcher=fetcher, adapters=[adapter])
    result = collector.collect(date(2026, 9, 2), [{"theme_name": "机器人"}], as_of_time=datetime(2026, 9, 2, 15, 30, tzinfo=TZ))

    assert result.scanned_sources == ["工信部"]
    assert result.records[0]["agency"] == "工信部"
    assert result.records[0]["evidence_level"] == "A"


def test_policy_sections_group_records(tmp_path):
    records = [
        {"policy_level": "national", "related_themes": ["AI"]},
        {"policy_level": "ministerial", "related_themes": []},
        {"policy_level": "local", "related_themes": ["消费"]},
    ]
    sections = build_policy_sections(records)
    assert len(sections["national_policies"]) == 1
    assert len(sections["ministerial_policies"]) == 1
    assert len(sections["related_theme_policies"]) == 2
