
STAGES = ["朦胧期", "发酵期", "验证期", "主升期", "扩散期", "兑现期"]

def validate_stage(stage: str) -> str:
    if stage not in STAGES:
        raise ValueError(f"invalid lifecycle stage: {stage}")
    return stage
