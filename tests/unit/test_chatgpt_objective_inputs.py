"""Objective handoff contract tests. All invented market data stays in tmp_path."""

import copy
import json
from datetime import date

import pytest
from jsonschema import Draft202012Validator, ValidationError

from src.formal_review.delivery import update_queue
from src.formal_review.objective_evidence import (
    evidence_nodes,
    factor_evidence,
    realization_facts,
    source_tier,
)
from src.formal_review.objective_inputs import SCHEMA_ROOT, build_inputs
from src.formal_review.objective_validation import metric_results
from tests.integration.test_first_formal_review_handoff import DAYS, formal, setup, write
from src.formal_review.persistence import import_record

DAY = date(2026, 9, 9)
FORBIDDEN = {
    "rank",
    "theme_rank",
    "rating",
    "true_mainline",
    "current_state",
    "previous_state",
    "lifecycle",
    "role",
    "total_score",
    "raw_score",
    "scores",
    "score_support",
    "causal_chain",
    "market_regime",
    "hit_rate",
    "result",
    "final_judgement",
}


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


@pytest.fixture
def root(tmp_path):
    setup(tmp_path)
    market = dict(
        meta=dict(trade_date=str(DAY)),
        data_quality=dict(status="PARTIAL"),
        market_overview=dict(
            total_market_turnover=300,
            rise_count=4,
            fall_count=2,
            flat_count=0,
            limit_up_count=3,
            failed_limit_count=1,
            highest_board=2,
        ),
        limit_up_down=dict(
            second_board_count=1, third_board_count=0, fourth_board_count=0, five_plus_board_count=0
        ),
        themes=[dict(theme_name="FIXTURE_THEME", amount=120, rise_count=2, change_pct=3)],
        stocks=[
            dict(stock_code="000001", stock_name="FIXTURE", themes=["FIXTURE_THEME"], amount=120)
        ],
        announcements=dict(records=[]),
    )
    write(tmp_path / f"data/market_packets/{DAY}.json", market)
    write(
        tmp_path / "data/market_packets/2026-09-08.json",
        dict(meta=dict(trade_date="2026-09-08"), market_overview=dict(total_market_turnover=100)),
    )
    for folder in (
        "review_intelligence",
        "capital_preference",
        "review_context",
        "formal_review_support",
    ):
        write(tmp_path / f"data/{folder}/{DAY}.json", dict(meta=dict(trade_date=str(DAY))))
    return tmp_path


@pytest.fixture
def packet(root):
    return build_inputs(root, DAY, DAYS)


def test_objective_input_no_final_judgement(packet):
    assert packet["meta"]["data_role"] == "OBJECTIVE_RESEARCH_INPUT"
    assert packet["meta"]["final_judgement_owner"] == "chatgpt"
    assert not keys(packet) & FORBIDDEN
    assert packet["market_snapshot"]["amount_change_vs_previous"] == 200
    assert packet["market_snapshot"]["limit_down_count"] is None


