from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from src.capital_preference.pipeline import CapitalPreferencePipeline
from src.feedback.forward import advance_feedback
from src.formal_review.support import build_formal_review_support
from src.inflection.pipeline import InflectionPipeline
from src.market_packet.packet_builder import build_market_packet, write_outputs
from src.market_packet.trading_calendar import TradingCalendarDay, load_trading_calendar
from src.review_context.builder import ReviewContextBuilder
from src.review_intelligence.pipeline import ReviewIntelligencePipeline

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHANGHAI = ZoneInfo("Asia/Shanghai")
CLOSE_READY = time(15, 15)
FINAL_STATUSES = {
    "PASS",
    "PARTIAL",
    "BLOCKED",
    "FAILED",
    "NON_TRADING_DAY",
    "MARKET_NOT_CLOSED",
}

ARTIFACTS = {
    "market_packet": ("market_packets", "market_packet.schema.json"),
    "inflection": ("inflection", "inflection_packet.schema.json"),
    "review_intelligence": ("review_intelligence", "review_intelligence_packet.schema.json"),
    "capital_preference": ("capital_preference", "capital_preference_packet.schema.json"),
    "review_context": ("review_context", "review_context_packet.schema.json"),
    "formal_review_support": ("formal_review_support", "formal_review_support.schema.json"),
}


