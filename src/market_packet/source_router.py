from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SourceRouter:
    def __init__(self, config_path: Path | None = None):
        path = config_path or PROJECT_ROOT / "config" / "market_packet_sources.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "source-routing.1":
            raise ValueError("unsupported source routing schema")
        self.datasets: dict[str, dict[str, Any]] = payload.get("datasets", {})

    def route(self, dataset: str) -> dict[str, Any]:
        try:
            return dict(self.datasets[dataset])
        except KeyError as exc:
            raise KeyError(f"no source route configured for {dataset}") from exc
