from typing import Any

from src.config.runtime import DataPipelineConfig
from src.domain.market_data import GateCheck, GateDecision, GateStatus


class QualityGate:
    def __init__(self, config: DataPipelineConfig):
        self.config = config

    def evaluate(self, snapshot: Any, report_mode: str = "close") -> GateDecision:
        thresholds = self.config.thresholds
        checks = (
            _bool_check(
                "trading_day",
                _value(snapshot, "is_trading_day"),
                True,
                "目标日期必须是已确认交易日",
            ),
            _bool_check(
                "trade_date_consistency",
                _value(snapshot, "trade_date_consistent"),
                True,
                "核心数据交易日期必须一致",
            ),
            _min_check(
                "security_status_explained",
                _value(snapshot, "security_status_explained"),
                thresholds.security_status_explained,
                "上市证券状态可解释率不足",
            ),
            _min_check(
                "daily_quote_required_fields",
                _value(snapshot, "daily_required_coverage"),
                thresholds.daily_quote_required_fields,
                "个股日行情关键字段完整率不足",
            ),
            _min_check(
                "major_index_coverage",
                _value(snapshot, "major_index_coverage"),
                thresholds.major_index_coverage,
                "主要指数行情覆盖率不足",
            ),
            _min_check(
                "limit_candidate_coverage",
                _value(snapshot, "limit_candidate_coverage"),
                thresholds.limit_candidate_coverage,
                "涨跌停候选覆盖率不足",
            ),
            _supplemental_diff_check(
                _value(snapshot, "supplemental_abs_diff"),
                _value(snapshot, "supplemental_ratio_diff"),
                thresholds.supplemental_abs_diff,
                thresholds.supplemental_ratio_diff,
            ),
            _max_check(
                "critical_conflicts",
                _value(snapshot, "critical_conflicts"),
                thresholds.critical_conflicts,
                "存在会改变核心结论的未解决冲突",
            ),
        )
        hard_passed = all(check.passed for check in checks)
        if not hard_passed:
            status = GateStatus.FAILED
        elif report_mode == "intraday":
            status = GateStatus.DRAFT_ONLY
        else:
            status = GateStatus.PASSED
        return GateDecision(
            status=status,
            rule_version=self.config.rule_version,
            checks=checks,
            confidence=_confidence(snapshot),
        )


def _value(snapshot: Any, name: str):
    return getattr(snapshot, name)


def _bool_check(name: str, actual: bool, threshold: bool, reason: str) -> GateCheck:
    return GateCheck(
        name=name,
        actual=actual,
        threshold=threshold,
        passed=actual is threshold,
        reason="通过" if actual is threshold else reason,
    )


def _min_check(name: str, actual: float, threshold: float, reason: str) -> GateCheck:
    return GateCheck(
        name=name,
        actual=actual,
        threshold=threshold,
        passed=actual >= threshold,
        reason="通过" if actual >= threshold else reason,
    )


def _max_check(name: str, actual: int, threshold: int, reason: str) -> GateCheck:
    return GateCheck(
        name=name,
        actual=actual,
        threshold=threshold,
        passed=actual <= threshold,
        reason="通过" if actual <= threshold else reason,
    )


def _supplemental_diff_check(
    actual_abs: int,
    actual_ratio: float,
    threshold_abs: int,
    threshold_ratio: float,
) -> GateCheck:
    passed = actual_abs <= threshold_abs or actual_ratio <= threshold_ratio
    return GateCheck(
        name="supplemental_diff",
        actual=f"{actual_abs}/{actual_ratio:.4f}",
        threshold=f"{threshold_abs}/{threshold_ratio:.4f}",
        passed=passed,
        reason="通过" if passed else "补充源结果与日行情重算结果差异过大",
    )


def _confidence(snapshot: Any) -> int:
    missing = list(getattr(snapshot, "missing_enhancements", []) or [])
    return max(0, 100 - len(missing) * 10)
