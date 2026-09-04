import pandas as pd
import streamlit as st

from src.queries.statistics_queries import validation_results
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import TomorrowCheck, TradingDay
from src.ui.layout import setup_page


setup_page("验证中心")
st.title("验证中心")
engine = create_db_engine()
create_schema(engine)

with session_factory(engine)() as session:
    pending = (
        session.query(TomorrowCheck, TradingDay.trade_date)
        .join(TradingDay, TomorrowCheck.proposed_day_id == TradingDay.id)
        .order_by(TradingDay.trade_date.desc(), TomorrowCheck.id.desc())
        .all()
    )
    st.subheader("tomorrow_check 状态")
    if pending:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "提出日期": trade_date,
                        "对象": check.entity_key,
                        "类型": check.check_type,
                        "描述": check.description,
                        "状态": check.status,
                        "结果": check.result,
                    }
                    for check, trade_date in pending
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("暂无 tomorrow_check")

    st.subheader("验证结果入库记录")
    rows = validation_results(session)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("暂无 validation_result 记录")
