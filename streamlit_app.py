from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.analytics import (
    build_cost_preview,
    build_module_summary,
    build_personal_preview,
    build_personnel_frame,
    build_retail_frame,
    build_order_preview,
    compute_kpis,
    current_month_key,
    display_module_summary,
    display_personnel_frame,
    display_preview_frame,
    display_retail_frame,
    empty_month,
    format_number,
    format_percent,
    format_wan,
    ym_to_label,
)
from app.charts import (
    build_module_cost_chart,
    build_personnel_scatter,
    build_retail_efficiency_chart,
    build_retail_orders_chart,
)
from app.importers import (
    merge_cost_import,
    merge_order_import,
    merge_personal_order_import,
    process_cost_data,
    process_order_data,
    process_personal_order_data,
    read_excel_rows,
)
from app.normalize import normalize_month_data
from app.repository import get_repository

st.set_page_config(page_title="江西战区人力成本分析看板", layout="wide")


def secret_or_default(key: str, default: str) -> str:
    try:
        value = st.secrets.get(key, default)
    except StreamlitSecretNotFoundError:
        value = default
    return str(value)


ZONE_NAME = secret_or_default("zone_name", "江西战区")
REPOSITORY = get_repository()


@st.cache_data(show_spinner=False)
def list_months_cached() -> list[str]:
    return REPOSITORY.list_months()


@st.cache_data(show_spinner=False)
def load_month_cached(ym: str) -> dict[str, Any] | None:
    return REPOSITORY.load_month(ym)


def refresh_month_cache(ym: str | None = None) -> None:
    list_months_cached.clear()
    if ym:
        load_month_cached.clear()


if "selected_month" not in st.session_state:
    months = list_months_cached()
    st.session_state.selected_month = months[0] if months else current_month_key()

if "month_data" not in st.session_state:
    data = load_month_cached(st.session_state.selected_month)
    st.session_state.month_data = normalize_month_data(data) or empty_month(ym_to_label(st.session_state.selected_month))

if "preview_cost" not in st.session_state:
    st.session_state.preview_cost = None
if "preview_order" not in st.session_state:
    st.session_state.preview_order = None
if "preview_personal" not in st.session_state:
    st.session_state.preview_personal = None
if "preview_messages" not in st.session_state:
    st.session_state.preview_messages = []


def load_selected_month(ym: str) -> None:
    data = load_month_cached(ym)
    st.session_state.selected_month = ym
    st.session_state.month_data = normalize_month_data(data) or empty_month(ym_to_label(ym))
    st.session_state.preview_cost = None
    st.session_state.preview_order = None
    st.session_state.preview_personal = None
    st.session_state.preview_messages = []


with st.sidebar:
    st.title(f"{ZONE_NAME}看板")
    months = list_months_cached()
    month_options = sorted(set([*months, st.session_state.selected_month]), reverse=True)
    selected_month = st.selectbox(
        "月份",
        options=month_options,
        index=month_options.index(st.session_state.selected_month) if st.session_state.selected_month in month_options else 0,
        format_func=ym_to_label,
    )
    if selected_month != st.session_state.selected_month:
        load_selected_month(selected_month)
        st.rerun()

    st.caption("上传后会先在页面中预览，再写入当月数据。")
    roster_file = st.file_uploader("上传花名册", type=["xlsx", "xls"], key="roster_uploader")
    order_file = st.file_uploader("上传定单数据", type=["xlsx", "xls"], key="order_uploader")
    personal_file = st.file_uploader("上传个人定单数据", type=["xlsx", "xls"], key="personal_uploader")

    if st.button("保存当前月份", use_container_width=True):
        payload = normalize_month_data(deepcopy(st.session_state.month_data))
        REPOSITORY.save_month(st.session_state.selected_month, payload)
        refresh_month_cache(st.session_state.selected_month)
        st.success(f"已保存到 {ym_to_label(st.session_state.selected_month)}")

month_data = deepcopy(st.session_state.month_data)
period_label = ym_to_label(st.session_state.selected_month)

if roster_file is not None:
    try:
        rows = read_excel_rows(roster_file.getvalue())
        parsed = process_cost_data(rows, zone_name=ZONE_NAME)
        if not parsed:
            st.sidebar.error("花名册格式有误，未识别到人工成本列。")
        else:
            month_data = merge_cost_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_cost = build_cost_preview(month_data)
            st.session_state.preview_messages = [f"花名册已加载：{len(month_data.get('employees') or [])} 条员工记录"]
    except Exception as exc:
        st.sidebar.error(f"花名册导入失败：{exc}")

if order_file is not None:
    try:
        rows = read_excel_rows(order_file.getvalue())
        parsed = process_order_data(rows)
        if not parsed:
            st.sidebar.error("定单数据格式有误。")
        else:
            month_data, stats = merge_order_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_order = display_preview_frame(build_order_preview(month_data))
            st.session_state.preview_messages = [
                f"定单数据已加载：未匹配 {stats['unmatched']} 家，重名冲突 {stats['ambiguous']} 家"
            ]
    except Exception as exc:
        st.sidebar.error(f"定单数据导入失败：{exc}")

