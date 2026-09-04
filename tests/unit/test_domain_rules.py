import pytest

from src.core.score import ScoreInput, rating, total_score
from src.domain.constants import DRIVER_TYPES, LifecycleStage
from src.domain.scoring import load_scoring_config


def test_fixed_driver_catalog_is_complete_and_unique():
    assert list(DRIVER_TYPES) == list(range(1, 42))
    assert len(set(DRIVER_TYPES.values())) == 41
    assert DRIVER_TYPES[1] == "0→1技术突破"
    assert DRIVER_TYPES[41] == "情绪抱团/妖股"


def test_lifecycle_matches_scoring_config():
    assert [item.value for item in LifecycleStage] == load_scoring_config()["lifecycle"]


def test_total_score_and_rating_use_configured_rules():
    score = total_score(ScoreInput(38, 23, 8, 9, 9, -3))
    assert score == 84
    assert rating(score) == "S"


@pytest.mark.parametrize(
    "value",
    [
        ScoreInput(41, 20, 10, 8, 8, 0),
        ScoreInput(30, 26, 10, 8, 8, 0),
        ScoreInput(30, 20, 16, 8, 8, 0),
        ScoreInput(30, 20, 10, 11, 8, 0),
        ScoreInput(30, 20, 10, 8, 11, 0),
        ScoreInput(30, 20, 10, 8, 8, -21),
    ],
)
def test_out_of_range_scores_are_rejected(value):
    with pytest.raises(ValueError, match="超出允许范围"):
        total_score(value)
