
def diff_theme(previous: dict | None, current: dict) -> dict:
    if not previous:
        return {"status": "new", "delta_score": None, "delta_reason": "上一交易日不存在该主线"}
    prev_score = previous.get("total_score")
    curr_score = current.get("total_score")
    delta = None if prev_score is None or curr_score is None else curr_score - prev_score
    return {
        "status": current.get("change_status", "unchanged"),
        "delta_score": delta,
        "delta_reason": current.get("delta_reason", "")
    }
