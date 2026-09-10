from datetime import datetime, date
from pathlib import Path
import json

import pytest

from src.opportunity_radar.contracts import SHANGHAI, normalize, visible, objective_guard
from src.opportunity_radar.coverage import coverage_matrix
from src.opportunity_radar.disclosure_body_extraction import extract_body, verified_body_relations
from src.opportunity_radar.enrichment import REGISTRY, parse_nbs, parse_dram, parse_monthly
from src.opportunity_radar.feedback import measure

BASE = {"source": "fixture", "source_tier": 1, "url": "https://www.stats.gov.cn/test",
        "first_seen_at": "2026-09-11T01:00:00+08:00", "source_path": "fixture.json",
        "provenance": {"sha256": "a"*64, "raw_sha256": "b"*64}}


def test_coverage_matrix_does_not_count_schema_as_live():
    matrix = coverage_matrix([], datetime(2026, 9, 11, tzinfo=SHANGHAI))
    assert len(matrix) == 16
    assert all(r["schema_supported"] and r["live_source_count"] == 0 for r in matrix)


def test_source_registry():
    for source in REGISTRY.values():
        assert source["url"].startswith("https://") and source["tier"] in range(1, 5)
        assert source["frequency"] and source["kind"]


def test_spot_vs_futures_semantics():
    html = '<meta name="PubDate" content="2026/09/10 09:30"><meta name="ArticleTitle" content="流通领域价格"><table><tr><td>铜</td><td>吨</td><td>100</td><td>2</td><td>2</td></tr></table>'
    row = parse_nbs(html, BASE)[0]
    assert row["facts"]["category"] == "SPOT_SURVEY_PRICE"
    assert row["unit"] == "CNY/吨"


@pytest.mark.parametrize("phrase", ["尚未形成订单", "尚未形成收入", "尚处验证阶段", "尚未量产", "预计未来", "拟开展", "有望", "可能", "不排除", "暂无", "未与某客户合作", "不涉及", "尚未商业化"])
def test_disclosure_negation(phrase):
    rows = extract_body("公司" + phrase + "，相关产品量产及合同订单情况如下。")
    assert all(r["facts"].get("event_type") != "ORDER_CONFIRMED" and r["facts"].get("current_stage") != "MASS_PRODUCTION" for r in rows)


def test_order_amount_parse():
    rows = extract_body("公司已签订合同，合同金额为人民币1.25亿元，占上年度营业收入的12.5%。")
    assert rows[0]["facts"]["contract_amount"] == 125000000
    assert rows[0]["facts"]["ratio_vs_last_year_revenue"] == 12.5
    assert rows[0]["facts"]["event_type"] == "ORDER_CONFIRMED"


def test_customer_validation_stage():
    row = extract_body("公司新产品目前尚处客户验证阶段。 ")[0]
    assert row["facts"]["event_type"] == "CUSTOMER_VALIDATION"


def test_commercialization_stage():
    assert extract_body("公司产品已实现量产并交付。 ")[0]["facts"]["current_stage"] == "MASS_PRODUCTION"
    assert extract_body("公司产品尚未实现量产。 ")[0]["facts"]["current_stage"] is None


def test_verified_relation_provenance_and_taxonomy_rejection():
    assert not verified_body_relations("公司属于MLCC概念。", "test", "000001", BASE)
    assert not verified_body_relations("公司主要从事MLCC生产。", "test", "000001", {**BASE, "source_tier": 4})
    edge = verified_body_relations("公司主要从事MLCC生产。", "test", "000001", BASE)[0]
    assert edge["provenance"] == BASE["provenance"] and edge["transmission_depth"] == 1


def test_storage_source():
    html = '<table><tr><td>DRAM Spot Price Last Update: Sep.10 2026 18:10</td></tr></table><table><tr><td>DDR5</td><td>5</td><td>4</td><td>5</td><td>4</td><td>4.5</td><td>1.2%</td></tr></table>'
    row = parse_dram(html, {**BASE, "source_tier": 3})[0]
    assert row["value"] == 4.5 and row["facts"]["category"] == "SPOT_QUOTE"


@pytest.mark.parametrize("code,theme", [("2408", "存储"), ("3363", "光通信"), ("2383", "PCB/CCL"), ("2327", "MLCC"), ("6223", "探针/测试")])
def test_overseas_technology_monthly_sources(code, theme):
    payload = [{"公司代號": code, "公司名稱": "fixture", "出表日期": "1150910", "資料年月": "11508", "營業收入-當月營收": "123"}]
    row = parse_monthly(json.dumps(payload), {**BASE, "source_tier": 2})[0]
    assert row["theme"] == theme and row["unit"] == "TWD_thousand"
    assert row["signal_type"] == "OVERSEAS_LEAD"


def test_macro_vintage_and_first_seen():
    html = '<meta name="PubDate" content="2026/09/10 09:30"><meta name="ArticleTitle" content="居民消费价格"><p>居民消费价格同比上涨1.5%。</p>'
    row = normalize(parse_nbs(html, BASE)[0])
    assert row["facts"]["revision_version"] == "b"*64
    assert not visible(row, datetime(2026, 9, 10, 20, tzinfo=SHANGHAI))


def test_lead_time_point_in_time_only():
    assert measure([{"observation_mode": "RETROSPECTIVE_SERIES"}], [], [], date(2026, 9, 11))["records"] == []


@pytest.mark.parametrize("key", ["beneficiary_priority", "undervalued", "overvalued", "opportunity_score"])
def test_no_final_judgement(key):
    with pytest.raises(ValueError):
        objective_guard({key: 1})


