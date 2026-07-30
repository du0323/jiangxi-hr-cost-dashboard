from __future__ import annotations

from copy import deepcopy
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from app.analytics import (
    build_annual_summary,
    build_annual_trend_frame,
    build_business_structure_frame,
    build_cost_preview,
    build_cost_structure_frame,
    build_delivery_insight,
    build_delivery_store_frame,
    build_delivery_summary_cards,
    build_delivery_support_frame,
    build_fixed_perf_frame,
    build_kpi_cards,
    build_module_summary,
    build_mom_comparison_frame,
    build_order_preview,
    build_personal_preview,
    build_personnel_frame,
    build_personnel_quadrant_frame,
    build_personnel_quadrant_summary,
    build_personnel_stats,
    build_retail_cost_frame,
    build_retail_frame,
    build_retail_notice,
    build_retail_quadrant_frame,
    build_retail_quadrant_summary,
    build_retail_summary_cards,
    build_store_cost_frame,
    build_support_frame,
    current_month_key,
    display_annual_summary,
    display_delivery_store_frame,
    display_delivery_support_frame,
    display_module_summary,
    display_personnel_frame,
    display_preview_frame,
    display_retail_cost_frame,
    display_retail_frame,
    display_support_frame,
    empty_month,
    filter_personnel_frame,
    filter_retail_frame,
    previous_month_key,
    sort_personnel_frame,
    ym_to_label,
)
from app.normalize import normalize_month_data
from app.charts import (
    build_annual_trend_chart,
    build_business_structure_pie,
    build_cost_structure_pie,
    build_delivery_chart,
    build_fixed_perf_chart,
    build_mom_chart,
    build_personnel_scatter,
    build_retail_cost_distribution_chart,
    build_retail_efficiency_chart,
    build_retail_orders_chart,
    build_store_cost_chart,
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
from app.repository import get_repository

st.set_page_config(page_title="江西战区人力成本分析看板", layout="wide")


PERSONNEL_SORT_OPTIONS = {
    "门店": ("门店", True),
    "姓名": ("姓名", True),
    "岗位": ("岗位", True),
    "部门": ("所属部门", True),
    "分类": ("分类", True),
    "个人成本": ("个人成本", False),
    "个人定单量": ("个人定单量", False),
    "象限": ("象限", True),
}


def secret_or_default(key: str, default: str) -> str:
    try:
        value = st.secrets.get(key, default)
    except StreamlitSecretNotFoundError:
        value = default
    return str(value)


def render_summary_cards(cards: list[dict[str, str]], columns_count: int) -> None:
    if not cards:
        return
    columns = st.columns(columns_count)
    for index, card in enumerate(cards):
        with columns[index % columns_count]:
            st.metric(card["label"], card["value"])


def render_quadrant_summary(items: list[dict[str, Any]], columns_count: int = 2) -> None:
    if not items:
        return
    pairs = [items[index:index + columns_count] for index in range(0, len(items), columns_count)]
    for pair in pairs:
        columns = st.columns(columns_count)
        for index, item in enumerate(pair):
            with columns[index]:
                st.markdown(f"**{item['icon']} {item['title']}**")
                st.caption(item["description"])
                st.caption(f"{item['count']} 个对象")
                if item["items"]:
                    st.write(" / ".join(item["items"]))
                else:
                    st.write("暂无对象")


def render_delivery_cards(frame) -> None:
    if frame.empty:
        st.info("暂无交付中心数据。")
        return
    columns = st.columns(len(frame))
    for index, (_, row) in enumerate(frame.iterrows()):
        with columns[index]:
            st.markdown(f"**🏭 {row['门店']}**")
            st.metric("在编人数", f"{int(row['在编人数'])} 人")
            st.metric("人工成本", f"{int(row['人工成本']):,} 元")
            st.metric("固定成本", f"{int(row['固定成本']):,} 元")
            st.metric("绩效成本", f"{int(row['绩效成本']):,} 元")
            st.metric("法定加班费", f"{int(row['法定加班费']):,} 元")
            st.metric("出差津贴", f"{int(row['出差津贴']):,} 元")
            st.metric("社保公积金（企业）", f"{int(row['社保公积金（企业）']):,} 元")
            avg_total = row['人均总成本']
            avg_fixed = row['人均固定成本']
            avg_perf = row['人均绩效成本']
            fixed_ratio = row['固浮比']
            st.metric("人均总成本", "—" if avg_total is None else f"{int(avg_total):,} 元/人")
            st.metric("人均固定成本", "—" if avg_fixed is None else f"{int(avg_fixed):,} 元/人")
            st.metric("人均绩效成本", "—" if avg_perf is None else f"{int(avg_perf):,} 元/人")
            st.metric("固浮比", "—" if fixed_ratio is None else f"{fixed_ratio * 100:.1f}%")


ZONE_NAME = secret_or_default("zone_name", "江西战区")
REPOSITORY = get_repository()


@st.cache_data(show_spinner=False)
def list_months_cached() -> list[str]:
    return REPOSITORY.list_months()


@st.cache_data(show_spinner=False)
def load_month_cached(ym: str) -> dict[str, Any] | None:
    return REPOSITORY.load_month(ym)


@st.cache_data(show_spinner=False)
def load_annual_payloads(months: tuple[str, ...]) -> list[tuple[str, dict[str, Any]]]:
    payloads: list[tuple[str, dict[str, Any]]] = []
    for ym in months:
        data = REPOSITORY.load_month(ym)
        if data:
            payloads.append((ym, data))
    return payloads


def refresh_month_cache() -> None:
    list_months_cached.clear()
    load_month_cached.clear()
    load_annual_payloads.clear()


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

    if st.button("保存当前月份", width="stretch"):
        payload = normalize_month_data(deepcopy(st.session_state.month_data))
        REPOSITORY.save_month(st.session_state.selected_month, payload)
        refresh_month_cache()
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
            st.session_state.preview_messages = [f"定单数据已加载：未匹配 {stats['unmatched']} 家，重名冲突 {stats['ambiguous']} 家"]
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
            st.session_state.preview_messages = [f"个人定单数据已加载：匹配 {stats['matched']} 人，待补齐 {stats['pending']} 人"]
    except Exception as exc:
        st.sidebar.error(f"个人定单数据导入失败：{exc}")

month_data = deepcopy(st.session_state.month_data)
prev_month = previous_month_key(st.session_state.selected_month)
prev_month_data = normalize_month_data(load_month_cached(prev_month)) if prev_month else None
annual_months = tuple(list_months_cached())
annual_payloads = load_annual_payloads(annual_months) if annual_months else []

kpi_cards = build_kpi_cards(month_data, prev_month_data)
module_summary = build_module_summary(month_data, prev_month_data, zone_name=ZONE_NAME)
fixed_perf_frame = build_fixed_perf_frame(month_data)
business_structure_frame = build_business_structure_frame(month_data)
cost_structure_frame = build_cost_structure_frame(month_data)
store_cost_frame = build_store_cost_frame(month_data)
mom_frame = build_mom_comparison_frame(month_data, prev_month_data)
retail_summary_cards = build_retail_summary_cards(month_data)
retail_notice = build_retail_notice(month_data)
retail_frame = build_retail_frame(month_data, prev_month_data)
retail_cost_frame = build_retail_cost_frame(month_data, prev_month_data)
support_frame = build_support_frame(month_data)
delivery_summary_cards = build_delivery_summary_cards(month_data)
delivery_store_frame = build_delivery_store_frame(month_data)
delivery_support_frame = build_delivery_support_frame(month_data)
delivery_insight = build_delivery_insight(delivery_store_frame)
personnel_frame = build_personnel_frame(month_data)
annual_frame = build_annual_summary(annual_payloads)
annual_trend_frame = build_annual_trend_frame(annual_frame)

st.title(f"{ZONE_NAME}人力成本分析看板")
st.caption(f"当前月份：{month_data.get('period') or period_label}")
for message in st.session_state.preview_messages:
    st.success(message)

kpi_columns = st.columns(5)
for index, card in enumerate(kpi_cards):
    with kpi_columns[index]:
        st.metric(card["label"], card["value"], delta=card["delta"], delta_color=card["delta_color"])
        if card["help"] and card["help"] != "—":
            st.caption(card["help"])

preview_expander = st.expander("上传数据预览", expanded=bool(st.session_state.preview_messages))
with preview_expander:
    left, middle, right = st.columns(3)
    with left:
        st.subheader("花名册预览")
        cost_preview = st.session_state.preview_cost or display_preview_frame(build_cost_preview(month_data))
        st.dataframe(cost_preview, width="stretch", hide_index=True)
    with middle:
        st.subheader("定单数据预览")
        order_preview = st.session_state.preview_order or display_preview_frame(build_order_preview(month_data))
        st.dataframe(order_preview, width="stretch", hide_index=True)
    with right:
        st.subheader("个人定单预览")
        personal_preview = st.session_state.preview_personal or display_preview_frame(build_personal_preview(month_data))
        st.dataframe(personal_preview, width="stretch", hide_index=True)

overview_tab, retail_tab, delivery_tab, personnel_tab, annual_tab = st.tabs(
    ["综合概览", "零售明细", "交付明细", "人员明细", "年度汇总"]
)

with overview_tab:
    top_left, top_right = st.columns(2)
    with top_left:
        st.subheader("零售 vs 交付 固浮比对比")
        st.plotly_chart(build_fixed_perf_chart(fixed_perf_frame), width="stretch")
    with top_right:
        st.subheader("战区成本结构占比")
        pie_left, pie_right = st.columns(2)
        with pie_left:
            st.plotly_chart(build_business_structure_pie(business_structure_frame), width="stretch")
        with pie_right:
            st.plotly_chart(build_cost_structure_pie(cost_structure_frame), width="stretch")
    st.subheader("战区分模块成本汇总")
    st.dataframe(display_module_summary(module_summary), width="stretch", hide_index=True)
    st.subheader("零售门店人工成本对比（固定 vs 绩效）")
    st.plotly_chart(build_store_cost_chart(store_cost_frame), width="stretch")
    st.subheader("与上月环比对比")
    if mom_frame.empty or prev_month_data is None:
        st.info("暂无上月数据，导入后即可自动对比。")
    else:
        st.caption(f"对比：{ym_to_label(prev_month)}")
        st.plotly_chart(build_mom_chart(mom_frame, month_data.get('period') or period_label, ym_to_label(prev_month)), width="stretch")
        st.dataframe(mom_frame, width="stretch", hide_index=True)

with retail_tab:
    render_summary_cards(retail_summary_cards, 6)
    st.caption(retail_notice)
    retail_display = retail_frame.copy()
    retail_cost_display = retail_cost_frame.copy()
    if not retail_display.empty:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            dept_options = ["全部", *sorted(retail_display["所属部门"].dropna().unique().tolist())]
            selected_dept = st.selectbox("所属部门", dept_options, key="retail_dept_filter")
        with filter_col2:
            selected_stores = st.multiselect("门店", sorted(retail_display["门店"].dropna().unique().tolist()), key="retail_store_filter")
        with filter_col3:
            rate_options = ["全部", "超额完成 ≥100%", "达标 85-100%", "偏低 70-85%", "未达标 <70%"]
            selected_rate = st.selectbox("达成状态", rate_options, key="retail_rate_filter")
        retail_display = filter_retail_frame(retail_display, selected_dept, selected_stores, selected_rate)
        if not retail_cost_display.empty:
            retail_cost_display = retail_cost_display[retail_cost_display["门店"].isin(retail_display["门店"].tolist())]
    st.subheader("零售门店综合分析")
    st.dataframe(display_retail_frame(retail_display), width="stretch", hide_index=True)
    st.subheader("补充成本明细（含环比）")
    st.dataframe(display_retail_cost_frame(retail_cost_display), width="stretch", hide_index=True)
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("门店定单达成分析")
        st.plotly_chart(build_retail_orders_chart(retail_display), width="stretch")
    with chart_col2:
        st.subheader("人均总成本分布")
        st.plotly_chart(build_retail_cost_distribution_chart(retail_display), width="stretch")
    st.subheader("人效 vs 人均总成本 · 四象限分析")
    retail_quadrant_frame = build_retail_quadrant_frame(retail_display)
    st.plotly_chart(build_retail_efficiency_chart(retail_quadrant_frame), width="stretch")
    render_quadrant_summary(build_retail_quadrant_summary(retail_quadrant_frame))
    st.subheader("零售战区级支持部门")
    st.dataframe(display_support_frame(support_frame), width="stretch", hide_index=True)

with delivery_tab:
    render_summary_cards(delivery_summary_cards, min(4, len(delivery_summary_cards) or 1))
    render_delivery_cards(delivery_store_frame)
    st.subheader("两大交付中心对比")
    st.plotly_chart(build_delivery_chart(delivery_store_frame), width="stretch")
    st.caption(delivery_insight)
    st.subheader("交付战区级（管理人员）")
    st.dataframe(display_delivery_support_frame(delivery_support_frame), width="stretch", hide_index=True)

with personnel_tab:
    render_summary_cards(build_personnel_stats(personnel_frame), 4)
    personnel_display = personnel_frame.copy()
    if not personnel_display.empty:
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            dept_options = ["全部", *sorted(personnel_display["所属部门"].dropna().unique().tolist())]
            selected_dept = st.selectbox("所属部门", dept_options, key="personnel_dept_filter")
        with filter_col2:
            selected_stores = st.multiselect("门店", sorted(personnel_display["门店"].dropna().unique().tolist()), key="personnel_store_filter")
        with filter_col3:
            title_options = sorted([title for title in personnel_display["岗位"].dropna().unique().tolist() if title])
            selected_titles = st.multiselect("岗位", title_options, key="personnel_title_filter")
        with filter_col4:
            sort_choice = st.selectbox("排序", list(PERSONNEL_SORT_OPTIONS.keys()), index=0, key="personnel_sort_choice")
        personnel_display = filter_personnel_frame(personnel_display, selected_dept, selected_stores, selected_titles)
    personnel_quadrant_frame = build_personnel_quadrant_frame(personnel_display)
    st.subheader("个人成本 vs 定单量 四象限分析")
    st.plotly_chart(build_personnel_scatter(personnel_quadrant_frame), width="stretch")
    render_quadrant_summary(build_personnel_quadrant_summary(personnel_quadrant_frame))
    sort_column, ascending = PERSONNEL_SORT_OPTIONS[st.session_state.get("personnel_sort_choice", "门店")]
    personnel_table = personnel_quadrant_frame.copy() if not personnel_quadrant_frame.empty else personnel_display.copy()
    if not personnel_table.empty:
        personnel_table = sort_personnel_frame(personnel_table, sort_column, ascending=ascending)
    st.subheader("人员明细列表")
    st.dataframe(display_personnel_frame(personnel_table), width="stretch", hide_index=True)

with annual_tab:
    st.subheader("1–12月数据汇总")
    st.dataframe(display_annual_summary(annual_frame), width="stretch", hide_index=True)
    st.subheader("年度趋势")
    st.plotly_chart(build_annual_trend_chart(annual_trend_frame), width="stretch")

st.divider()
st.caption(
    f"当前月零售门店 {len(month_data.get('retailStores') or [])} 家，员工 {len(month_data.get('employees') or [])} 人，待补齐个人定单 {len(month_data.get('_pendingEmployeeOrders') or {})} 人。"
)
