
from src.domain.constants import LifecycleStage


STAGES = [stage.value for stage in LifecycleStage]

def validate_stage(stage: str) -> str:
    if stage not in STAGES:
        raise ValueError(f"invalid lifecycle stage: {stage}")
    return stage
