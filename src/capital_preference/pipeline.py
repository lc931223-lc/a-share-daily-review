from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator

from src.capital_preference.features import build_features
from src.inflection.history import DailyHistoryRepository
from src.storage.fact_store import FactStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CapitalPreferencePipeline:
    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        *,
        history_repository: DailyHistoryRepository | None = None,
    ):
        self.root = root
        self.fact_store = FactStore(root / "data" / "facts")
        self.history = history_repository or DailyHistoryRepository(
            root, fact_store=self.fact_store
        )
        self.database_path = root / "data" / "a_share_review.db"

    def run(
        self,
        target: date,
        *,
        daily_history: pd.DataFrame | None = None,
        stock_statistics: tuple[set[str], dict[str, dict[str, Any]]] | None = None,
        metadata: dict[str, dict[str, Any]] | None = None,
        persist_outputs: bool = True,
    ) -> dict[str, Any]:
        intelligence, intelligence_path = self._required("review_intelligence", target)
        market, market_path = self._optional("market_packets", target)
        inflection, inflection_path = self._optional("inflection", target)
        from src.auction.production import optional_review_input
        accepted_auction, _ = optional_review_input(self.root, target)
        auction, auction_path = accepted_auction.get("packet", {}), accepted_auction.get("path")
        official, official_path = self._optional("official_reviews", target)
        daily = (
            daily_history
            if daily_history is not None
            else self.history.query(target - timedelta(days=550), target)
        )
        daily = daily[daily["trade_date"].astype(str).str[:10] <= target.isoformat()].copy()
        if daily[daily["trade_date"].astype(str).str[:10] == target.isoformat()].empty:
            raise RuntimeError(f"daily facts unavailable for {target.isoformat()}")
        metadata = metadata if metadata is not None else self.history.stock_metadata(target)
        activity = self._theme_activity(target)
        themes, stocks = build_features(
            target=target.isoformat(),
            daily=daily,
            metadata=metadata,
            market=market,
            intelligence=intelligence,
            inflection=inflection,
            auction=auction,
            theme_activity=activity,
            stock_statistics=stock_statistics,
        )
        checks = _quality_checks(
            themes,
            stocks,
            {
                "market_packet": (market, market_path),
                "review_intelligence": (intelligence, intelligence_path),
                "inflection_scanner": (inflection, inflection_path),
                "auction_packet": (auction, auction_path),
                "official_review": (official, official_path),
            },
        )
        status = "PASS" if all(row["passed"] for row in checks) else "PARTIAL"
        packet = {
            "meta": {
                "schema_version": "capital_preference_packet.1",
                "trade_date": target.isoformat(),
                "as_of": f"{target.isoformat()}T15:05:00+08:00",
                "data_role": "OBJECTIVE_EVIDENCE",
                "final_judgement_owner": "chatgpt",
            },
            "source_manifest": {
                "market_packet": _manifest(market, market_path),
                "review_intelligence": _manifest(intelligence, intelligence_path),
                "inflection_scanner": _manifest(inflection, inflection_path),
                "auction_packet": _manifest(auction, auction_path),
                "official_review": _manifest(official, official_path),
                "fact_store": {
                    "status": "AVAILABLE",
                    "dataset": "stock_daily_ohlcv",
                    "through_date": target.isoformat(),
                },
            },
            "theme_capital_preference": themes,
            "stock_capital_preference": stocks,
            "data_quality": {
                "status": status,
                "checks": checks,
                "known_gaps": [
                    "Historical point-in-time concept membership is unavailable; industry membership and existing candidate links are used.",
                    "Market-cap coverage is limited to existing Market Packet stock rows.",
                    "Historical news count and institution coverage are unavailable and remain null.",
                    "Dedicated cycle fundamental data is unavailable and remains null.",
                    "Raw unadjusted daily prices are used because adjustment factors are unavailable.",
                ],
            },
        }
        compact = _compact(packet)
        Draft202012Validator(_schema(self.root, "capital_preference_packet.schema.json")).validate(
            packet
        )
        Draft202012Validator(_schema(self.root, "capital_preference_compact.schema.json")).validate(
            compact
        )
        full_path = compact_path = None
        if persist_outputs:
            self._persist(target, themes, stocks)
            output = self.root / "data" / "capital_preference"
            output.mkdir(parents=True, exist_ok=True)
            full_path = output / f"{target.isoformat()}.json"
            compact_path = output / f"{target.isoformat()}_compact.json"
            full_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
            compact_path.write_text(
                json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return {
            "packet": packet,
            "compact": compact,
            "paths": {
                "full": str(full_path) if full_path else None,
                "compact": str(compact_path) if compact_path else None,
            },
        }

    def _required(self, folder: str, target: date):
        path = self.root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            raise FileNotFoundError(f"required {folder} input is unavailable: {path}")
        payload = _read(path)
        _assert_date(payload, target, folder)
        return payload, path

    def _optional(self, folder: str, target: date):
        path = self.root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            return {}, None
        payload = _read(path)
        _assert_date(payload, target, folder)
        return payload, path

    def _theme_activity(self, target: date) -> dict[str, dict[str, Any]]:
        folder = self.root / "data" / "review_intelligence"
        paths = sorted(
            path for path in folder.glob("????-??-??.json") if path.stem <= target.isoformat()
        )[-20:]
        counts: dict[str, int] = {}
        for path in paths:
            for row in _read(path).get("theme_features") or []:
                name = str(row.get("theme_name") or "")
                if name and (
                    row.get("theme_amount") is not None
                    or row.get("theme_inflection_score") is not None
                ):
                    counts[name] = counts.get(name, 0) + 1
        return {
            name: {
                "active_days": count,
                "observation_days": len(paths),
                "active_ratio": count / len(paths) if paths else None,
            }
            for name, count in counts.items()
        }

    def _persist(self, target, themes, stocks):
        written = []
        for dataset, rows in (
            ("capital_preference_theme", themes),
            ("capital_preference_stock", stocks),
        ):
            partition = self.fact_store.write_dataset(dataset, target, rows)
            if partition:
                written.append(partition)
        self.fact_store._catalog(written, self.database_path)


def _compact(packet):
    themes = packet["theme_capital_preference"][:20]
    stocks = packet["stock_capital_preference"][:100]
    return {
        "meta": packet["meta"] | {"schema_version": "capital_preference_compact.1"},
        "source_manifest": packet["source_manifest"],
        "theme_capital_preference": [
            {
                key: row.get(key)
                for key in (
                    "theme",
                    "capital_preference_score",
                    "available_max_score",
                    "component_coverage",
                    "fundamental_fit",
                    "position_advantage",
                    "capital_capacity",
                    "crowding_advantage",
                    "style_match",
                    "consensus_proxy",
                    "capital_structure_score",
                    "candidate_only",
                )
            }
            for row in themes
        ],
        "stock_capital_preference": [
            {
                key: row.get(key)
                for key in (
                    "ts_code",
                    "stock_name",
                    "themes",
                    "stock_capital_preference_score",
                    "available_max_score",
                    "position",
                    "capacity",
                    "crowding",
                    "style_match",
                    "theme_role",
                    "leader_candidate",
                    "capacity_candidate",
                    "candidate_only",
                )
            }
            for row in stocks
        ],
        "why_capital_selected": [
            {"theme": row["theme"], "evidence": row["why_capital_selected"]} for row in themes
        ],
        "capacity_structure": [
            {"theme": row["theme"], **row["capacity_structure"]} for row in themes
        ],
        "crowding_status": [
            {
                "theme": row["theme"],
                "status": row["crowding_status"],
                "inputs": row["crowding_advantage"]["inputs"],
            }
            for row in themes
        ],
        "review_section_support": {
            "title": "资金青睐逻辑拆解",
            "fields": [
                "why_capital_selected",
                "fundamental_fit",
                "position_advantage",
                "capital_capacity",
                "crowding_advantage",
                "style_match",
                "consensus_proxy",
            ],
            "final_judgement_owner": "chatgpt",
        },
        "data_quality": packet["data_quality"],
    }


def _quality_checks(themes, stocks, sources):
    component_coverage = (
        sum(row.get("component_coverage") or 0 for row in themes) / len(themes) if themes else 0
    )
    return [
        {"name": "theme_nonempty", "actual": len(themes), "threshold": 1, "passed": bool(themes)},
        {"name": "stock_nonempty", "actual": len(stocks), "threshold": 1, "passed": bool(stocks)},
        {
            "name": "average_component_coverage",
            "actual": round(component_coverage, 4),
            "threshold": 0.95,
            "passed": component_coverage >= 0.95,
        },
        *[
            {
                "name": f"{name}_quality",
                "actual": _source_quality(name, payload, path),
                "threshold": "PASS",
                "passed": _source_quality(name, payload, path) == "PASS",
            }
            for name, (payload, path) in sources.items()
        ],
    ]


def _source_quality(name, payload, path):
    if path is None:
        return "UNAVAILABLE"
    if name == "official_review":
        commentary = " ".join(str(value) for value in payload.get("market_commentary") or [])
        return (
            "SIMULATED"
            if "模拟" in commentary or str(payload.get("data_kind")) in {"demo", "sample"}
            else "PASS"
        )
    return str((payload.get("data_quality") or {}).get("status") or "UNKNOWN")


def _manifest(payload, path):
    if path is None:
        return {"status": "UNAVAILABLE", "path": None, "sha256": None}
    return {
        "status": "AVAILABLE",
        "path": path.as_posix(),
        "sha256": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def _assert_date(payload, target, folder):
    actual = str(payload.get("date") or (payload.get("meta") or {}).get("trade_date") or "")[:10]
    if actual != target.isoformat():
        raise ValueError(f"{folder} date mismatch: expected {target.isoformat()}, got {actual}")


def _schema(root, name):
    return json.loads((root / "schemas" / name).read_text(encoding="utf-8"))


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))
