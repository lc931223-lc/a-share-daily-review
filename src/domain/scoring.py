import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_scoring_config() -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / "scoring.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "base_logic",
        "realization",
        "expectation_gap",
        "persistence",
        "market_confirmation",
        "risk_penalty",
    }
    if set(config.get("dimensions", {})) != required:
        raise ValueError("config/scoring.json 的评分维度不完整或包含未知维度")
    return config


def validate_dimensions(values: dict[str, int]) -> None:
    dimensions = load_scoring_config()["dimensions"]
    for name, bounds in dimensions.items():
        value = values[name]
        if not bounds["min"] <= value <= bounds["max"]:
            raise ValueError(
                f"{name}={value} 超出允许范围 {bounds['min']}..{bounds['max']}"
            )


def calculate_total(values: dict[str, int]) -> int:
    validate_dimensions(values)
    return sum(values.values())


def rating_for_score(score: int) -> str:
    for item in load_scoring_config()["ratings"]:
        if item["min"] <= score <= item["max"]:
            return item["rating"]
    raise ValueError(f"total_score={score} 不在评分配置范围内")