if personal_file is not None:
    try:
        rows = read_excel_rows(personal_file.getvalue())
        parsed = process_personal_order_data(rows)
        if not parsed:
            st.sidebar.error("个人定单数据格式有误。")
        else:
            month_data, stats = merge_personal_order_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_personal = display_preview_frame(build_personal_preview(month_data))
            st.session_state.preview_messages = [
                f"个人定单数据已加载：匹配 {stats['matched']} 人，待补齐 {stats['pending']} 人"
            ]
    except Exception as exc:
        st.sidebar.error(f"个人定单数据导入失败：{exc}")

month_data = deepcopy(st.session_state.month_data)
kpis = compute_kpis(month_data)
module_summary = build_module_summary(month_data)
retail_frame = build_retail_frame(month_data)
personnel_frame = build_personnel_frame(month_data)

st.title(f"{ZONE_NAME}人力成本分析看板")
st.caption(f"当前月份：{month_data.get('period') or period_label}")
for message in st.session_state.preview_messages:
    st.success(message)

kpi_cols = st.columns(5)
kpi_cols[0].metric("战区总人工成本", f"{format_wan(kpis['total_labor'])} 万")
kpi_cols[1].metric("战区在编人数", str(kpis["total_count"]))
kpi_cols[2].metric("战区固浮比", format_percent(kpis["fixed_ratio"]))
kpi_cols[3].metric("零售定单达成", format_percent(kpis["order_rate"]))
kpi_cols[4].metric(
    "零售人均总成本",
    "—" if kpis["retail_avg_cost"] is None else f"{kpis['retail_avg_cost'] / 10000:.2f} 万/人",
)

preview_tab, overview_tab, retail_tab, personnel_tab = st.tabs(["上传预览", "总览", "零售明细", "人员明细"])

with preview_tab:
    left, middle, right = st.columns(3)
    with left:
        st.subheader("花名册预览")
        cost_preview = st.session_state.preview_cost or display_preview_frame(build_cost_preview(month_data))
        st.dataframe(cost_preview, use_container_width=True, hide_index=True)
    with middle:
        st.subheader("定单数据预览")
        order_preview = st.session_state.preview_order or display_preview_frame(build_order_preview(month_data))
        st.dataframe(order_preview, use_container_width=True, hide_index=True)
    with right:
        st.subheader("个人定单预览")
        personal_preview = st.session_state.preview_personal or display_preview_frame(build_personal_preview(month_data))
        st.dataframe(personal_preview, use_container_width=True, hide_index=True)

with overview_tab:
    st.subheader("战区分模块成本汇总")
    st.dataframe(display_module_summary(module_summary), use_container_width=True, hide_index=True)
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.plotly_chart(build_module_cost_chart(module_summary), use_container_width=True)
    with chart_col2:
        st.plotly_chart(build_retail_orders_chart(retail_frame), use_container_width=True)

with retail_tab:
    st.subheader("零售门店明细")
    retail_display = retail_frame.copy()
    if not retail_display.empty:
        dept_options = ["全部", *sorted(retail_display["所属部门"].dropna().unique().tolist())]
        selected_dept = st.selectbox("所属部门", dept_options, key="retail_dept_filter")
        if selected_dept != "全部":
            retail_display = retail_display[retail_display["所属部门"] == selected_dept]
        selected_stores = st.multiselect("门店", sorted(retail_display["门店"].dropna().unique().tolist()), key="retail_store_filter")
        if selected_stores:
            retail_display = retail_display[retail_display["门店"].isin(selected_stores)]
    st.dataframe(display_retail_frame(retail_display), use_container_width=True, hide_index=True)
    st.plotly_chart(build_retail_efficiency_chart(retail_display), use_container_width=True)

with personnel_tab:
    st.subheader("人员明细")
    personnel_display = personnel_frame.copy()
    if not personnel_display.empty:
        dept_options = ["全部", *sorted(personnel_display["所属部门"].dropna().unique().tolist())]
        selected_dept = st.selectbox("所属部门", dept_options, key="personnel_dept_filter")
        if selected_dept != "全部":
            personnel_display = personnel_display[personnel_display["所属部门"] == selected_dept]
        store_options = sorted(personnel_display["门店"].dropna().unique().tolist())
        selected_stores = st.multiselect("门店", store_options, key="personnel_store_filter")
        if selected_stores:
            personnel_display = personnel_display[personnel_display["门店"].isin(selected_stores)]
        title_options = sorted(personnel_display["岗位"].dropna().unique().tolist())
        selected_titles = st.multiselect("岗位", title_options, key="personnel_title_filter")
        if selected_titles:
            personnel_display = personnel_display[personnel_display["岗位"].isin(selected_titles)]
    st.dataframe(display_personnel_frame(personnel_display), use_container_width=True, hide_index=True)
    st.plotly_chart(build_personnel_scatter(personnel_display), use_container_width=True)

st.divider()
st.caption(
    f"当前月零售门店 {len(month_data.get('retailStores') or [])} 家，员工 {len(month_data.get('employees') or [])} 人，待补齐个人定单 {len(month_data.get('_pendingEmployeeOrders') or {})} 人。"
)
