"""Offline 9/8 -> 9/9 handoff: only upstream market producers are fixtures."""

import hashlib
import io
import json
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator

from src.daily_close.orchestrator import ARTIFACTS, DailyCloseOrchestrator
from src.domain.constants import DRIVER_TYPES
from src.formal_review.persistence import import_record, load_previous_formal, validate_record
from src.market_packet.trading_calendar import TradingCalendarDay
from src.review_context.builder import ReviewContextBuilder
from src.storage.fact_store import FactStore
from tools import import_formal_review_record as cli

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 9, 9)
DAYS = [TradingCalendarDay(date(2026, 9, d), True) for d in (4, 7, 8, 9)]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def setup(root):
    shutil.copytree(ROOT / "schemas", root / "schemas")
    # External producer payloads are small fixtures; keep real contracts for all
    # handoff components, including formal import, context, support and manifest.
    for name in ("market_packet", "inflection", "review_intelligence", "capital_preference"):
        write(root / "schemas" / ARTIFACTS[name][1], {"type": "object"})
    write(
        root / "data/reference/trade_calendar_2026.json",
        {"rows": [{"cal_date": d.cal_date.strftime("%Y%m%d"), "is_open": 1} for d in DAYS]},
    )


def formal():
    payload = read(ROOT / "docs/templates/formal_review.3-2026-09-08.json")
    payload["uncertainties"] = ["INTEGRATION TEST ONLY"]
    component = {
        "raw_score": None,
        "available_score": 0,
        "subcomponents": [],
        "evidence": [],
        "reason": "test input unavailable",
    }
    scores = {
        k: dict(component)
        for k in (
            "base_logic",
            "realization",
            "expectation_gap",
            "continuity",
            "market_confirmation",
            "risk_deduction",
        )
    }
    scores.update(total_score=None, rating=None)
    checks = []
    for label, field, threshold in (
        ("formal amount", "amount", 100),
        ("formal breadth", "rise_count", 10),
        ("formal prose", None, None),
    ):
        check = {
            "validation_point": label,
            "strengthening_condition": label,
            "weakening_condition": "test weak",
            "falsification_condition": "test fail",
        }
        if field:
            check["predicate"] = {"field": field, "operator": "gte", "threshold": threshold}
        checks.append(check)
    payload["main_themes"] = [
        {
            "theme_name": "FIXTURE_THEME",
            "theme_rank": 1,
            "41_factors": [
                {
                    "factor_id": i,
                    "factor_name": n,
                    "status": "UNCONFIRMED",
                    "evidence": [],
                    "confidence": "NONE",
                }
                for i, n in DRIVER_TYPES.items()
            ],
            "base_logic_score": None,
            "realization_score": None,
            "expectation_gap_score": None,
            "continuity_score": None,
            "market_confirmation_score": None,
            "risk_deduction": None,
            "total_score": None,
            "rating": None,
            "scores": scores,
            "lifecycle": {
                "previous_state": None,
                "current_state": "VALIDATION",
                "transition_reason": "FIXTURE ONLY",
                "positive_evidence": [],
                "negative_evidence": [],
                "confidence": "LOW",
            },
            "previous_lifecycle": None,
            "core_stocks": [],
            "next_day_validation": checks,
            "uncertainties": ["FIXTURE ONLY"],
        }
    ]
    return payload


def upstream(root, name, day):
    folder = ARTIFACTS[name][0]
    payload = {"meta": {"trade_date": str(day)}, "data_quality": {"status": "PASS"}}
    if name == "market_packet":
        payload.update(
            themes=[{"theme_name": "FIXTURE_THEME", "amount": 120, "rise_count": 2}],
            industries=[],
            stocks=[],
            announcements={"records": []},
            market_overview={},
            limit_up_down={},
        )
        payload["data_quality"].update(
            checks=[{"item": "全市场日线", "status": "PASS"}], sources=[]
        )
    write(root / "data" / folder / f"{day}.json", payload)
    if name == "capital_preference":
        write(root / "data" / folder / f"{day}_compact.json", payload)


@pytest.mark.parametrize("entry", ["stdin", "inbox", "cli"])
def test_standard_import_paths_and_idempotency(tmp_path, monkeypatch, capsys, entry):
    setup(tmp_path)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    payload = formal()
    path = tmp_path / "data/formal_review_inbox/2026-09-08.json"
    write(path, payload)
    if entry == "stdin":
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        args = ["-"]
    else:
        args = ["--inbox"] if entry == "inbox" else [str(path)]
    assert cli.main(args) == 0
    capsys.readouterr()
    canonical = tmp_path / "data/formal_reviews/2026-09-08.json"
    digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
    assert read(tmp_path / "data/official_reviews/2026-09-08.json")["source_sha256"] == digest
    assert (
        read(tmp_path / "data/formal_review_queue/2026-09-08.json")["status"]
        == "FORMAL_REVIEW_READY"
    )
    assert import_record(tmp_path, payload, DAYS)["status"] == "UNCHANGED"
    assert not (tmp_path / "research_feedback/formal/2026-09-09.json").exists()


