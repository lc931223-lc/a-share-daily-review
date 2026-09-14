"""All synthetic documents stay in tmp_path and never reach production FactStore."""
import copy
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src.opportunity_radar.company_evidence import (
    PARSER, REVISION_METRICS, body_facts, expectation_revision, parse_amd_expectations, technology_stage, valid_relation,
)
from src.opportunity_radar.contracts import SHANGHAI, normalize, stamp, visible, objective_guard, evidence_eligible
from src.opportunity_radar.objective_features import price_features, divergence_label
from src.opportunity_radar.objective_scoring import objective_score, freshness, enrich_candidates
from src.opportunity_radar.pipeline import _verify_sources, candidates
from src.opportunity_radar.changes import latest_changes
from src.opportunity_radar.storage import ObservationStore, archive_json
from src.opportunity_radar.relations import transmission_paths, merge_relations

BASE = {"source": "fixture", "source_tier": 1, "url": "https://www.sse.com.cn/fixture",
        "first_seen_at": "2026-09-15T01:00:00+08:00", "source_path": "fixture.json", "provenance": {"sha256": "a"*64}}
ITEM = {"stock_code": "000001", "stock_name": "fixture", "theme": "光通信", "title": "2026年半年度报告", "published_at": "2026-08-28"}


@pytest.mark.parametrize("text,expected", [
    ("公司CPO产品预计未来量产", None), ("公司CPO产品尚未量产", None),
    ("公司CPO产品正在研发", "RESEARCH"), ("公司CPO产品工程样片已送样", "ENGINEERING_SAMPLE"),
    ("公司CPO产品客户验证中", "CUSTOMER_VALIDATION"),
    ("公司CPO产品已实现小批量生产", "SMALL_SCALE_PRODUCTION"),
    ("公司CPO产品已实现量产", "MASS_PRODUCTION"),
    ("公司CPO产品已小批量出货", "SMALL_SCALE_PRODUCTION"),
    ("公司CPO产品渗透率提升至25%", "RAPID_PENETRATION"),
])
def test_stage_negations_and_actual_predicates(text, expected):
    assert technology_stage(text) == expected


@pytest.mark.parametrize("body", ["公司主营业务是光芯片的研发、生产和销售。", "公司产品研发失败风险仍存在。", "CPO技术发布规划。"])
def test_boilerplate_and_headline_are_not_breakthrough(body):
    events, _ = body_facts(body, ITEM, BASE)
    assert not any(e["signal_type"] == "TECHNOLOGY_BREAKTHROUGH" for e in events)


def test_technology_body_evidence_not_other_product_stage():
    events, _ = body_facts("公司CPO产品正在研发；MLCC产品已实现量产。", ITEM, BASE)
    assert not any(e["facts"].get("technology") == "CPO" and e["facts"]["current_stage"] == "MASS_PRODUCTION" for e in events)


def test_corporate_report_table_not_toc():
    body = "第三节 管理层讨论与分析 ...... 10\n第二节 主要财务指标\n营业收入（元） 120.00 100.00 20.00%\n归属于上市公司股东的净利\n润（元） 20.00 10.00 100.00%\n第三节 管理层讨论与分析"
    events, _ = body_facts(body, ITEM, BASE)
    financial = [e for e in events if e["signal_type"] == "REVENUE_PROFIT_MARGIN"]
    assert len(financial) == 2
    assert {e["facts"]["fundamental_change_pct"] for e in financial} == {20, 100}
    assert all(e["facts"]["observation_mode"] == "HISTORICAL_BACKFILL" for e in financial)
    assert not any(e["signal_type"] == "EXPECTATION_REVISION" for e in events)


def pair(metric="revenue_revision"):
    prior = {**BASE, "stock_code": "000001", "period": "2026H1", "unit": "CNY", "basis": "CONSOLIDATED",
        "expectation_metric": metric, "value": 100, "expectation_source_type": "COMPANY_PRIOR_GUIDANCE",
        "published_at": "2026-07-10", "body_evidence": "fixture prior guidance"}
    return prior, {**prior, "value": 120, "published_at": "2026-08-28", "expectation_source_type": "LATEST_REPORTED_FACT"}


