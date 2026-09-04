from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ThemeCycleResult:
    name: str
    strength: int
    stage: str
    duration_days: int
    members: list[str]
    reasons: list[str]


def rank_themes(snapshot: Any) -> list[ThemeCycleResult]:
    memberships = getattr(snapshot, "theme_memberships", {}) or {}
    results = []
    for name, members in memberships.items():
        member_list = list(members)
        strength = min(100, 50 + len(member_list) * 10)
        stage = "主升期" if strength >= 80 else "发酵期"
        results.append(
            ThemeCycleResult(
                name=name,
                strength=strength,
                stage=stage,
                duration_days=max(1, int(getattr(snapshot, "theme_duration_days", {}).get(name, 1))),
                members=member_list,
                reasons=[f"{name} 有 {len(member_list)} 个观测成员"],
            )
        )
    return sorted(results, key=lambda item: -item.strength)