def test_morning_eod_scheduler():
    text = (Path(__file__).parents[2] / ".github/workflows/opportunity-radar.yml").read_text()
    assert "10 0 * * 1-5" in text and "10 8 * * 1-5" in text
    assert "Asia/Shanghai" in text and "if: always()" in text and "exit 1" in text


def test_real_counterexample_rejects_synthetic_or_missing_outcomes():
    from src.opportunity_radar.coverage import validate_counterexample
    with pytest.raises(ValueError):
        validate_counterexample({"event": "signed framework only"})
    case = {k: "fixture" for k in ("event", "objective_facts", "later_market_result", "why_not_counted_as_success")}
    case.update(observation_mode="SYNTHETIC_TEST", source_evidence=[{"url": "https://example.com", "sha256": "a"*64}])
    with pytest.raises(ValueError):
        validate_counterexample(case)


def test_production_failure_receipt(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tools import run_opportunity_radar_production as producer
    monkeypatch.setattr(producer, "load_trading_calendar", lambda *a, **k: [SimpleNamespace(cal_date=date(2026, 9, 11), is_open=True)])
    class Failed:
        def __init__(self, root):
            pass
        def build(self, *a, **k):
            raise ValueError("fixture production failure")
    monkeypatch.setattr(producer, "RadarPipeline", Failed)
    with pytest.raises(ValueError):
        producer.run(tmp_path, date(2026, 9, 11), "MORNING")
    receipt = json.loads((tmp_path / "data/opportunity_radar/diagnostics/2026-09-11_morning_production.json").read_text())
    assert receipt["status"] == "FAILED" and receipt["blocker"] == "fixture production failure"
    assert not (tmp_path / "data/opportunity_radar/2026-09-11_morning.json").exists()


def test_semantic_dedup_ignores_absent_optional_field():
    from src.opportunity_radar.storage import semantic_key
    assert semantic_key({"entity": "x"}) == semantic_key({"entity": "x", "theme": None})


def test_auction_and_review_adapter_never_adds_score(tmp_path):
    from src.opportunity_radar.pipeline import read_only_summary
    assert read_only_summary(tmp_path, date(2026, 9, 11))["score_effect"] == 0


def test_relation_retrieval_dedup_preserves_earliest_seen():
    from src.opportunity_radar.relations import merge_relations
    edge = {"from": "a", "to": "b", "relationship_type": "PRODUCER", "evidence": "explicit statement",
            "first_seen_at": "2026-09-10T10:00:00+08:00"}
    assert merge_relations([{**edge, "first_seen_at": "2026-09-11T10:00:00+08:00"}, edge]) == [edge]


def test_compact_size_guard_against_real_shape():
    from src.opportunity_radar.pipeline import compact
    path = Path(__file__).parents[2] / "data/opportunity_radar/2026-09-11_morning.json"
    if not path.exists():
        pytest.skip("Frozen acceptance artifact not present")
    packet = compact(json.loads(path.read_text(encoding="utf-8")))
    assert len(json.dumps(packet, ensure_ascii=False, indent=2).encode()) < 200_000
    assert "compact_size_warning" in packet["compact_metadata"]


@pytest.mark.parametrize("sentence", [
    "截至本公告日，以上项目未签订正式合同，后续合同的签订尚存在不确定性。",
    "销售模式为直接面向下游客户进行技术推介、签订合同并交付。",
    "公司已签署股票质押合同，合同金额为人民币1亿元。",
    "公司已签署借款合同，合同金额为人民币1亿元。",
    "双方签署本协议不会与其他合同协议约定相违背。",
])
def test_real_disclosure_clause_regressions(sentence):
    assert all(r["facts"].get("event_type") != "ORDER_CONFIRMED" for r in extract_body(sentence))


def test_monthly_and_cumulative_production_never_share_metric():
    html = '<meta name="PubDate" content="2026/08/17 09:30"><meta name="ArticleTitle" content="2026年7月份能源生产情况"><p>7月份，规上工业原煤产量3.4亿吨。1—7月份，规上工业原煤产量27.0亿吨。</p>'
    rows = parse_nbs(html, BASE)
    assert [(r["metric"], r["value"]) for r in rows] == [("production_monthly", 3.4), ("production_ytd", 27)]


def test_withdrawn_parser_rows_are_excluded():
    from src.opportunity_radar.contracts import evidence_eligible
    assert not evidence_eligible({"stock_code": "000001", "facts": {"body_parsed": True}})
    assert not evidence_eligible({"source": "NBS", "metric": "reported_production"})
    assert evidence_eligible({"stock_code": "000001", "facts": {"body_parsed": True, "parser_version": "DISCLOSURE_BODY_V21_3"}})


def test_shareholder_lockup_is_not_reduction():
    sentence = "自完成过户登记之日起12个月内，不以任何方式减持其通过本次交易取得的股份。"
    assert all(not r["facts"].get("action") for r in extract_body(sentence))
    actual = "公司股东通过集中竞价交易方式累计减持本公司股份1,000,000股。"
    assert extract_body(actual)[0]["facts"]["action"] == "DECREASE_HOLDING"


def test_overseas_xbrl_keeps_period_basis_and_filing_vintage():
    from src.opportunity_radar.enrichment import parse_sec
    payload = {"entityName": "fixture", "cik": 1, "facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {"form": "10-Q", "filed": "2026-08-01", "end": "2026-06-30", "start": "2026-04-01", "val": 10, "accn": "fixture"}
    ]}}}}}
    row = parse_sec(json.dumps(payload), {**BASE, "source_tier": 2})[0]
    assert row["facts"]["period_basis"] == "DURATION_91_DAYS"
    assert row["facts"]["observation_mode"] == "RETROSPECTIVE_SERIES"
    assert row["published_at"] == "2026-08-01"