@pytest.mark.parametrize("metric", sorted(REVISION_METRICS))
def test_ten_expectation_metrics(metric):
    result = expectation_revision(*pair(metric))
    assert result["revision_pct"] == 20 and result["revision_abs"] == 20 and result["revision_direction"] == "UP"
    assert result["prior_evidence"]["first_seen_at"] == BASE["first_seen_at"]


@pytest.mark.parametrize("key,value", [("period", "2026Q3"), ("unit", "USD"), ("basis", "NON_GAAP"), ("stock_code", "000002")])
def test_expectation_pair_scope_rejects_mismatch(key, value):
    prior, latest = pair()
    latest[key] = value
    with pytest.raises(ValueError, match="MISMATCH"):
        expectation_revision(prior, latest)


def test_yoy_missing_provenance_and_zero_prior():
    prior, latest = pair()
    with pytest.raises(ValueError, match="NOT_YOY"):
        expectation_revision({**prior, "expectation_source_type": "YOY"}, latest)
    with pytest.raises(ValueError, match="PROVENANCE"):
        expectation_revision({**prior, "body_evidence": ""}, latest)
    assert expectation_revision({**prior, "value": 0}, latest)["revision_pct"] is None


def test_amd_guidance_actual_table_same_quarter():
    a = parse_amd_expectations("For the second quarter of 2026, AMD expects revenue to be approximately $11.2 billion, plus or minus $300 million.", BASE)
    b = parse_amd_expectations("AMD announced financial results for the second quarter of 2026. Revenue ($M) $11,536 $7,000", BASE)
    assert a[0]["period"] == b[0]["period"] == "2026Q2"
    assert a[0]["value"] == 11200 and b[0]["value"] == 11536


def test_relation_verified_requires_economics_and_evidence():
    _, edges = body_facts("公司主要从事光模块生产与销售。", ITEM, BASE)
    assert edges and all(valid_relation(e) for e in edges)
    assert all(e["revenue_exposure"] is None for e in edges)
    assert not body_facts("公司属于光模块概念。", ITEM, BASE)[1]
    assert not valid_relation({**edges[0], "verification_basis": "CLASSIFICATION_ONLY"})
    assert not valid_relation({**edges[0], "relation_status": "PARTIAL"})
    assert not valid_relation({**edges[0], "source_tier": 4})
    assert not transmission_paths([{**edges[0], "relation_status": "CLASSIFICATION_ONLY"}], stamp(BASE["first_seen_at"]))


def test_parser_version_dedup_and_old_evidence_quarantine():
    _, edges = body_facts("公司主要从事光模块生产与销售。", ITEM, BASE)
    versions = merge_relations([edges[0], {**edges[0], "parser_version": "COMPANY_EVIDENCE_V1"}])
    assert len(versions) == 2
    assert not evidence_eligible({"stock_code": "000001", "facts": {"body_parsed": True, "parser_version": "COMPANY_EVIDENCE_V1"}})


def test_shared_product_cannot_imply_customer_supplier_transmission():
    _, edges = body_facts("公司主要从事光模块生产与销售。", ITEM, BASE)
    other = {**edges[0], "from": "fixture-other", "to": "光模块", "stock_code": "000002", "relationship_type": "PRODUCER"}
    result = transmission_paths(edges+[other], stamp(BASE["first_seen_at"]))
    assert all(r["transmission_depth"] == 1 for r in result)


def test_repeated_expectation_fetch_is_one_current_pair():
    from src.opportunity_radar.enrichment import observation
    prior, latest = pair()
    facts = expectation_revision(prior, latest)
    raw = observation(BASE, "EXPECTATION_REVISION", "fixture", "earnings_revision:2026H1", None, "2026-08-28", facts,
                      stock_code="000001", body_evidence="fixture actual table")
    newer = {**raw, "first_seen_at": "2026-09-15T02:00:00+08:00", "facts": {**facts, "guidance_comparison_basis": "DISCLOSED_POINT_ESTIMATE"}}
    selected = latest_changes([normalize(raw), normalize(newer)], stamp("2026-09-15T08:00:00+08:00"))
    assert len(selected) == 1
    assert len(selected[0]["history_references"]) == 1


