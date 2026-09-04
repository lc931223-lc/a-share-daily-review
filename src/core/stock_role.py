from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StockRoleResult:
    ts_code: str
    name: str
    theme: str
    role: str
    reasons: list[str]


def classify_stock(stock: Any, snapshot: Any) -> StockRoleResult:
    ts_code = getattr(stock, "ts_code", getattr(stock, "code", ""))
    name = getattr(stock, "name", ts_code)
    theme = getattr(stock, "theme", "")
    board_height = int(getattr(stock, "board_height", 0) or 0)
    amount = float(getattr(stock, "amount", 0) or 0)
    observed_members = set((getattr(snapshot, "theme_memberships", {}) or {}).get(theme, []))

    if ts_code not in observed_members:
        role = "孤立票"
        reasons = [f"{ts_code} 未出现在题材 {theme} 的观测成员中"]
    elif board_height >= 3:
        role = "龙头"
        reasons = [f"连板高度 {board_height} 在题材内具备辨识度"]
    elif amount >= 25:
        role = "容量中军"
        reasons = [f"成交额 {amount} 亿元，承担题材容量"]
    elif board_height == 1:
        role = "低位补涨"
        reasons = ["低位首板，属于补涨候选"]
    elif board_height == 2:
        role = "中位股"
        reasons = ["二板位置需要观察晋级和反馈"]
    else:
        role = "风险票"
        reasons = ["缺少连板和容量证据"]
    return StockRoleResult(ts_code, name, theme, role, reasons)
