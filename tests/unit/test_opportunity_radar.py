"""Synthetic counterexamples never enter production data or historical statistics."""
import copy
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import shutil
import hashlib

import pytest

from src.opportunity_radar.contracts import CATEGORIES, FIELDS, FORBIDDEN, SHANGHAI, normalize, stamp, visible, objective_guard
from src.opportunity_radar.changes import series_changes, latest_changes, transition, fundamental_changes, divergence
from src.opportunity_radar.feedback import confirmation, measure
from src.opportunity_radar.pipeline import RadarPipeline, candidates, compact, validate, read_context
from src.opportunity_radar.relations import transmission_paths
from src.opportunity_radar.sources import tier
from src.opportunity_radar.storage import ObservationStore

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 9, 10)
CUTOFF = datetime(2026, 9, 10, 8, tzinfo=SHANGHAI)
FIXTURE_BYTES = b'{"data_role":"TEST_FIXTURE"}\n'


def observation(category="COMMODITY_PRICE", **changes):
    raw = {"signal_type": category, "entity": "fixture-entity", "theme": "fixture-theme", "metric": "price",
           "value": 100, "facts": {}, "source": "fixture-exchange", "source_tier": 1,
           "unit": "CNY/tonne", "currency": "CNY", "source_date": "2026-09-09", "event_date": "2026-09-09",
           "effective_date": None, "published_at": "2026-09-09T17:00:00+08:00", "first_seen_at": "2026-09-09T18:00:00+08:00",
           "url": "https://www.sse.com.cn/fixture", "source_path": "fixture.json",
           "provenance": {"sha256": hashlib.sha256(FIXTURE_BYTES).hexdigest(), "kind": "TEST_FIXTURE"}}
    raw.update(changes)
    return raw


