from types import SimpleNamespace

from src.core.sentiment import analyze_sentiment


def test_sentiment_outputs_stage_temperature_and_reasons():
    snapshot = SimpleNamespace(
        advancers=3200,
        decliners=1800,
        limit_up_count=88,
        limit_down_count=5,
        failed_limit_count=12,
        max_board_height=6,
        index_pct_chg=0.6,
    )

    result = analyze_sentiment(snapshot)

    assert 0 <= result.temperature <= 100
    assert result.stage in {"冰点", "修复", "主升", "分歧", "退潮"}
    assert result.reasons
