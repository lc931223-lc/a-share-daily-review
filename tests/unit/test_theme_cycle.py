from types import SimpleNamespace

from src.core.theme_cycle import rank_themes


def test_theme_cycle_uses_observed_memberships_only():
    snapshot = SimpleNamespace(theme_memberships={"主题甲": ["600001.SH"], "主题乙": ["000001.SZ"]})

    result = rank_themes(snapshot)

    assert [theme.name for theme in result] == ["主题甲", "主题乙"]
    assert "AI算力" not in {theme.name for theme in result}