@pytest.fixture
def root(tmp_path):
    (tmp_path / "fixture.json").write_bytes(FIXTURE_BYTES)
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config/opportunity_radar_taxonomy.json", tmp_path / "config")
    ref = tmp_path / "data/reference"
    ref.mkdir(parents=True)
    days = [DAY-timedelta(days=i) for i in range(80)]
    (ref / "trade_calendar_2026.json").write_text(json.dumps({"rows": [{"cal_date": str(d), "is_open": int(d.weekday()<5)} for d in days]}), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("category", list(CATEGORIES))
def test_all_16_signal_categories_schema_and_factor41(root, category):
    row = normalize(observation(category))
    assert set(FIELDS[category].split()) <= set(row["facts"])
    assert all(1 <= fid <= 41 for fid in row["mapped_factor_ids"])
    p = RadarPipeline(root, now=lambda: CUTOFF).build(DAY, "MORNING", rows=[row])
    validate(p)
    assert p[CATEGORIES[category]]
    assert p["meta"]["data_role"] == "OBJECTIVE_OPPORTUNITY_EVIDENCE"


@pytest.mark.parametrize("field", sorted(FORBIDDEN))
def test_objective_opportunity_no_final_judgement(field):
    with pytest.raises(ValueError, match="FORBIDDEN"):
        normalize(observation(facts={field: 1}))


def test_commodity_inflection_and_missing_windows():
    data = list(range(100, 80, -1)) + [95, 105]
    changes = series_changes(data)
    assert changes["change_label"] == "PRICE_INFLECTION_CANDIDATE"
    assert changes["percentile_250d"] is None
    assert changes["slope_3d"] > 0 > changes["slope_20d"]
    assert series_changes([1, None, 3]) == {}
    assert series_changes([0, 10])["change_1d"] is None


def test_supply_demand_change_and_source_units_do_not_mix():
    a = normalize(observation("SUPPLY_DEMAND", value=10, source_date="2026-09-08", metric="inventory"))
    b = normalize(observation("SUPPLY_DEMAND", value=20, metric="inventory"))
    rows = latest_changes([a, b], CUTOFF)
    assert rows[0]["changes"]["delta"] == 10
    assert len(candidates(rows)[1]) == 1
    c = normalize(observation("SUPPLY_DEMAND", unit="USD/tonne", value=80))
    assert len(latest_changes([a, b, c], CUTOFF)) == 2


@pytest.mark.parametrize("category,stage", [
    ("CAPACITY_AND_UTILIZATION", "ANNOUNCED_CAPACITY"), ("POLICY_AND_FISCAL", "FUNDING"),
    ("TECHNOLOGY_BREAKTHROUGH", "LAB"), ("PRODUCT_COMMERCIALIZATION", "CUSTOMER_VALIDATION"),
    ("CUSTOMER_AND_ORDER", "FRAMEWORK_AGREEMENT"), ("M&A_AND_CAPITAL_OPERATION", "INTENTION"),
])
def test_explicit_stage_not_title_inference(category, stage):
    field = "policy_stage" if category == "POLICY_AND_FISCAL" else "current_stage"
    row = observation(category, facts={field: stage}, body_evidence="explicit stage in fixture body")
    assert normalize(row)["facts"][field] == stage
    row.pop("body_evidence")
    with pytest.raises(ValueError, match="TITLE"):
        normalize(row)


@pytest.mark.parametrize("title", ["签署战略协议", "与头部客户合作", "进入验证", "产品可用于AI", "拟扩产", "政策支持", "海外同行上涨"])
def test_title_not_order_confirmation_or_revenue(title):
    row = normalize(observation("CUSTOMER_AND_ORDER", title=title, value=None))
    assert row["facts"]["event_type"] is None
    assert row["facts"]["contract_amount"] is None
    assert candidates(latest_changes([row], CUTOFF)) == ([], [])


def test_commercialization_transition_has_two_evidenced_stages():
    a = normalize(observation("PRODUCT_COMMERCIALIZATION", facts={"current_stage": "CUSTOMER_VALIDATION"}, body_evidence="validation", source_date="2026-09-08"))
    b = normalize(observation("PRODUCT_COMMERCIALIZATION", facts={"current_stage": "SMALL_BATCH"}, body_evidence="small batch"))
    assert transition(a, b)["state_transition"] is True
    assert b["facts"]["current_stage"] != "MASS_PRODUCTION"


def test_fundamental_acceleration_and_expectation_revision():
    result = fundamental_changes({"profit_yoy": -10}, {"profit_yoy": -30}, {"profit_yoy": -40})
    assert result["profit_yoy_delta"] == 20
    assert result["profit_yoy_acceleration"] == 10
    assert result["revenue_yoy_acceleration"] is None
    assert normalize(observation("EXPECTATION_REVISION", value=None))["facts"]["consensus_eps_current"] is None


@pytest.mark.parametrize("category", ["INDUSTRY_COMPETITION", "SHAREHOLDER_MANAGEMENT_ACTION", "OVERSEAS_LEAD", "MACRO_LIQUIDITY_FX_RATES", "MARKET_STRUCTURE_AND_FLOW"])
def test_generic_changes_have_no_research_conclusion(category):
    a = normalize(observation(category, source_date="2026-09-08", value=100))
    b = normalize(observation(category, value=105))
    rows = latest_changes([a, b], CUTOFF)
    assert rows[0]["changes"]["change_1d"] == pytest.approx(5)
    objective_guard(rows)


def test_valuation_fundamental_divergence_is_only_candidate():
    assert divergence(10, 0) == "FUNDAMENTAL_UP_PRICE_FLAT"
    assert divergence(10, -5) == "FUNDAMENTAL_UP_PRICE_DOWN"
    assert divergence(-10, 5) == "FUNDAMENTAL_DOWN_PRICE_UP"
    assert divergence(None, 5) is None


def test_company_specific_alpha_does_not_require_strong_theme():
    a = normalize(observation("REVENUE_PROFIT_MARGIN", stock_code="000001", theme=None, source_date="2026-09-08", value=10))
    b = normalize(observation("REVENUE_PROFIT_MARGIN", stock_code="000001", theme=None, value=12))
    positive, _ = candidates(latest_changes([a, b], CUTOFF))
    assert positive[0]["candidate_type"] == "COMPANY_SPECIFIC_CANDIDATE"


def test_second_and_third_order_transmission_and_cycles():
    edges = []
    for a, b in [("HBM", "packaging"), ("packaging", "test"), ("test", "probe"), ("probe", "HBM")]:
        edges.append(observation(**{"from": a, "to": b, "relationship_type": "EQUIPMENT_SUPPLIER", "confidence": .8}))
    paths = transmission_paths(edges, CUTOFF)
    assert {r["transmission_depth"] for r in paths} == {1, 2, 3}
    assert all(r["upstream_theme"] != r["downstream_theme"] for r in paths)
    assert all(r["revenue_exposure"] is None for r in paths)
    edges[0]["first_seen_at"] = "2026-09-11T00:00:00+08:00"
    assert not any(p["upstream_theme"] == "HBM" for p in transmission_paths(edges, CUTOFF))


@pytest.mark.parametrize("chain", ["存储", "光通信", "探针测试", "MLCC", "PCB_CCL", "先进封装", "半导体设备", "机器人"])
def test_technology_chain_taxonomy_not_company_evidence(root, chain):
    payload = json.loads((root / "config/opportunity_radar_taxonomy.json").read_text(encoding="utf-8"))
    assert payload["chains"][chain]
    assert "NOT_VERIFIED_COMPANY_RELATION" in payload["data_role"]


def test_no_future_leakage_publication_first_seen_and_revision(root):
    old = normalize(observation(source_date="2026-09-08", value=10))
    revised = normalize(observation(source_date="2026-09-08", value=100, first_seen_at="2026-09-11T00:00:00+08:00"))
    future_publication = normalize(observation(published_at="2026-09-11T00:00:00+08:00"))
    assert len(latest_changes([old, revised, future_publication], CUTOFF)) == 1
    assert latest_changes([old, revised], CUTOFF)[0]["value"] == 10
    assert not visible(normalize(observation(first_seen_at=None)), CUTOFF)


def test_frozen_morning_no_eod_overwrite_and_readonly_context(root):
    pipeline = RadarPipeline(root, now=lambda: CUTOFF)
    packet = pipeline.build(DAY, "MORNING", rows=[normalize(observation())])
    full, small, _ = pipeline.write(packet)
    before = full.read_bytes()
    changed = copy.deepcopy(packet)
    changed["commodity_observations"][0]["value"] = 777
    pipeline.write(changed)
    assert full.read_bytes() == before and small.exists()
    assert read_context(root, DAY)["score_effect"] == 0
    eod = RadarPipeline(root, now=lambda: datetime(2026, 9, 10, 18, tzinfo=SHANGHAI))
    eod.write(eod.build(DAY, "EOD", rows=[]))
    assert full.read_bytes() == before
    with pytest.raises(ValueError, match="DEADLINE"):
        eod.build(DAY, "MORNING", rows=[])


def test_storage_preserves_first_seen_and_revisions(root):
    store = ObservationStore(root)
    a = observation()
    receipt = root / "fixture.json"
    receipt.write_text('{"data_role": "TEST_FIXTURE"}', encoding="utf-8")
    a["provenance"]["sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    store.append([a])
    store.append([dict(a, first_seen_at="2026-09-10T07:00:00+08:00")])
    store.append([dict(a, value=200, first_seen_at="2026-09-11T07:00:00+08:00")])
    assert len(store.all()) == 2
    assert latest_changes(store.all(), CUTOFF)[0]["value"] == 100


@pytest.mark.parametrize("body", ["尚未形成订单", "预计未来产生收入", "产品仍在研发", "验证中", "no order yet", "签署战略协议", "通过客户验证", "产品可用于AI", "海外同行上涨"])
def test_negated_body_cannot_confirm_order(body):
    with pytest.raises(ValueError, match="NEGATED"):
        normalize(observation("CUSTOMER_AND_ORDER", body_evidence=body, facts={"event_type": "ORDER_CONFIRMED"}))


def test_provenance_receipt_required(root):
    with pytest.raises(ValueError, match="PROVENANCE"):
        ObservationStore(root).append([observation(source_path="missing.json")])


def test_lead_time_fixed_rule_and_censoring():
    days = [str(date(2026, 8, 1) + timedelta(days=i)) for i in range(30)]
    signal = {"entity": "x", "signal_type": "COMMODITY_PRICE", "signal_first_seen_date": days[0]}
    market = [{"entity": "x", "date": d, "as_of_valid": True, "relative_return_5d": 4, "breadth": .7, "amount_ratio_20d": 1.4} for d in days[1:21]]
    result = measure([signal], market, days, days[-1])
    assert result["median_lead_time"] == 1
    assert result["market_confirmation_rate"] == 1
    assert measure([signal], market[:3], days[:4], days[3])["market_confirmation_rate"] is None


COUNTEREXAMPLES = ["commodity_up_stock_flat", "policy_no_market_response", "overseas_up_a_share_flat", "disclosure_up_stock_down", "technology_without_commercialization", "large_order_low_margin", "buyback_deteriorating_business", "earnings_growth_price_already_up", "price_up_demand_collapse", "capacity_expansion_oversupply"]


@pytest.mark.parametrize("case", COUNTEREXAMPLES)
def test_counterexample_no_automatic_market_confirmation(case):
    assert confirmation({"relative_return_5d": 0, "breadth": .4, "amount_ratio_20d": .8}) is False
    assert confirmation({"relative_return_5d": 10, "breadth": None, "amount_ratio_20d": 2}) is None
    row = normalize(observation(title=case, value=None))
    assert candidates(latest_changes([row], CUTOFF)) == ([], [])
    # Even a measured positive change remains a failed market-confirmation case.
    earlier = normalize(observation(source_date="2026-09-08", value=100, title=case))
    later = normalize(observation(value=110, title=case))
    positive, _ = candidates(latest_changes([earlier, later], CUTOFF))
    signal = dict(positive[0], signal_first_seen_date="2026-08-01")
    days = [str(date(2026, 8, 1)+timedelta(days=i)) for i in range(25)]
    market = [{"entity": "fixture-theme", "date": d, "as_of_valid": True, "relative_return_5d": -2,
               "breadth": .4, "amount_ratio_20d": .8} for d in days[1:21]]
    result = measure([signal], market, days, days[-1])
    assert result["false_positive_rate"] == 1
    assert result["market_confirmation_rate"] == 0


def test_source_tier_and_tier4_not_confirmed():
    assert tier("https://static.cninfo.com.cn/a.pdf") == 1
    assert tier("https://cninfo.com.cn.evil.example/a") == 4
    assert tier("https://example.com", "structured_market_data") == 3
    with pytest.raises(ValueError, match="UNSUPPORTED_HARD"):
        normalize(observation("CUSTOMER_AND_ORDER", source_tier=4, body_evidence="rumor", facts={"event_type": "ORDER_CONFIRMED"}))


def test_compact_limits_and_links(root):
    raw = [normalize(observation(entity=str(i))) for i in range(30)]
    packet = RadarPipeline(root, now=lambda: CUTOFF).build(DAY, "MORNING", rows=raw)
    small = compact(packet)
    assert len(small["commodity_observations"]) == 20
    assert small["compact_metadata"]["available_counts"]["commodity_observations"] == 30
    validate(small)


def test_daily_review_optional_radar_does_not_change_existing_analysis(root):
    from tests.unit.test_review_context_builder import _inputs, _builder
    _inputs(root)
    day = date(2026, 9, 4)
    before = _builder(root).build(day)["packet"]
    morning = datetime(2026, 9, 4, 8, tzinfo=SHANGHAI)
    pipeline = RadarPipeline(root, now=lambda: morning)
    raw = normalize(observation(source_date="2026-09-03", event_date="2026-09-03", published_at="2026-09-03T18:00:00+08:00", first_seen_at="2026-09-03T19:00:00+08:00"))
    pipeline.write(pipeline.build(day, "MORNING", rows=[raw]))
    result = _builder(root).build(day)
    assert result["packet"]["opportunity_radar"]["score_effect"] == 0
    assert result["compact"]["opportunity_radar"]["status"] == "AVAILABLE"
    result["packet"].pop("opportunity_radar")
    assert before == result["packet"]


def test_snapshot_tampering_is_detected(root):
    pipeline = RadarPipeline(root, now=lambda: CUTOFF)
    path, _, _ = pipeline.write(pipeline.build(DAY, "MORNING", rows=[]))
    packet = json.loads(path.read_text(encoding="utf-8"))
    packet["market_context"]["status"] = "TAMPERED"
    path.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(ValueError, match="HASH"):
        read_context(root, DAY)


def test_invalid_and_future_timestamps_are_not_admitted():
    assert not visible(normalize(observation(published_at="invalid")), CUTOFF)
    assert not visible(normalize(observation(event_date="2026-09-11")), CUTOFF)


def test_episode_first_seen_survives_next_snapshot(root):
    first = normalize(observation(source_date="2026-09-08", value=100))
    second = normalize(observation(value=110))
    morning = RadarPipeline(root, now=lambda: CUTOFF)
    morning.write(morning.build(DAY, "MORNING", rows=[first, second]))
    third = normalize(observation(source_date="2026-09-10", event_date="2026-09-10", value=120,
                                  published_at="2026-09-10T15:00:00+08:00", first_seen_at="2026-09-10T16:00:00+08:00"))
    evening = RadarPipeline(root, now=lambda: datetime(2026, 9, 10, 18, tzinfo=SHANGHAI))
    packet = evening.build(DAY, "EOD", rows=[first, second, third])
    assert packet["positive_change_candidates"][0]["signal_first_seen_date"] == "2026-09-09"


def test_already_reacted_market_never_gets_positive_lead_time():
    days = [str(date(2026, 8, 1)+timedelta(days=i)) for i in range(30)]
    signal = {"entity": "x", "signal_type": "COMMODITY_PRICE", "signal_first_seen_date": days[3]}
    market = [{"entity": "x", "date": d, "as_of_valid": True, "relative_return_5d": 4, "breadth": .7, "amount_ratio_20d": 1.4} for d in days]
    record = measure([signal], market, days, days[-1])["records"][0]
    assert record["lead_trading_days"] == -3
    assert record["pre_existing_market_confirmation"] is True


def test_optional_corrupt_radar_does_not_block_daily_review(root):
    from src.opportunity_radar.pipeline import read_only_summary
    path = root / "data/opportunity_radar/2026-09-10_morning.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"meta": {}}', encoding="utf-8")
    assert read_only_summary(root, DAY)["status"] == "UNAVAILABLE"


def test_git_line_ending_transport_preserves_provenance():
    from src.opportunity_radar.storage import receipt_matches
    raw = b'{\r\n  "fixture": 1\r\n}\r\n'
    assert receipt_matches(raw.replace(b'\r\n', b'\n'), hashlib.sha256(raw).hexdigest())
    assert not receipt_matches(raw.replace(b'1', b'2'), hashlib.sha256(raw).hexdigest())


def test_source_replacement_cannot_erase_old_evidence(root):
    store = ObservationStore(root)
    store.append([observation()])
    pipeline = RadarPipeline(root, now=lambda: CUTOFF)
    pipeline.write(pipeline.build(DAY, "MORNING"))
    (root / "fixture.json").write_text('{"changed": true}', encoding="utf-8")
    assert read_context(root, DAY)["status"] == "AVAILABLE"


def test_morning_and_eod_collection_use_distinct_closed_dates():
    from tools.build_opportunity_radar import collection_end
    assert collection_end(DAY, "MORNING", CUTOFF) == date(2026, 9, 9)
    with pytest.raises(ValueError, match="NOT_CLOSED"):
        collection_end(DAY, "EOD", CUTOFF)
    evening = datetime(2026, 9, 10, 18, tzinfo=SHANGHAI)
    assert collection_end(DAY, "EOD", evening) == DAY


def test_historical_eod_cannot_be_labeled_live(root):
    with pytest.raises(ValueError, match="REQUIRES_REPLAY"):
        RadarPipeline(root, now=lambda: CUTOFF).build(date(2026, 9, 9), "EOD", rows=[])


def test_bad_feedback_record_is_rejected_by_schema(root):
    from jsonschema import ValidationError
    packet = RadarPipeline(root, now=lambda: CUTOFF).build(DAY, "MORNING", rows=[])
    packet["lead_time_statistics"]["records"] = [1]
    with pytest.raises(ValidationError):
        validate(packet)