@pytest.mark.parametrize(
    "section,field",
    [
        ("theme_candidates", "rank"),
        ("theme_candidates", "rating"),
        ("lifecycle_vectors", "current_state"),
        ("stock_role_candidates", "role"),
        ("six_dimension_inputs", "total_score"),
        ("theme_candidates", "causal_chain"),
    ],
    ids=[
        "no_mainline_final_rank",
        "no_final_judgement",
        "no_final_lifecycle",
        "no_final_role_classification",
        "no_final_six_dimension_score",
        "no_causal_overreach",
    ],
)
def test_schema_rejects_final_fields(packet, section, field):
    invalid = copy.deepcopy(packet)
    invalid[section][0][field] = "UNAUTHORIZED"
    schema = json.loads(
        (SCHEMA_ROOT / "chatgpt_review_inputs.schema.json").read_text(encoding="utf-8")
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(invalid)


def test_factor41_evidence_only(packet):
    rows = packet["factor41_evidence"]
    assert [r["factor_id"] for r in rows] == list(range(1, 42))
    assert all(r["evidence_status"] == "DATA_UNAVAILABLE" for r in rows)
    assert not keys(rows) & FORBIDDEN


def announcement(**kw):
    return dict(
        stock_code="000001",
        published_at="2026-09-09T12:00:00+08:00",
        category="order",
        url="https://static.cninfo.com.cn/test.pdf",
        source_type="official",
        is_official=True,
        source="cninfo",
        contract_amount=1000,
        **kw,
    )


def test_source_tier():
    official = announcement()
    assert source_tier(official) == 1
    for changed in (
        dict(url="https://social.example/test"),
        dict(url="https://cninfo.com.cn.evil.example/test"),
    ):
        row = official | changed
        assert source_tier(row) == 4
        nodes = evidence_nodes(dict(announcements=dict(records=[row])), DAY, [])
        assert realization_facts(nodes)[0]["fact_level"] == "UNKNOWN"
    assert (
        source_tier(dict(source_type="reputable_media", original_source_url="https://gov.cn/x"))
        == 2
    )
    assert source_tier(dict(source_type="broker")) == 3


def test_title_or_clarification_does_not_confirm_orders():
    for change in (
        dict(contract_amount=None),
        dict(clarification_flags=["NO_ORDER"]),
        dict(uncertainty_flag=True),
    ):
        nodes = evidence_nodes(dict(announcements=dict(records=[announcement() | change])), DAY, [])
        assert realization_facts(nodes)[0]["fact_level"] == "UNKNOWN"
    nodes = evidence_nodes(
        dict(announcements=dict(records=[announcement(), announcement()])), DAY, []
    )
    assert len(nodes) == 1
    assert realization_facts(nodes)[0]["fact_level"] == "ORDER_CONFIRMED"
    assert factor_evidence(nodes)[18]["evidence_status"] == "PARTIAL_EVIDENCE"


def test_previous_validation_metric_only(root):
    import_record(root, formal(), DAYS)
    packet = build_inputs(root, DAY, DAYS)
    results = packet["previous_review_actual_results"]
    assert results["source"]["data_date"] == "2026-09-08"
    assert len(results["records"]) == 12
    evaluated = [r for r in results["records"] if r["metric_status"] == "EVALUATED"]
    assert [r["condition_met"] for r in evaluated] == [True, False]
    assert all(r["condition_type"] == "validation_point" for r in evaluated)
    assert not keys(results) & FORBIDDEN


def test_condition_predicates_are_independent():
    review = formal()
    check = review["main_themes"][0]["next_day_validation"][0]
    check["predicates"] = {
        "weakening_condition": dict(field="amount", operator="lt", threshold=100)
    }
    rows = metric_results(
        review,
        dict(meta=dict(trade_date=str(DAY)), themes=[dict(theme_name="FIXTURE_THEME", amount=120)]),
    )
    assert rows[0]["condition_met"] is True and rows[2]["condition_met"] is False


def test_compact_input(root, packet):
    queue = update_queue(root, str(DAY))
    assert queue["chatgpt_review_input_path"] == f"data/chatgpt_review_inputs/{DAY}.json"
    assert queue["chatgpt_review_input_compact_path"] == f"data/chatgpt_review_inputs/{DAY}_compact.json"
    compact = json.loads(
        (root / f"data/chatgpt_review_inputs/{DAY}_compact.json").read_text(encoding="utf-8")
    )
    assert len(compact["theme_candidates"]) <= 10
    assert len(compact["stock_role_candidates"]) <= 20
    assert len(compact["factor41_evidence"]) == 41
    assert not keys(compact) & FORBIDDEN
    assert "previous_review_actual_results" in compact and "data_gaps" in compact
    assert compact["meta"]["schema_version"] == "chatgpt_review_inputs_compact.1"


def test_no_future_leakage(root):
    path = root / f"data/market_packets/{DAY}.json"
    market = json.loads(path.read_text(encoding="utf-8"))
    market["announcements"]["records"] = [
        announcement() | dict(published_at="2026-09-09T18:00:00Z")
    ]
    market["themes"].append(dict(theme_name="FUTURE", data_date="2026-09-10", amount=999))
    market["themes"].append(dict(theme_name="CURRENT_ONLY", freshness="current_only", amount=888))
    write(path, market)
    output = build_inputs(root, DAY, DAYS)
    assert output["theme_evidence"] == []
    assert [r["theme_name"] for r in output["theme_candidates"]] == ["FIXTURE_THEME"]
    assert any(g["reason"] == "AS_OF_EXCLUDED" for g in output["data_gaps"])
    # A tomorrow file must not change today's output or its source hashes.
    write(
        root / "data/review_intelligence/2026-09-10.json",
        dict(meta=dict(trade_date="2026-09-10"), cycle_candidates=["FUTURE"]),
    )
    assert output == build_inputs(root, DAY, DAYS)


def test_exact_previous_trade_day(root):
    older = formal() | dict(date="2026-09-07", previous_trade_date="2026-09-04")
    import_record(root, older, DAYS)
    result = build_inputs(root, DAY, DAYS)["previous_review_actual_results"]
    assert result["status"] == "PREVIOUS_FORMAL_REVIEW_UNAVAILABLE"
    assert result["source"]["expected_date"] == "2026-09-08"
    assert result["records"] == []


def test_queue_readiness_survives_only_git_newline_conversion(root):
    import_record(root, formal(), DAYS)
    path = root / "data/formal_reviews/2026-09-08.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert update_queue(root, "2026-09-08")["status"] == "FORMAL_REVIEW_READY"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["uncertainties"] = ["ALTERED"]
    write(path, changed)
    assert update_queue(root, "2026-09-08")["status"] == "WAITING_FOR_CHATGPT_REVIEW"


def test_missing_input_fails_without_overwriting(root, packet):
    output = root / f"data/chatgpt_review_inputs/{DAY}.json"
    before = output.read_bytes()
    (root / f"data/market_packets/{DAY}.json").unlink()
    with pytest.raises(ValueError, match="same-date"):
        build_inputs(root, DAY, DAYS)
    assert output.read_bytes() == before


def test_future_dependency_rejects_derived_features(root):
    write(
        root / f"data/review_intelligence/{DAY}.json",
        {
            "meta": {"trade_date": str(DAY)},
            "source_manifest": {"future": {"data_date": "2026-09-10"}},
            "theme_features": [{"theme_name": "TAINTED", "change_pct": 99}],
        },
    )
    result = build_inputs(root, DAY, DAYS)
    assert result["source_manifest"]["review_intelligence"]["status"] == "AS_OF_REJECTED"
    assert all(t["theme_name"] != "TAINTED" for t in result["theme_candidates"])


def test_nonfinite_archive_values_remain_missing(root):
    path = root / f"data/market_packets/{DAY}.json"
    market = json.loads(path.read_text(encoding="utf-8"))
    market["market_overview"]["rise_count"] = float("nan")
    write(path, market)
    packet = build_inputs(root, DAY, DAYS)
    assert packet["market_snapshot"]["rise_count"] is None
    assert any(g["reason"] == "NONFINITE_SOURCE_VALUES_AS_NULL" for g in packet["data_gaps"])
    json.dumps(packet, allow_nan=False)


def test_compact_references_resolve_and_anomalies_are_numeric(root):
    path = root / f"data/market_packets/{DAY}.json"
    market = json.loads(path.read_text(encoding="utf-8"))
    market["stocks"][0]["turnover_rate"] = 40
    market["announcements"]["records"] = [announcement()]
    market["cross_market_facts"] = [
        dict(
            market="HK",
            instrument="FIXTURE",
            date="2026-09-09T16:00:00+08:00",
            value=1.5,
            source="fixture",
        )
    ]
    write(path, market)
    packet = build_inputs(root, DAY, DAYS)
    assert packet["abnormal_data_candidates"][0]["metric_a"] == 40
    assert packet["cross_market_facts"][0]["value"] == 1.5
    compact = json.loads(
        (root / f"data/chatgpt_review_inputs/{DAY}_compact.json").read_text(encoding="utf-8")
    )
    ids = {n["evidence_id"] for n in compact["theme_evidence"]}
    assert all(set(f["evidence"]) <= ids for f in compact["factor41_evidence"])