def test_return_windows_duplicate_and_suspension_are_not_compressed():
    days = [(date(2026, 6, 1)+timedelta(days=i)).isoformat() for i in range(60)]
    rows = [{"trade_date": d, "pct_chg": 1} for d in days]
    assert price_features(rows, days)["stock_return_20d"] == pytest.approx(100*(1.01**20-1))
    assert price_features(rows[:-1], days)["stock_return_1d"] is None
    assert price_features(rows[:-2]+rows[-1:], days)["stock_return_5d"] is None
    assert price_features(rows+[{"trade_date": days[-1], "pct_chg": 2}], days)["stock_return_1d"] is None
    assert price_features(rows+rows, days)["stock_return_20d"] is not None


@pytest.mark.parametrize("fund,ret,val,label", [(20, 2, None, "FUNDAMENTALS_UP_PRICE_LAGGING"),
    (20, 10, None, "FUNDAMENTALS_UP_PRICE_CONFIRMED"), (0, 30, None, "FUNDAMENTALS_FLAT_PRICE_OVERHEATED"),
    (-20, 10, None, "FUNDAMENTALS_DOWN_PRICE_NOT_PRICED"), (20, 30, 95, "HIGH_EXPECTATION_RISK"),
    (None, 10, 1, None)])
def test_divergence_not_low_pe(fund, ret, val, label):
    assert divergence_label(fund, ret, val) == label


def test_missing_components_reduce_score_and_confidence():
    thin = objective_score({"evidence_quality": 100})
    assert thin["objective_opportunity_score"] is None and thin["confidence"] == "LOW"
    partial = objective_score({"fundamental_change": 100, "technology": 100, "price_confirmation": 100, "evidence_quality": 100})
    assert partial["objective_opportunity_score"] == 40 and partial["confidence"] == "LOW"
    assert partial["expectation_revision_score"] is None
    assert objective_score({k: 100 for k in partial["score_weights"]}, 100, 100)["objective_opportunity_score"] == 80
    objective_guard(partial)
    with pytest.raises(ValueError):
        objective_guard({"opportunity_rank": 1})


def test_first_seen_after_event_and_morning_eod_separation():
    raw = {**BASE, "signal_type": "TECHNOLOGY_BREAKTHROUGH", "entity": "fixture", "source_date": "2026-09-14",
           "event_date": "2026-09-14", "published_at": "2026-09-14", "facts": {}, "value": None, "body_evidence": "fixture"}
    row = normalize(raw)
    assert not visible(row, stamp("2026-09-14T08:00:00+08:00"))
    assert not visible(row, stamp("2026-09-14T23:59:59+08:00"))
    assert visible(row, stamp("2026-09-15T08:00:00+08:00"))
    assert not visible({**row, "event_date": "2026-09-16"}, stamp("2026-09-17T08:00:00+08:00"))


def test_stale_and_backfill_not_overnight_positive():
    raw = {**BASE, "signal_type": "TECHNOLOGY_BREAKTHROUGH", "entity": "fixture", "source_date": "2026-08-01",
           "event_date": "2026-08-01", "published_at": "2026-08-01", "facts": {"current_stage": "MASS_PRODUCTION", "observation_mode": "HISTORICAL_BACKFILL"},
           "value": None, "body_evidence": "actual fixture mass production"}
    selected = latest_changes([normalize(raw)], stamp(BASE["first_seen_at"]))
    assert candidates(selected) == ([], [])
    assert freshness({**selected[0], "signal_type": "SUPPLY_DEMAND", "source_date": "2026-01-01"}, stamp(BASE["first_seen_at"]))["status"] == "STALE"


