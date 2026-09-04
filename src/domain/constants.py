from enum import StrEnum


class DataKind(StrEnum):
    REAL = "real"


class LifecycleStage(StrEnum):
    EMERGING = "朦胧期"
    FERMENTING = "发酵期"
    VALIDATING = "验证期"
    MARKUP = "主升期"
    DIFFUSING = "扩散期"
    REALIZING = "兑现期"


class StockRole(StrEnum):
    LEADER = "龙头"
    CORE = "中军"
    CATCHUP = "补涨"
    FOLLOWER = "跟风"
    SENTIMENT = "情绪股"


class EvidenceLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class CheckStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    WEAKENED = "weakened"
    INVALIDATED = "invalidated"


CHANGE_STATUSES = (
    "new",
    "strengthened",
    "weakened",
    "expanded",
    "realized",
    "invalidated",
    "unchanged",
)

DRIVER_TYPES = {
    1: "0→1技术突破",
    2: "1→10渗透率提升",
    3: "国产替代/自主可控",
    4: "海外产业映射",
    5: "国家级产业政策",
    6: "财政刺激/补贴",
    7: "货币与流动性政策",
    8: "监管边际改善/行业松绑",
    9: "反内卷/供给侧改革",
    10: "国企改革/市值管理",
    11: "国际重大事件",
    12: "国内重大会议/重要文件",
    13: "行业大会/产品发布会",
    14: "突发供给事故",
    15: "需求型涨价",
    16: "供给收缩型涨价",
    17: "库存周期/补库",
    18: "成本下降+售价稳定",
    19: "大额订单",
    20: "订单超预期",
    21: "下游资本开支爆发",
    22: "排产/交期/稼动率",
    23: "业绩超预期",
    24: "亏损转盈利/困境反转",
    25: "利润率提升",
    26: "业绩加速",
    27: "并购重组",
    28: "资产注入/控制权变更",
    29: "股权激励",
    30: "回购/增持/高分红",
    31: "重大客户认证/新供应链",
    32: "行业出清",
    33: "估值修复",
    34: "增量资金",
    35: "指数纳入/被动配置",
    36: "筹码出清/突破",
    37: "龙头效应与补涨",
    38: "风格切换/高低切",
    39: "名称玄学",
    40: "生肖/谐音/数字/地名",
    41: "情绪抱团/妖股",
}