def test_import_to_next_day_pipeline_formal_only_feedback(tmp_path, monkeypatch):
    setup(tmp_path)
    # Synthetic history belongs only to this temporary FactStore, never production.
    facts = FactStore(tmp_path / "data/facts")
    for day in (date(2026, 9, 8), DAY):
        facts.write_dataset(
            "stock_daily_ohlcv",
            day,
            [
                {
                    "trade_date": str(day),
                    "ts_code": "FIXTURE.SZ",
                    "open": 10.0,
                    "close": 10.0,
                    "high": 10.0,
                    "low": 10.0,
                    "amount": 100.0,
                    "vol": 10.0,
                    "pct_chg": 0.0,
                    "source": "INTEGRATION_FIXTURE",
                }
            ],
        )
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    write(tmp_path / "data/formal_review_inbox/2026-09-08.json", formal())
    assert cli.main(["--inbox"]) == 0
    canonical = tmp_path / "data/formal_reviews/2026-09-08.json"
    digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
    write(
        tmp_path / "data/formal_review_support/2026-09-08.json",
        {
            "meta": {"trade_date": "2026-09-08"},
            "theme_support": [
                {
                    "theme_name": "FIXTURE_THEME",
                    "next_day_validation": [
                        {
                            "validation_point": "OBJECTIVE_SUPPORT_MUST_NOT_COUNT",
                            "predicate": {"field": "amount", "operator": "gte", "threshold": 0},
                        }
                    ],
                }
            ],
        },
    )
    runners = {
        name: (lambda day, n=name: upstream(tmp_path, n, day))
        for name in ("market_packet", "inflection", "review_intelligence", "capital_preference")
    }
    runners["review_context"] = lambda day: ReviewContextBuilder(
        tmp_path, calendar_loader=lambda _: DAYS
    ).build(day)
    pipeline = DailyCloseOrchestrator(
        tmp_path,
        now=lambda: datetime(2026, 9, 9, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        calendar_loader=lambda _: DAYS,
        runners=runners,
        max_retries=0,
    )
    result = pipeline.run_date(DAY)
    assert result["status"] in {"PASS", "PARTIAL"}, result.get("blockers")
    assert result["steps"]["feedback"]["status"] not in {"FAILED", "BLOCKED"}
    context = read(tmp_path / "data/review_context/2026-09-09.json")
    prior = context["source_manifest"]["prior_official_review"]
    assert prior["data_date"] == "2026-09-08" and prior["sha256"] == digest
    support = read(tmp_path / "data/formal_review_support/2026-09-09.json")
    assert all(not {"theme_rank", "score_support", "lifecycle"}.intersection(t) for t in support["theme_support"])
    objective_input = read(tmp_path / "data/chatgpt_review_inputs/2026-09-09.json")
    metric_validation = objective_input["previous_review_actual_results"]
    assert metric_validation["source"]["sha256"] == digest
    assert len(metric_validation["records"]) == 12
    assert [r["condition_met"] for r in metric_validation["records"] if r["metric_status"] == "EVALUATED"] == [True, False]
    assert all("result" not in r and "hypothesis_kind" not in r for r in metric_validation["records"])
    assert len(support["objective_support_hypotheses"]["records"]) == 1
    assert support["objective_support_hypotheses"]["formal_hit_rate_eligible"] is False
    feedback = read(tmp_path / "research_feedback/formal/2026-09-09.json")
    assert feedback == support["previous_day_validation"]
    assert feedback["source"]["sha256"] == digest
    assert feedback["prediction_count"] == 3 and feedback["not_evaluable_count"] == 1
    assert feedback["confirmed_count"] == 1 and feedback["failed_count"] == 1
    assert feedback["hit_rate"] == feedback["weighted_hit_rate"] == 0.5
    assert {r["hypothesis_kind"] for r in feedback["records"]} == {"FORMAL_REVIEW_HYPOTHESIS"}
    assert all("OBJECTIVE_SUPPORT_MUST_NOT_COUNT" != r["hypothesis"] for r in feedback["records"])
    objective = read(tmp_path / "data/feedback_records/2026-09-09/validation.json")
    assert objective["meta"]["hypothesis_kind"] == "OBJECTIVE_SUPPORT_HYPOTHESIS"
    assert objective["meta"]["formal_hit_rate_eligible"] is False
    before = canonical.read_bytes()
    pipeline.run_date(DAY)
    assert canonical.read_bytes() == before
    assert read(tmp_path / "research_feedback/formal/2026-09-09.json") == feedback
    def fail_delivery(*args, **kwargs):
        raise ValueError("FIXTURE_INPUT_SCHEMA_FAILURE")
    monkeypatch.setattr("src.formal_review.objective_inputs.build_inputs", fail_delivery)
    failed = pipeline.run_date(DAY)
    assert failed["status"] == "FAILED"
    receipt = read(tmp_path / "data/daily_runs/2026-09-09.json")
    assert receipt["failed_step"] == "chatgpt_review_inputs"
    assert any("FIXTURE_INPUT_SCHEMA_FAILURE" in row["error"] for row in receipt["blockers"])


def test_missing_exact_day_never_falls_back_to_older_formal(tmp_path):
    setup(tmp_path)
    older = formal() | {"date": "2026-09-07", "previous_trade_date": "2026-09-04"}
    import_record(tmp_path, older, DAYS)
    write(tmp_path / "data/formal_review_support/2026-09-08.json", formal())
    payload, manifest = load_previous_formal(tmp_path, DAY, DAYS)
    assert payload == {}
    assert manifest["status"] == "PREVIOUS_FORMAL_REVIEW_UNAVAILABLE"
    assert manifest["expected_date"] == "2026-09-08"


def test_judgement_free_template_validates_without_being_imported(tmp_path):
    setup(tmp_path)
    payload = read(ROOT / "docs/templates/formal_review.3-2026-09-08.json")
    validate_record(tmp_path, payload, DAYS)
    Draft202012Validator(read(ROOT / "schemas/formal_review_record.schema.json")).validate(payload)
    assert payload["main_themes"] == [] and payload["market_regime"] == "NOT_ASSESSED"
    assert not (tmp_path / "data/formal_reviews").exists()
