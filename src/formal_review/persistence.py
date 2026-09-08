"""Single canonical store for ChatGPT formal records and inbox imports."""
import hashlib
import json
from datetime import date
from pathlib import Path

from src.market_packet.trading_calendar import load_trading_calendar


def previous_day(root, target, calendar=None):
    days = calendar if calendar is not None else load_trading_calendar(target, cache_root=root / "data/reference")
    earlier = sorted(row.cal_date for row in days if row.is_open and row.cal_date < target)
    if not earlier:
        raise ValueError("previous trading day unavailable")
    return earlier[-1]


def load_previous_formal(root, target, calendar=None):
    expected = previous_day(root, target, calendar)
    path = root / "data/formal_reviews" / f"{expected}.json"
    manifest = {"status": "PREVIOUS_FORMAL_REVIEW_UNAVAILABLE", "expected_date": str(expected), "data_date": None, "path": None, "sha256": None}
    if not path.exists():
        return {}, manifest
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_record(root, payload, calendar)
    if payload["date"] != str(expected):
        raise ValueError("formal review exact previous-date mismatch")
    return payload, manifest | {"status": "AVAILABLE", "data_date": str(expected), "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_record(root, payload, calendar=None):
    from src.formal_review.support import validate_formal_review_record
    validate_formal_review_record(payload, schema_root=root)
    target = date.fromisoformat(payload["date"])
    days = calendar if calendar is not None else load_trading_calendar(target, cache_root=root / "data/reference")
    if not any(row.cal_date == target and row.is_open for row in days):
        raise ValueError("formal review date is not an exchange trading day")
    if payload.get("final_judgement_owner") != "chatgpt":
        raise ValueError("formal review owner must be chatgpt")
    expected = str(previous_day(root, target, days))
    if payload.get("previous_trade_date") != expected:
        raise ValueError(f"previous_trade_date must be {expected}")
    validation = payload.get("previous_day_validation") or {}
    if not (root / "data/formal_reviews" / f"{expected}.json").exists():
        if validation.get("records") or validation.get("hit_rate") is not None or validation.get("weighted_hit_rate") is not None:
            raise ValueError("formal hit rate requires the exact previous formal review")
    if any(row.get("hypothesis_kind") != "FORMAL_REVIEW_HYPOTHESIS" for row in validation.get("records", [])):
        raise ValueError("non-formal hypothesis cannot enter formal hit rate")


def import_record(root, payload, calendar=None):
    validate_record(root, payload, calendar)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    folder = root / "data/formal_reviews"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{payload['date']}.json"
    if target.exists():
        if json.loads(target.read_text(encoding="utf-8")) != payload:
            raise ValueError("immutable formal review already exists with different content")
        status = "UNCHANGED"
    else:
        with target.open("xb") as stream:
            stream.write(raw)
        status = "IMPORTED"
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {"status": status, "path": str(target), "sha256": digest, "date": payload["date"]}


def import_inbox(root, calendar=None):
    results = []
    for path in sorted((root / "data/formal_review_inbox").glob("*.json")):
        try:
            result = import_record(root, json.loads(path.read_text(encoding="utf-8")), calendar)
        except (ValueError, OSError, KeyError) as exc:
            result = {"status": "REJECTED", "error": type(exc).__name__}
        except Exception as exc:
            result = {"status": "REJECTED", "error": type(exc).__name__}
        results.append({"inbox_path": str(path), **result})
    return results
