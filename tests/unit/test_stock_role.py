from types import SimpleNamespace

from src.core.stock_role import classify_stock


def test_stock_role_requires_evidence():
    snapshot = SimpleNamespace(theme_memberships={"主题甲": ["600001.SH"]})
    stock = SimpleNamespace(ts_code="600001.SH", name="测试银行", theme="主题甲", board_height=2, amount=30)

    result = classify_stock(stock, snapshot)

    assert result.role in {"龙头", "容量中军", "低位补涨", "中位股", "孤立票", "风险票"}
    assert result.reasons
