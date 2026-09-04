def format_score(value, rating=None) -> str:
    if value is None:
        return "暂不评分"
    return f"{value} / {rating}" if rating else str(value)


def format_number(value, suffix="") -> str:
    if value is None:
        return "数据不足"
    return f"{value:,.2f}{suffix}" if isinstance(value, float) else f"{value:,}{suffix}"


def format_delta(value) -> str:
    if value is None:
        return "—"
    arrow = "↑" if value > 0 else "↓" if value < 0 else "→"
    return f"{value:+d} {arrow}"


def format_status(value: str) -> str:
    labels = {
        "new": "新增",
        "strengthened": "强化",
        "weakened": "弱化",
        "expanded": "扩散",
        "realized": "兑现",
        "invalidated": "证伪",
        "unchanged": "持平",
    }
    return labels.get(value, value)