def test_nested_guidance_hash_is_verified(tmp_path):
    archive = archive_json(tmp_path, "fixture", {"data_role": "SYNTHETIC_TEST"})
    ref = {"source_path": archive.relative_to(tmp_path).as_posix(), "provenance": {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}}
    packet = {"source_manifest": [], "facts": {"prior_evidence": ref}}
    _verify_sources(tmp_path, packet)
    archive.write_text("tampered", encoding="utf8")
    with pytest.raises(ValueError, match="PROVENANCE"):
        _verify_sources(tmp_path, packet)


def test_mainland_forecast_range_keeps_midpoint_and_scope():
    from src.opportunity_radar.company_evidence import issuer_expectations
    forecast = {**ITEM, "title": "2026年半年度业绩预告", "published_at": "2026-07-10"}
    rows = issuer_expectations("预计归属于上市公司股东的净利润盈利：10,000万元至12,000万元。", forecast, BASE, [])
    assert rows[0]["value"] == 110000000
    assert rows[0]["guidance_low"] == 100000000 and rows[0]["guidance_high"] == 120000000
    actual = {**rows[0], "value": 115000000, "published_at": "2026-08-28", "expectation_source_type": "LATEST_REPORTED_FACT"}
    result = expectation_revision(rows[0], actual)
    assert result["outside_guidance_range"] is False
    assert result["guidance_comparison_basis"] == "DISCLOSED_RANGE_MIDPOINT"
    assert not issuer_expectations("预计归属于上市公司股东的净利润同比增加10,000万元至12,000万元。", forecast, BASE, [])


def test_company_packet_scoring_compact_and_exact_as_of(tmp_path):
    from src.opportunity_radar.pipeline import RadarPipeline, compact, validate, read_context
    from src.opportunity_radar.enrichment import observation
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "config").mkdir()
    for name in ("opportunity_radar_evidence_sources.json", "opportunity_radar_taxonomy.json"):
        (tmp_path / "config" / name).write_bytes((root / "config" / name).read_bytes())
    receipt = archive_json(tmp_path, "fixture", {"data_role": "SYNTHETIC_TEST"})
    base = {**BASE, "source_path": receipt.relative_to(tmp_path).as_posix(),
            "provenance": {"sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(), "kind": "TEST_FIXTURE"}}
    raw = observation(base, "REVENUE_PROFIT_MARGIN", "fixture", "reported_earnings", 120, "2026-08-28",
        {"fundamental_change_pct": 20, "financial_metric": "earnings", "observation_mode": "HISTORICAL_BACKFILL"},
        stock_code="000001", stock_name="fixture", theme="光通信", body_evidence="fixture reported table")
    from src.market_packet import trading_calendar
    reference = tmp_path / "data/reference"
    reference.mkdir(parents=True)
    (reference / "trade_calendar_2026.json").write_text(json.dumps({"rows": [{"cal_date": "2026-09-14", "is_open": 1}, {"cal_date": "2026-09-15", "is_open": 1}]}))
    pipeline = RadarPipeline(tmp_path, now=lambda: stamp("2026-09-15T08:00:00+08:00"))
    later = {**raw, "value": 999, "first_seen_at": "2026-09-15T16:00:00+08:00"}
    packet = pipeline.build(date(2026, 9, 15), "MORNING", rows=[normalize(raw), normalize(later)])
    full, small, _ = pipeline.write(packet)
    company = packet["company_specific_candidates"][0]
    assert company["objective_opportunity_score"] is None
    assert company["fundamental_change_score"] == 60
    assert len(packet["fundamental_change_observations"]) == 1
    assert not packet["positive_change_candidates"]
    validate(compact(packet))
    assert small.stat().st_size < 200000
    assert read_context(tmp_path, date(2026, 9, 15))["score_effect"] == 0
    frozen = full.read_bytes()
    eod = RadarPipeline(tmp_path, now=lambda: stamp("2026-09-15T18:00:00+08:00"))
    eod.write(eod.build(date(2026, 9, 15), "EOD", rows=[normalize(raw), normalize(later)]))
    assert full.read_bytes() == frozen