class DailyCloseOrchestrator:
    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        *,
        now: Callable[[], datetime] | None = None,
        calendar_loader: Callable[[date], list[TradingCalendarDay]] | None = None,
        runners: dict[str, Callable[[date], Any]] | None = None,
        max_retries: int = 2,
    ):
        self.root = root
        self.now = now or (lambda: datetime.now(SHANGHAI))
        self.calendar_loader = calendar_loader or (
            lambda anchor: load_trading_calendar(
                anchor, cache_root=self.root / "data" / "reference"
            )
        )
        self.max_retries = max_retries
        self.runners = self._default_runners() | (runners or {})

    def run_date(self, target: date, *, force: bool = False) -> dict[str, Any]:
        started = self.now().astimezone(SHANGHAI)
        days = self.calendar_loader(target)
        is_trade_day = any(row.cal_date == target and row.is_open for row in days)
        market_closed = target < started.date() or (
            target == started.date() and started.time() >= CLOSE_READY
        )
        manifest = {
            "date": target.isoformat(),
            "run_id": f"daily-close:{target.isoformat()}",
            "is_trade_day": is_trade_day,
            "market_closed": market_closed,
            "pipeline_started_at": started.isoformat(),
            "pipeline_completed_at": None,
            "steps": {},
            "status": "BLOCKED",
            "blockers": [],
        }
        if not is_trade_day:
            manifest["status"] = "NON_TRADING_DAY"
            return self._finish(manifest)
        if not market_closed:
            manifest["status"] = "MARKET_NOT_CLOSED"
            return self._finish(manifest)

        for name in (
            "market_packet",
            "inflection",
            "review_intelligence",
            "capital_preference",
            "review_context",
            "formal_review_support",
        ):
            step = self._execute_step(name, target, force=force)
            manifest["steps"][name] = step
            if step["status"] in {"FAILED", "BLOCKED"}:
                manifest["blockers"].append(
                    {"step": name, "error": step.get("error"), "missing_upstream": self._missing_upstream(name, target)}
                )
                manifest["status"] = "BLOCKED" if name != "market_packet" else "FAILED"
                return self._finish(manifest)

        manifest["steps"]["auction"] = self._optional_artifact("auction_packets", target)
        feedback = self._execute_feedback(target)
        manifest["steps"]["feedback"] = feedback
        statuses = [
            row["status"]
            for name, row in manifest["steps"].items()
            if name != "auction" or row["status"] != "UNAVAILABLE"
        ]
        manifest["status"] = (
            "FAILED"
            if "FAILED" in statuses
            else "BLOCKED"
            if "BLOCKED" in statuses
            else "PARTIAL"
            if any(status in {"PARTIAL", "UNAVAILABLE", "WAITING"} for status in statuses)
            else "PASS"
        )
        return self._finish(manifest)

    def run_latest(self, *, backfill_missing: bool = False, force: bool = False) -> list[dict[str, Any]]:
        current = self.now().astimezone(SHANGHAI)
        days = self.calendar_loader(current.date())
        closed_days = sorted(
            row.cal_date
            for row in days
            if row.is_open
            and (row.cal_date < current.date() or (row.cal_date == current.date() and current.time() >= CLOSE_READY))
        )
        if not closed_days:
            raise RuntimeError("no completed A-share trading day is available")
        latest = closed_days[-1]
        if not backfill_missing:
            return [self.run_date(latest, force=force)]
        completed = {
            path.stem
            for path in (self.root / "data" / "review_context").glob("????-??-??.json")
        }
        missing = [day for day in closed_days if day.isoformat() not in completed]
        if completed:
            anchor = max(completed)
            missing = [day for day in missing if day.isoformat() > anchor]
        if not missing:
            return [self.run_date(latest, force=force)]
        results = []
        for day in missing:
            result = self.run_date(day, force=force)
            results.append(result)
            if result["status"] in {"BLOCKED", "FAILED"}:
                break
        return results

    def _execute_step(self, name: str, target: date, *, force: bool) -> dict[str, Any]:
        started = self.now().astimezone(SHANGHAI)
        if not force:
            existing = self._validate_artifact(name, target)
            if existing["valid"]:
                return self._step_record(
                    "PASS" if existing["quality"] == "PASS" else "PARTIAL",
                    existing["path"],
                    target,
                    existing["quality"],
                    started,
                    retry_count=0,
                    error=None,
                    reused=True,
                    sha256=existing["sha256"],
                )
        error = None
        for attempt in range(self.max_retries + 1):
            try:
                self.runners[name](target)
                artifact = self._validate_artifact(name, target)
                if not artifact["valid"]:
                    raise RuntimeError(artifact["error"] or "artifact validation failed")
                return self._step_record(
                    "PASS" if artifact["quality"] == "PASS" else "PARTIAL",
                    artifact["path"],
                    target,
                    artifact["quality"],
                    started,
                    retry_count=attempt,
                    error=None,
                    reused=False,
                    sha256=artifact["sha256"],
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:500]}"
        return self._step_record(
            "FAILED",
            None,
            target,
            None,
            started,
            retry_count=self.max_retries,
            error=error,
            reused=False,
            sha256=None,
        )

    def _execute_feedback(self, target: date) -> dict[str, Any]:
        started = self.now().astimezone(SHANGHAI)
        try:
            result = self.runners["feedback"](target)
            status = "WAITING" if result["still_waiting_count"] else "PASS"
            return self._step_record(
                status,
                None,
                target,
                status,
                started,
                retry_count=0,
                error=None,
                reused=False,
                sha256=None,
            ) | result
        except Exception as exc:
            return self._step_record(
                "FAILED",
                None,
                target,
                None,
                started,
                retry_count=0,
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
                reused=False,
                sha256=None,
            )

    def _validate_artifact(self, name: str, target: date) -> dict[str, Any]:
        folder, schema_name = ARTIFACTS[name]
        path = self.root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            return {"valid": False, "path": str(path), "error": "artifact missing", "quality": None, "sha256": None}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            source_date = _payload_date(payload)
            if source_date != target.isoformat():
                raise ValueError(f"stale artifact source_date={source_date}")
            if name == "market_packet":
                self._validate_market_packet_sources(payload, target)
            schema = json.loads((self.root / "schemas" / schema_name).read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(payload)
            if name == "review_context":
                self._validate_context_provenance(payload, target)
            quality = (payload.get("data_quality") or {}).get("status") or "PASS"
            return {
                "valid": True,
                "path": str(path),
                "error": None,
                "quality": quality,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        except Exception as exc:
            return {"valid": False, "path": str(path), "error": str(exc), "quality": None, "sha256": None}

    @staticmethod
    def _validate_context_provenance(payload: dict[str, Any], target: date) -> None:
        manifest = payload.get("source_manifest") or {}
        for name in ("market_packet", "review_intelligence", "inflection_scanner", "capital_preference"):
            actual = str((manifest.get(name) or {}).get("data_date") or "")[:10]
            if actual != target.isoformat():
                raise ValueError(f"review_context {name} provenance is not same-date: {actual}")
        auction = manifest.get("auction_packet") or {}
        if auction.get("status") == "AVAILABLE" and str(auction.get("data_date") or "")[:10] != target.isoformat():
            raise ValueError("review_context auction provenance is cross-date")

    @staticmethod
    def _validate_market_packet_sources(payload: dict[str, Any], target: date) -> None:
        checks = {
            row.get("item"): row for row in (payload.get("data_quality") or {}).get("checks") or []
        }
        daily = checks.get("全市场日线") or {}
        if daily.get("status") != "PASS":
            raise ValueError("full-market daily rows did not pass the production gate")
        for source in (payload.get("data_quality") or {}).get("sources") or []:
            value = str(source.get("data_date") or "")[:10]
            if value and value > target.isoformat():
                raise ValueError(
                    f"future-dated source detected: {source.get('dataset')}={value}"
                )

    def _optional_artifact(self, folder: str, target: date) -> dict[str, Any]:
        path = self.root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            return self._step_record("UNAVAILABLE", None, target, None, self.now(), 0, None, False, None)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _payload_date(payload) != target.isoformat():
            return self._step_record("FAILED", str(path), target, None, self.now(), 0, "cross-date artifact", True, None)
        return self._step_record(
            "PASS" if (payload.get("data_quality") or {}).get("status") == "PASS" else "PARTIAL",
            str(path),
            target,
            (payload.get("data_quality") or {}).get("status"),
            self.now(),
            0,
            None,
            True,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def _finish(self, manifest: dict[str, Any]) -> dict[str, Any]:
        if manifest["status"] not in FINAL_STATUSES:
            raise ValueError(f"invalid final status {manifest['status']}")
        manifest["readiness_checks"] = self._readiness_checks(manifest)
        secret_check = next(
            row for row in manifest["readiness_checks"] if row["name"] == "no_plaintext_secrets"
        )
        if not secret_check["passed"]:
            manifest["blockers"].append(
                {"step": "production_readiness", "error": secret_check["detail"]}
            )
            manifest["status"] = "FAILED"
        manifest["pipeline_completed_at"] = self.now().astimezone(SHANGHAI).isoformat()
        schema = json.loads(
            (self.root / "schemas" / "daily_run_manifest.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(manifest)
        folder = self.root / "data" / "daily_runs"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{manifest['date']}.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(path)
        return manifest

    def _readiness_checks(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        core = [
            row
            for name, row in manifest["steps"].items()
            if name in ARTIFACTS
        ]
        secret_files = self._plaintext_secret_files()
        market = next(
            (row for name, row in manifest["steps"].items() if name == "market_packet"),
            {},
        )
        daily_rows_passed = self._daily_rows_passed(market.get("artifact_path"))
        return [
            {
                "name": "real_trading_calendar",
                "passed": manifest["is_trade_day"],
                "detail": "target is present as open in the cached/fetched A-share calendar",
            },
            {
                "name": "market_close_gate",
                "passed": manifest["market_closed"],
                "detail": "target session is closed under Asia/Shanghai close policy",
            },
            {
                "name": "daily_rows_completeness",
                "passed": daily_rows_passed,
                "detail": "Market Packet full-market daily rows passed its hard gate",
            },
            {
                "name": "same_date_core_artifacts",
                "passed": all(row.get("source_date") == manifest["date"] for row in core),
                "detail": "all generated core artifacts must carry the requested trade date",
            },
            {
                "name": "schema_and_provenance_sha256",
                "passed": all(row.get("provenance_sha256") for row in core),
                "detail": "all available core artifacts passed schema validation and have a digest",
            },
            {
                "name": "idempotent_reuse_contract",
                "passed": all(row.get("provenance_sha256") for row in core),
                "detail": "validated artifacts are content-addressed and reusable on rerun",
            },
            {
                "name": "no_plaintext_secrets",
                "passed": not secret_files,
                "detail": "no probable plaintext secrets found"
                if not secret_files
                else "probable plaintext secret assignments found in: " + ", ".join(secret_files),
            },
        ]

    @staticmethod
    def _daily_rows_passed(artifact_path: str | None) -> bool:
        if not artifact_path:
            return False
        try:
            payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return any(
            row.get("item") == "全市场日线" and row.get("status") == "PASS"
            for row in (payload.get("data_quality") or {}).get("checks") or []
        )

    def _plaintext_secret_files(self) -> list[str]:
        pattern = re.compile(
            r"(?i)(?:token|api[_-]?key|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"
        )
        roots = [self.root / name for name in ("src", "tools", "config", ".github")]
        matches = []
        for folder in roots:
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {
                    ".py", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg"
                }:
                    continue
                try:
                    if pattern.search(path.read_text(encoding="utf-8")):
                        matches.append(path.relative_to(self.root).as_posix())
                except UnicodeDecodeError:
                    continue
        return sorted(matches)

    @staticmethod
    def _step_record(status, artifact_path, target, quality, started, retry_count, error, reused, sha256):
        completed = datetime.now(SHANGHAI)
        return {
            "status": status,
            "artifact_path": artifact_path,
            "source_date": target.isoformat() if artifact_path else None,
            "quality": quality,
            "started_at": started.astimezone(SHANGHAI).isoformat(),
            "completed_at": completed.isoformat(),
            "error": error,
            "retry_count": retry_count,
            "reused": reused,
            "provenance_sha256": sha256,
        }

    def _default_runners(self):
        return {
            "market_packet": lambda target: write_outputs(build_market_packet(target), self.root),
            "inflection": lambda target: InflectionPipeline(self.root).run(target),
            "review_intelligence": lambda target: ReviewIntelligencePipeline(self.root).run(target),
            "capital_preference": lambda target: CapitalPreferencePipeline(self.root).run(target),
            "review_context": lambda target: ReviewContextBuilder(self.root).build(target),
            "formal_review_support": lambda target: build_formal_review_support(self.root, target),
            "feedback": lambda target: advance_feedback(self.root, target),
        }

    def _missing_upstream(self, name: str, target: date) -> list[str]:
        dependencies = {
            "inflection": ["market_packet"],
            "review_intelligence": ["market_packet", "inflection"],
            "capital_preference": ["market_packet", "review_intelligence", "inflection"],
            "review_context": ["market_packet", "review_intelligence", "inflection", "capital_preference"],
            "formal_review_support": ["market_packet", "review_context"],
        }
        return [name for name in dependencies.get(name, []) if not self._validate_artifact(name, target)["valid"]]


def _payload_date(payload: dict[str, Any]) -> str:
    return str(
        (payload.get("meta") or {}).get("trade_date")
        or payload.get("trade_date")
        or payload.get("date")
        or ""
    )[:10]
