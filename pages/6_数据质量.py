import json

import pandas as pd
import streamlit as st
from sqlalchemy import select

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import AnalysisSnapshot, QualityGateCheck, QualityGateRun, SourceBatch, SourceFallback
from src.ui.layout import choose_day, empty_state, setup_page


setup_page("数据质量")
st.title("数据质量")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    day = choose_day(session, "quality_day")
    if day is None:
        empty_state("暂无数据质量记录"); st.stop()
    snapshot = session.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.trade_date == day.trade_date, AnalysisSnapshot.status == "PASSED")
        .order_by(AnalysisSnapshot.id.desc())
    ).scalar()
    if snapshot is None:
        empty_state("该交易日暂无正式快照"); st.stop()
    snapshot_data = json.loads(snapshot.result_json) if snapshot.result_json else {}
    quality_detail = snapshot_data.get("data_quality_detail") or {}
    st.markdown(f'<span class="status-real">正式真实数据 · {snapshot.status}</span>', unsafe_allow_html=True)
    st.caption(f"规则版本 {snapshot.rule_version} · 置信度 {snapshot.confidence}%")

    if quality_detail:
        st.subheader("快照质量摘要")
        st.table(
            pd.DataFrame(
                [
                    {"项目": "来源策略", "说明": quality_detail.get("primary_source", "")},
                    {"项目": "状态", "说明": quality_detail.get("status", "")},
                    {"项目": "已补齐缺口", "说明": "；".join(quality_detail.get("resolved_gaps", [])) or "无"},
                    {"项目": "口径差异", "说明": "；".join(quality_detail.get("source_disagreements", [])) or "无"},
                    {"项目": "仍未纳入项", "说明": "；".join(quality_detail.get("known_gaps", [])) or "无"},
                ]
            )
        )
        sources = quality_detail.get("sources", [])
        if sources:
            st.subheader("交叉核验来源")
            st.table(pd.DataFrame({"来源": sources}))

    batches = session.execute(
        select(SourceBatch).where(SourceBatch.trade_date == snapshot.trade_date).order_by(SourceBatch.id)
    ).scalars().all()
    st.subheader("来源批次")
    if batches:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "来源": item.source_name,
                        "数据集": item.dataset,
                        "交易日": item.trade_date,
                        "抓取时间": item.fetched_at,
                        "记录数": item.record_count,
                        "状态": item.status,
                        "归档": item.archive_path,
                    }
                    for item in batches
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        empty_state("导入型快照暂无逐项来源批次，见上方快照质量摘要")

    st.subheader("门禁检查")
    gate = session.execute(
        select(QualityGateRun)
        .where(QualityGateRun.trade_date == snapshot.trade_date)
        .order_by(QualityGateRun.id.desc())
    ).scalar()
    if gate:
        checks = session.execute(
            select(QualityGateCheck).where(QualityGateCheck.gate_run_id == gate.id)
        ).scalars().all()
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "检查项": item.check_name,
                        "实际值": item.actual_value,
                        "阈值": item.threshold_value,
                        "结果": "通过" if item.passed else "失败",
                        "原因": item.reason,
                    }
                    for item in checks
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        empty_state("导入型快照暂无逐项门禁记录，使用快照完整度和已知缺口说明")

    st.subheader("降级来源")
    fallbacks = session.execute(
        select(SourceFallback).where(SourceFallback.trade_date == snapshot.trade_date)
    ).scalars().all()
    if fallbacks:
        st.markdown('<div class="quality-warning"><b>东方财富降级</b></div>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "主源": item.primary_source,
                        "降级源": item.fallback_source,
                        "数据集": item.dataset,
                        "使用原因": item.reason,
                        "字段": item.fields_json,
                        "交叉验证": item.cross_validation_status,
                    }
                    for item in fallbacks
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.success("无东方财富降级记录")
