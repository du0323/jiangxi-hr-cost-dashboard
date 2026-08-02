from __future__ import annotations

from copy import deepcopy
from html import escape
import importlib
from typing import Any, Optional

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

analytics = importlib.import_module("app.analytics")
if not hasattr(analytics, "build_annual_summary"):
    analytics = importlib.reload(analytics)

build_annual_summary = analytics.build_annual_summary
build_annual_trend_frame = analytics.build_annual_trend_frame
build_business_structure_frame = analytics.build_business_structure_frame
build_cost_preview = analytics.build_cost_preview
build_cost_structure_frame = analytics.build_cost_structure_frame
build_delivery_insight = analytics.build_delivery_insight
build_delivery_store_frame = analytics.build_delivery_store_frame
build_delivery_summary_cards = analytics.build_delivery_summary_cards
build_delivery_support_frame = analytics.build_delivery_support_frame
build_fixed_perf_frame = analytics.build_fixed_perf_frame
build_kpi_cards = analytics.build_kpi_cards
build_module_summary = analytics.build_module_summary
build_mom_comparison_frame = analytics.build_mom_comparison_frame
build_order_preview = analytics.build_order_preview
build_personal_preview = analytics.build_personal_preview
build_personnel_frame = analytics.build_personnel_frame
build_personnel_quadrant_frame = analytics.build_personnel_quadrant_frame
build_personnel_quadrant_summary = analytics.build_personnel_quadrant_summary
build_personnel_stats = analytics.build_personnel_stats
build_retail_cost_frame = analytics.build_retail_cost_frame
build_retail_frame = analytics.build_retail_frame
build_retail_notice = analytics.build_retail_notice
build_retail_quadrant_frame = analytics.build_retail_quadrant_frame
build_retail_quadrant_summary = analytics.build_retail_quadrant_summary
build_retail_summary_cards = analytics.build_retail_summary_cards
build_store_cost_frame = analytics.build_store_cost_frame
build_support_frame = analytics.build_support_frame
current_month_key = analytics.current_month_key
display_annual_summary = analytics.display_annual_summary
display_module_summary = analytics.display_module_summary
display_personnel_frame = analytics.display_personnel_frame
display_preview_frame = analytics.display_preview_frame
display_retail_cost_frame = analytics.display_retail_cost_frame
display_retail_frame = analytics.display_retail_frame
display_support_frame = analytics.display_support_frame
empty_month = analytics.empty_month
filter_personnel_frame = analytics.filter_personnel_frame
filter_retail_frame = analytics.filter_retail_frame
previous_month_key = analytics.previous_month_key
sort_personnel_frame = analytics.sort_personnel_frame
ym_to_label = analytics.ym_to_label
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

LEGACY_CSS = """
<style>
:root {
  --bg:#f0f5f4;
  --card:#ffffff;
  --border:#c8d8d6;
  --primary:#00726D;
  --primary-light:#e0f2f0;
  --primary-dark:#002D28;
  --fixed-color:#00726D;
  --perf-color:#CEA472;
  --green:#16a34a;
  --green-bg:#dcfce7;
  --red:#dc2626;
  --red-bg:#fee2e2;
  --orange:#d97706;
  --orange-bg:#fef3c7;
  --text:#333333;
  --sub:#666666;
}
html, body, [class*="css"] {
  font-family:'PingFang SC','Microsoft YaHei',sans-serif;
}
.stApp,
[data-testid="stAppViewContainer"] {
  background:var(--bg);
  color:var(--text);
}
[data-testid="stHeader"] {
  background:transparent;
}
section[data-testid="stSidebar"],
[data-testid="collapsedControl"] {
  display:none !important;
}
.block-container {
  max-width:1440px;
  padding-top:1rem;
  padding-bottom:2rem;
}
.legacy-header {
  background:linear-gradient(135deg,var(--primary-dark),var(--primary));
  color:#fff;
  padding:14px 20px;
  border-radius:10px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:12px;
}
.legacy-header-title {
  font-size:19px;
  font-weight:700;
  letter-spacing:.3px;
}
.legacy-header-sub {
  font-size:11px;
  opacity:.82;
  margin-top:2px;
}
.legacy-period-badge {
  background:rgba(255,255,255,.2);
  border-radius:20px;
  padding:4px 14px;
  font-size:13px;
  font-weight:600;
  white-space:nowrap;
}
.legacy-import-tip {
  font-size:11px;
  color:var(--sub);
  margin:6px 0 2px;
}
div[class*="st-key-legacy-import-bar"] {
  background:#fff;
  border-bottom:1px solid var(--border);
  border-radius:0;
  padding:10px 20px 6px;
  margin-bottom:0;
}
div[class*="st-key-legacy-import-bar"] > div[data-testid="stVerticalBlock"] {
  gap:0.35rem;
}
div[class*="st-key-legacy-import-bar"] .stMarkdown {
  margin-top:0.35rem;
}
div[class*="st-key-legacy-import-bar"] [data-testid="stFileUploader"] {
  margin-top:0;
}
div[class*="st-key-legacy-import-bar"] [data-testid="stFileUploaderDropzone"] {
  min-height:42px;
  border:1.5px dashed var(--border);
  border-radius:7px;
  background:#f8fafc;
  padding:0 12px;
}
div[class*="st-key-legacy-import-bar"] [data-testid="stFileUploaderDropzoneInstructions"] > div,
div[class*="st-key-legacy-import-bar"] [data-testid="stFileUploaderDropzoneInstructions"] span,
div[class*="st-key-legacy-import-bar"] [data-testid="stFileUploaderDropzoneInstructions"] small {
  font-size:11px !important;
  color:var(--sub) !important;
}
div[class*="st-key-legacy-import-bar"] .stButton > button {
  min-height:40px;
}
.legacy-preview-board {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:12px;
  margin:12px 0 0;
}
.legacy-preview-card {
  background:var(--card);
  border-radius:10px;
  border:1px solid var(--border);
  padding:14px;
}
.legacy-preview-head {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
.legacy-preview-title {
  font-size:13px;
  font-weight:700;
  color:var(--primary-dark);
}
.legacy-preview-sub {
  font-size:11px;
  color:var(--sub);
  margin-top:2px;
}
.legacy-preview-count {
  font-size:11px;
  font-weight:700;
  color:var(--primary);
  background:var(--primary-light);
  padding:3px 9px;
  border-radius:999px;
  white-space:nowrap;
}
.legacy-preview-meta {
  margin-top:8px;
  font-size:11px;
  color:var(--sub);
}
div[class*="st-key-legacy-month-bar"] {
  background:#fff;
  border-bottom:1px solid var(--border);
  border-radius:0;
  padding:8px 20px 10px;
  margin-bottom:0;
}
div[class*="st-key-legacy-month-bar"] > div[data-testid="stVerticalBlock"] {
  gap:0.4rem;
}
div[class*="st-key-legacy-month-bar"] .stButton > button {
  min-height:34px;
  padding:4px 12px;
  border-radius:20px;
  font-size:12px;
}
div[class*="st-key-legacy-month-bar"] .stButton > button[kind="secondary"] {
  background:#f8fafc;
  color:var(--sub);
  border:1.5px solid var(--border);
}
div[class*="st-key-legacy-month-bar"] .stButton > button[kind="primary"] {
  background:var(--primary);
  border-color:var(--primary);
  color:#fff;
}
.legacy-month-label {
  font-size:11px;
  color:var(--sub);
  font-weight:600;
}
.legacy-kpi-grid {
  display:grid;
  grid-template-columns:repeat(5,minmax(0,1fr));
  gap:10px;
  margin:12px 0 8px;
}
.legacy-kpi-card {
  background:var(--card);
  border-radius:10px;
  padding:12px 14px;
  border:1px solid var(--border);
  border-top:3px solid var(--primary);
}
.legacy-kpi-card.green { border-top-color:var(--green); }
.legacy-kpi-card.orange { border-top-color:var(--orange); }
.legacy-kpi-card.red { border-top-color:var(--red); }
.legacy-kpi-label {
  font-size:11px;
  color:var(--sub);
  font-weight:500;
  margin-bottom:6px;
}
.legacy-kpi-value {
  font-size:21px;
  line-height:1;
  font-weight:700;
  color:var(--text);
}
.legacy-kpi-delta {
  margin-top:6px;
  font-size:11px;
  font-weight:700;
}
.legacy-kpi-delta.up { color:var(--red); }
.legacy-kpi-delta.down { color:var(--green); }
.legacy-kpi-delta.flat { color:var(--sub); }
.legacy-kpi-help {
  margin-top:4px;
  font-size:11px;
  color:var(--sub);
}
.legacy-summary-grid {
  display:grid;
  gap:8px;
  margin-bottom:12px;
}
.legacy-summary-grid.cols-6 {
  grid-template-columns:repeat(6,minmax(0,1fr));
}
.legacy-summary-grid.cols-5 {
  grid-template-columns:repeat(5,minmax(0,1fr));
}
.legacy-summary-grid.cols-4 {
  grid-template-columns:repeat(4,minmax(0,1fr));
}
.legacy-summary-grid.cols-3 {
  grid-template-columns:repeat(3,minmax(0,1fr));
}
.legacy-summary-grid.cols-2 {
  grid-template-columns:repeat(2,minmax(0,1fr));
}
.legacy-summary-card {
  background:var(--card);
  border-radius:8px;
  padding:9px 10px;
  border:1px solid var(--border);
  text-align:center;
}
.legacy-summary-label {
  font-size:10px;
  color:var(--sub);
  margin-bottom:3px;
}
.legacy-summary-value {
  font-size:15px;
  font-weight:700;
  color:var(--text);
}
.legacy-section-title {
  font-size:13px;
  font-weight:700;
  margin:6px 0 10px;
  display:flex;
  align-items:center;
  gap:7px;
  color:var(--text);
}
.legacy-section-title::before {
  content:'';
  width:3px;
  height:13px;
  background:var(--primary);
  border-radius:2px;
  display:inline-block;
}
.legacy-card,
div[class*="st-key-legacy-card-"] {
  background:var(--card);
  border-radius:10px;
  border:1px solid var(--border);
  padding:14px 0;
  margin-bottom:12px;
  box-shadow:none;
}
.legacy-card.compact,
div[class*="st-key-legacy-card-compact-"] {
  padding-top:10px;
}
div[class*="st-key-legacy-card-"] > div[data-testid="stVerticalBlock"],
div[class*="st-key-legacy-filter-bar-"] > div[data-testid="stVerticalBlock"] {
  gap:0.4rem;
}
div[class*="st-key-legacy-card-"] > div[data-testid="stVerticalBlock"] {
  padding:0 14px;
}
div[class*="st-key-legacy-card-compact-"] > div[data-testid="stVerticalBlock"] {
  padding:0;
}
.legacy-note {
  background:#fef9c3;
  border:1px solid #fde047;
  border-radius:8px;
  padding:8px 12px;
  font-size:11px;
  color:#713f12;
  margin-bottom:10px;
}
.legacy-empty {
  text-align:center;
  padding:24px 12px;
  color:var(--sub);
  font-size:12px;
}
.legacy-quadrant-grid {
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:10px;
  margin-top:12px;
}
.legacy-quadrant-card {
  border-radius:8px;
  border:1px solid var(--border);
  background:#f8fafc;
  padding:12px 14px;
}
.legacy-quadrant-head {
  display:flex;
  align-items:center;
  gap:6px;
  font-size:13px;
  font-weight:700;
  color:var(--text);
}
.legacy-quadrant-desc {
  margin-top:5px;
  font-size:11px;
  color:var(--sub);
  line-height:1.5;
}
.legacy-quadrant-count {
  margin-top:8px;
  font-size:11px;
  color:var(--primary);
  font-weight:700;
}
.legacy-quadrant-items {
  margin-top:6px;
  font-size:11px;
  color:var(--text);
  line-height:1.6;
}
.legacy-footer-note {
  font-size:11px;
  color:#aaaaaa;
  text-align:center;
  padding:12px 0 6px;
}
.legacy-delivery-metric {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:5px 0;
  border-bottom:1px dashed var(--border);
  gap:10px;
}
.legacy-delivery-metric:last-child {
  border-bottom:none;
}
.legacy-delivery-metric span {
  font-size:11px;
  color:var(--sub);
}
.legacy-delivery-metric strong {
  font-size:13px;
  color:var(--text);
}
div[class*="st-key-legacy-filter-bar-"] {
  background:var(--card);
  border-radius:10px;
  border:1px solid var(--border);
  padding:12px 14px 8px;
  margin-bottom:12px;
}
div[class*="st-key-legacy-filter-bar-"] .stButton > button {
  min-height:38px;
}
.legacy-filter-count {
  font-size:11px;
  color:var(--sub);
  text-align:right;
  padding-top:0.55rem;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
  gap:2px;
  border-bottom:2px solid var(--border);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
  height:auto;
  padding:8px 18px;
  background:transparent;
  border-radius:6px 6px 0 0;
  color:var(--sub);
  font-size:13px;
  font-weight:600;
}
[data-testid="stTabs"] [aria-selected="true"] {
  background:var(--primary-light);
  color:var(--primary);
  border-bottom:2px solid var(--primary);
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
  padding-top:14px;
}
.stSelectbox label,
.stMultiSelect label,
.stFileUploader label {
  color:var(--sub);
  font-size:11px;
  font-weight:600;
}
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div,
.stTextInput input {
  background:#f8fafc;
  border-color:var(--border);
  border-radius:6px;
  color:var(--text);
  min-height:38px;
}
.stButton > button {
  border-radius:7px;
  border:1.5px solid var(--border);
  background:#ffffff;
  color:var(--sub);
  font-size:12px;
  font-weight:600;
}
.stButton > button:hover {
  border-color:var(--primary);
  color:var(--primary);
  background:var(--primary-light);
}
[data-testid="stAlert"] {
  border-radius:8px;
}
[data-testid="stPlotlyChart"] {
  border:none;
}
.legacy-table-wrap {
  overflow:auto;
  border:1px solid var(--border);
  border-radius:8px;
  background:#fff;
}
.legacy-table-wrap.preview {
  max-height:240px;
}
.legacy-html-table {
  width:100%;
  border-collapse:collapse;
  font-size:12px;
}
.legacy-html-table thead th {
  background:#f8fafc;
  color:var(--sub);
  font-weight:600;
  padding:8px 9px;
  text-align:center;
  border-bottom:2px solid var(--border);
  white-space:nowrap;
  position:sticky;
  top:0;
  z-index:1;
}
.legacy-html-table thead th:first-child,
.legacy-html-table tbody td:first-child {
  text-align:left;
}
.legacy-html-table tbody tr:hover {
  background:#f8fafc;
}
.legacy-html-table tbody td {
  padding:7px 9px;
  border-bottom:1px solid var(--border);
  text-align:center;
  white-space:nowrap;
}
.legacy-html-table tbody tr:last-child td {
  border-bottom:none;
}
.legacy-html-table tbody tr.legacy-total-row td {
  font-weight:700;
  background:#f0f9ff;
  color:var(--primary-dark);
}
.legacy-annual-table thead tr:first-child th {
  background:#eef2f1;
  color:var(--primary-dark);
}
.legacy-annual-table thead tr:nth-child(2) th {
  background:#f8fafc;
}
.legacy-empty-inline {
  padding:22px 12px;
  text-align:center;
  font-size:11px;
  color:var(--sub);
}
[data-testid="stMarkdownContainer"] p {
  color:var(--text);
}
@media (max-width: 1100px) {
  .legacy-header {
    flex-direction:column;
    align-items:flex-start;
  }
  .legacy-kpi-grid {
    grid-template-columns:repeat(2,minmax(0,1fr));
  }
  .legacy-summary-grid.cols-6,
  .legacy-summary-grid.cols-5,
  .legacy-summary-grid.cols-4,
  .legacy-summary-grid.cols-3 {
    grid-template-columns:repeat(2,minmax(0,1fr));
  }
  .legacy-quadrant-grid,
  .legacy-preview-board {
    grid-template-columns:1fr;
  }
}
</style>
"""

st.markdown(LEGACY_CSS, unsafe_allow_html=True)

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


def _safe_text(value: Any) -> str:
    return escape(str(value if value is not None else ""))


def _is_missing_number(value: Any) -> bool:
    try:
        return value is None or value != value
    except Exception:
        return value is None


def _format_number(value: Any, suffix: str = "") -> str:
    if _is_missing_number(value):
        return "—"
    return f"{int(float(value)):,}{suffix}"


def _format_ratio(value: Any) -> str:
    if _is_missing_number(value):
        return "—"
    return f"{float(value) * 100:.1f}%"


def _is_total_like(value: Any) -> bool:
    text = str(value or "")
    return "合计" in text or "总计" in text


def _render_html_table(frame: pd.DataFrame, table_class: str = "", wrapper_class: str = "") -> str:
    if frame is None or frame.empty:
        return "<div class='legacy-empty-inline'>暂无数据</div>"
    wrapper = "legacy-table-wrap"
    if wrapper_class:
        wrapper = f"{wrapper} {wrapper_class}"
    table = "legacy-html-table"
    if table_class:
        table = f"{table} {table_class}"
    parts: list[str] = [f"<div class='{wrapper}'><table class='{table}'><thead><tr>"]
    for column in frame.columns:
        parts.append(f"<th>{_safe_text(column)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in frame.itertuples(index=False, name=None):
        row_class = "legacy-total-row" if row and _is_total_like(row[0]) else ""
        parts.append(f"<tr class='{row_class}'>")
        for value in row:
            parts.append(f"<td>{_safe_text(value)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def render_html_table(frame: pd.DataFrame, table_class: str = "", wrapper_class: str = "") -> None:
    st.markdown(_render_html_table(frame, table_class=table_class, wrapper_class=wrapper_class), unsafe_allow_html=True)


def render_annual_table(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        st.markdown("<div class='legacy-empty-inline'>暂无数据</div>", unsafe_allow_html=True)
        return
    required_columns = [
        "月份",
        "战区总人工成本（万）",
        "战区固定（万）",
        "战区绩效（万）",
        "战区人数",
        "零售总成本（万）",
        "零售固定（万）",
        "零售绩效（万）",
        "零售人数",
        "零售总定单量",
        "零售人效（单/人）",
        "交付总成本（万）",
        "交付固定（万）",
        "交付绩效（万）",
        "交付人数",
        "总交付量",
        "交付人效（单/人）",
    ]
    if any(column not in frame.columns for column in required_columns):
        render_html_table(frame, table_class="legacy-annual-table")
        return
    display = frame[required_columns]
    parts: list[str] = [
        "<div class='legacy-table-wrap'><table class='legacy-html-table legacy-annual-table'><thead>",
        "<tr>",
        "<th rowspan='2'>月份</th>",
        "<th colspan='4'>战区</th>",
        "<th colspan='6'>零售</th>",
        "<th colspan='6'>交付</th>",
        "</tr>",
        "<tr>",
        "<th>总成本（万）</th><th>固定（万）</th><th>绩效（万）</th><th>人数</th>",
        "<th>总成本（万）</th><th>固定（万）</th><th>绩效（万）</th><th>人数</th><th>总定单量</th><th>人效（单/人）</th>",
        "<th>总成本（万）</th><th>固定（万）</th><th>绩效（万）</th><th>人数</th><th>总交付量</th><th>人效（单/人）</th>",
        "</tr></thead><tbody>",
    ]
    for row in display.itertuples(index=False, name=None):
        row_class = "legacy-total-row" if row and _is_total_like(row[0]) else ""
        parts.append(f"<tr class='{row_class}'>")
        for value in row:
            parts.append(f"<td>{_safe_text(value)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_summary_cards(cards: list[dict[str, str]], columns_count: int) -> None:
    if not cards:
        return
    columns_count = max(1, min(columns_count, 6))
    parts: list[str] = [f"<div class='legacy-summary-grid cols-{columns_count}'>"]
    for card in cards:
        parts.append(
            f"<div class=\"legacy-summary-card\">"
            f"<div class=\"legacy-summary-label\">{_safe_text(card['label'])}</div>"
            f"<div class=\"legacy-summary-value\">{_safe_text(card['value'])}</div>"
            f"</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str, period: str) -> None:
    st.markdown(
        f"<div class=\"legacy-header\">"
        f"<div>"
        f"<div class=\"legacy-header-title\">{_safe_text(title)}</div>"
        f"<div class=\"legacy-header-sub\">{_safe_text(subtitle)}</div>"
        f"</div>"
        f"<div class=\"legacy-period-badge\">{_safe_text(period)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_kpi_cards(cards: list[dict[str, Optional[str]]]) -> None:
    if not cards:
        return
    variants = ["", "", "orange", "green", ""]
    parts: list[str] = ["<div class='legacy-kpi-grid'>"]
    for index, card in enumerate(cards):
        delta = card.get("delta") or ""
        delta_class = "flat"
        if delta.startswith("+"):
            delta_class = "up"
        elif delta.startswith("-"):
            delta_class = "down"
        help_text = card.get("help") or ""
        variant = variants[index % len(variants)]
        class_name = f"legacy-kpi-card {variant}".strip()
        help_html = _safe_text(help_text) if help_text and help_text != "—" else "&nbsp;"
        parts.append(
            f"<div class=\"{class_name}\">"
            f"<div class=\"legacy-kpi-label\">{_safe_text(card['label'])}</div>"
            f"<div class=\"legacy-kpi-value\">{_safe_text(card['value'])}</div>"
            f"<div class=\"legacy-kpi-delta {delta_class}\">{_safe_text(delta or '—')}</div>"
            f"<div class=\"legacy-kpi-help\">{help_html}</div>"
            f"</div>"
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_section_title(title: str) -> None:
    st.markdown(f"<div class='legacy-section-title'>{_safe_text(title)}</div>", unsafe_allow_html=True)


_CARD_COUNTER = 0
_FILTER_BAR_COUNTER = 0


def open_card(compact: bool = False):
    global _CARD_COUNTER
    prefix = "legacy-card-compact" if compact else "legacy-card"
    container = st.container(key=f"{prefix}-{_CARD_COUNTER}")
    _CARD_COUNTER += 1
    return container


def open_filter_bar():
    global _FILTER_BAR_COUNTER
    container = st.container(key=f"legacy-filter-bar-{_FILTER_BAR_COUNTER}")
    _FILTER_BAR_COUNTER += 1
    return container


def render_notice(text: str) -> None:
    st.markdown(f"<div class='legacy-note'>{_safe_text(text)}</div>", unsafe_allow_html=True)


def render_preview_card(title: str, subtitle: str, frame: pd.DataFrame, meta: str) -> None:
    count = len(frame.index) if frame is not None and not frame.empty else 0
    st.markdown(
        f"""
        <div class=\"legacy-preview-card\">
          <div class=\"legacy-preview-head\">
            <div>
              <div class=\"legacy-preview-title\">{_safe_text(title)}</div>
              <div class=\"legacy-preview-sub\">{_safe_text(subtitle)}</div>
            </div>
            <div class=\"legacy-preview-count\">{count} 行</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_html_table(frame, wrapper_class="preview")
    st.markdown(f"<div class='legacy-preview-meta'>{_safe_text(meta)}</div>", unsafe_allow_html=True)


def render_preview_board(cost_preview: pd.DataFrame, order_preview: pd.DataFrame, personal_preview: pd.DataFrame) -> None:
    left, middle, right = st.columns(3)
    with left:
        render_preview_card("花名册预览", "员工与人工成本最新预览", cost_preview, "最多显示 50 行预览数据")
    with middle:
        render_preview_card("定单数据预览", "门店定单与目标预览", order_preview, "最多显示 50 行预览数据")
    with right:
        render_preview_card("个人定单预览", "员工个人定单量预览", personal_preview, "最多显示 50 行预览数据")


def render_import_bar(month_options: list[str]) -> tuple[str, Any, Any, Any, bool]:
    current_year, current_month = st.session_state.import_target_month.split("-", 1)
    year_options = sorted({ym.split("-", 1)[0] for ym in month_options} | {current_year, str(int(current_year) - 1), str(int(current_year) + 1)}, reverse=True)
    month_labels = {index: f"{index}月" for index in range(1, 13)}
    with st.container(key="legacy-import-bar"):
        columns = st.columns([0.8, 1.2, 1.2, 1.2, 0.8, 0.8, 1.0])
        with columns[0]:
            st.markdown("<div class='legacy-month-label'>导入数据</div>", unsafe_allow_html=True)
        with columns[1]:
            roster_file = st.file_uploader("上传花名册", type=["xlsx", "xls"], key="roster_uploader", label_visibility="collapsed")
        with columns[2]:
            order_file = st.file_uploader("上传定单数据", type=["xlsx", "xls"], key="order_uploader", label_visibility="collapsed")
        with columns[3]:
            personal_file = st.file_uploader("上传个人定单数据", type=["xlsx", "xls"], key="personal_uploader", label_visibility="collapsed")
        with columns[4]:
            selected_year = st.selectbox(
                "年份",
                options=year_options,
                index=year_options.index(current_year),
                label_visibility="collapsed",
            )
        with columns[5]:
            selected_month_number = st.selectbox(
                "月份",
                options=list(range(1, 13)),
                index=int(current_month) - 1,
                format_func=lambda value: month_labels[value],
                label_visibility="collapsed",
            )
        with columns[6]:
            save_clicked = st.button("保存当前月份", use_container_width=True)
        st.markdown("<div class='legacy-import-tip'>上传后会先在页面中预览，再写入所选年月数据。</div>", unsafe_allow_html=True)
    selected_ym = f"{selected_year}-{int(selected_month_number):02d}"
    return selected_ym, roster_file, order_file, personal_file, save_clicked


def render_month_bar(month_options: list[str], selected_month: str) -> None:
    with st.container(key="legacy-month-bar"):
        st.markdown("<div class='legacy-month-label'>查看月份</div>", unsafe_allow_html=True)
        for start in range(0, len(month_options), 6):
            row = month_options[start : start + 6]
            columns = st.columns(len(row))
            for index, ym in enumerate(row):
                with columns[index]:
                    if st.button(
                        ym_to_label(ym),
                        key=f"month-chip-{ym}",
                        use_container_width=True,
                        type="primary" if ym == selected_month else "secondary",
                    ):
                        load_selected_month(ym)
                        st.rerun()


def render_quadrant_summary(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    columns = st.columns(2)
    for index, item in enumerate(items):
        members = " / ".join(_safe_text(name) for name in item["items"]) if item["items"] else "暂无对象"
        with columns[index % 2]:
            st.markdown(
                f"""
                <div class=\"legacy-quadrant-card\">
                  <div class=\"legacy-quadrant-head\">{_safe_text(item['icon'])} {_safe_text(item['title'])}</div>
                  <div class=\"legacy-quadrant-desc\">{_safe_text(item['description'])}</div>
                  <div class=\"legacy-quadrant-count\">{_safe_text(item['count'])} 个对象</div>
                  <div class=\"legacy-quadrant-items\">{members}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_delivery_cards(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.markdown("<div class='legacy-empty'>暂无交付中心数据</div>", unsafe_allow_html=True)
        return
    columns = st.columns(len(frame))
    for index, (_, row) in enumerate(frame.iterrows()):
        with columns[index]:
            with open_card():
                render_section_title(f"🏭 {row['门店']}")
                metrics = [
                    ("在编人数", _format_number(row['在编人数'], ' 人')),
                    ("人工成本", _format_number(row['人工成本'], ' 元')),
                    ("固定成本", _format_number(row['固定成本'], ' 元')),
                    ("绩效成本", _format_number(row['绩效成本'], ' 元')),
                    ("法定加班费", _format_number(row['法定加班费'], ' 元')),
                    ("出差津贴", _format_number(row['出差津贴'], ' 元')),
                    ("社保公积金（企业）", _format_number(row['社保公积金（企业）'], ' 元')),
                    ("人均总成本", _format_number(row['人均总成本'], ' 元/人')),
                    ("人均固定成本", _format_number(row['人均固定成本'], ' 元/人')),
                    ("人均绩效成本", _format_number(row['人均绩效成本'], ' 元/人')),
                    ("固浮比", _format_ratio(row['固浮比'])),
                ]
                for label, value in metrics:
                    st.markdown(
                        f"<div class='legacy-delivery-metric'><span>{_safe_text(label)}</span><strong>{_safe_text(value)}</strong></div>",
                        unsafe_allow_html=True,
                    )


def render_table_block(title: str, frame: pd.DataFrame, table_class: str = "") -> None:
    render_section_title(title)
    render_html_table(frame, table_class=table_class)


def render_chart_block(title: str, figure, help_text: Optional[str] = None) -> None:
    render_section_title(title)
    if figure is None:
        st.markdown("<div class='legacy-empty'>暂无图表数据</div>", unsafe_allow_html=True)
        return
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True})
    if help_text:
        st.caption(help_text)


def render_empty_block(text: str) -> None:
    st.markdown(f"<div class='legacy-empty'>{_safe_text(text)}</div>", unsafe_allow_html=True)


ZONE_NAME = secret_or_default("zone_name", "江西战区")
REPOSITORY = get_repository()


@st.cache_data(show_spinner=False)
def list_months_cached() -> list[str]:
    return REPOSITORY.list_months()


@st.cache_data(show_spinner=False)
def load_month_cached(ym: str) -> Optional[dict[str, Any]]:
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
if "import_target_month" not in st.session_state:
    st.session_state.import_target_month = st.session_state.selected_month


def load_selected_month(ym: str) -> None:
    data = load_month_cached(ym)
    st.session_state.selected_month = ym
    st.session_state.import_target_month = ym
    st.session_state.month_data = normalize_month_data(data) or empty_month(ym_to_label(ym))
    st.session_state.preview_cost = None
    st.session_state.preview_order = None
    st.session_state.preview_personal = None


def reset_retail_filters() -> None:
    st.session_state.retail_dept_filter = "全部"
    st.session_state.retail_store_filter = []
    st.session_state.retail_rate_filter = "全部"


def reset_personnel_filters() -> None:
    st.session_state.personnel_dept_filter = "全部"
    st.session_state.personnel_store_filter = []
    st.session_state.personnel_title_filter = []
    st.session_state.personnel_sort_choice = "门店"


months = list_months_cached()
month_options = sorted(set([*months, st.session_state.selected_month]), reverse=True)
period_label = ym_to_label(st.session_state.selected_month)
render_page_header(
    f"{ZONE_NAME}人力成本分析看板",
    "数据来源：实际发放成本 + 定单数据 | 人数口径：不含实习生",
    period_label,
)
selected_month, roster_file, order_file, personal_file, save_clicked = render_import_bar(month_options)
st.session_state.import_target_month = selected_month
if selected_month != st.session_state.selected_month and not any(file is not None for file in [roster_file, order_file, personal_file]):
    load_selected_month(selected_month)
    st.rerun()

page_messages: list[tuple[str, str]] = []
month_data = deepcopy(st.session_state.month_data)
period_label = ym_to_label(selected_month)

if roster_file is not None:
    try:
        rows = read_excel_rows(roster_file.getvalue())
        parsed = process_cost_data(rows, zone_name=ZONE_NAME)
        if not parsed:
            page_messages.append(("error", "花名册格式有误，未识别到人工成本列。"))
        else:
            month_data = merge_cost_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_cost = display_preview_frame(build_cost_preview(month_data))
            page_messages.append(("success", f"花名册已加载：{len(month_data.get('employees') or [])} 条员工记录"))
    except Exception as exc:
        page_messages.append(("error", f"花名册导入失败：{exc}"))

if order_file is not None:
    try:
        rows = read_excel_rows(order_file.getvalue())
        parsed = process_order_data(rows)
        if not parsed:
            page_messages.append(("error", "定单数据格式有误。"))
        else:
            month_data, stats = merge_order_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_order = display_preview_frame(build_order_preview(month_data))
            page_messages.append(("success", f"定单数据已加载：未匹配 {stats['unmatched']} 家，重名冲突 {stats['ambiguous']} 家"))
    except Exception as exc:
        page_messages.append(("error", f"定单数据导入失败：{exc}"))

if personal_file is not None:
    try:
        rows = read_excel_rows(personal_file.getvalue())
        parsed = process_personal_order_data(rows)
        if not parsed:
            page_messages.append(("error", "个人定单数据格式有误。"))
        else:
            month_data, stats = merge_personal_order_import(month_data, parsed, period_label)
            month_data = normalize_month_data(month_data) or month_data
            st.session_state.month_data = month_data
            st.session_state.preview_personal = display_preview_frame(build_personal_preview(month_data))
            page_messages.append(("success", f"个人定单数据已加载：匹配 {stats['matched']} 人，待补齐 {stats['pending']} 人"))
    except Exception as exc:
        page_messages.append(("error", f"个人定单数据导入失败：{exc}"))

if save_clicked:
    st.session_state.selected_month = selected_month
    st.session_state.import_target_month = selected_month
    st.session_state.month_data = month_data
    payload = normalize_month_data(deepcopy(month_data))
    REPOSITORY.save_month(selected_month, payload)
    refresh_month_cache()
    page_messages.append(("success", f"已保存到 {ym_to_label(selected_month)}"))

for level, message in page_messages:
    if level == "success":
        st.success(message)
    else:
        st.error(message)

month_data = deepcopy(st.session_state.month_data)
prev_month = previous_month_key(st.session_state.selected_month)
prev_month_data = normalize_month_data(load_month_cached(prev_month)) if prev_month else None
annual_months = tuple(list_months_cached())
annual_payloads = load_annual_payloads(annual_months) if annual_months else []

cost_preview = (
    st.session_state.preview_cost
    if st.session_state.preview_cost is not None
    else display_preview_frame(build_cost_preview(month_data))
)
order_preview = (
    st.session_state.preview_order
    if st.session_state.preview_order is not None
    else display_preview_frame(build_order_preview(month_data))
)
personal_preview = (
    st.session_state.preview_personal
    if st.session_state.preview_personal is not None
    else display_preview_frame(build_personal_preview(month_data))
)
render_preview_board(cost_preview, order_preview, personal_preview)
render_month_bar(month_options, st.session_state.selected_month)

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

render_kpi_cards(kpi_cards)

overview_tab, retail_tab, delivery_tab, personnel_tab, annual_tab = st.tabs(
    ["综合概览", "零售明细", "交付明细", "人员明细", "年度汇总"]
)

with overview_tab:
    top_left, top_right = st.columns(2)
    with top_left:
        with open_card():
            render_chart_block("零售 vs 交付 固浮比对比", build_fixed_perf_chart(fixed_perf_frame))
    with top_right:
        with open_card():
            render_section_title("战区成本结构占比")
            pie_left, pie_right = st.columns(2)
            with pie_left:
                st.plotly_chart(build_business_structure_pie(business_structure_frame), width="stretch", config={"displayModeBar": False, "responsive": True})
            with pie_right:
                st.plotly_chart(build_cost_structure_pie(cost_structure_frame), width="stretch", config={"displayModeBar": False, "responsive": True})
            st.caption("零售 vs 交付 / 固定 vs 绩效")
    with open_card():
        render_table_block("战区分模块成本汇总", display_module_summary(module_summary))
    with open_card():
        render_chart_block("零售门店人工成本对比（固定 vs 绩效）", build_store_cost_chart(store_cost_frame))
    with open_card():
        render_section_title("与上月环比对比")
        if mom_frame.empty or prev_month_data is None:
            render_empty_block("暂无上月数据，导入后即可自动对比。")
        else:
            st.caption(f"对比：{ym_to_label(prev_month)}")
            st.plotly_chart(
                build_mom_chart(mom_frame, month_data.get('period') or period_label, ym_to_label(prev_month)),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
            )
            render_html_table(mom_frame)

with retail_tab:
    render_summary_cards(retail_summary_cards, 6)
    render_notice(retail_notice)
    retail_display = retail_frame.copy()
    retail_cost_display = retail_cost_frame.copy()
    if not retail_display.empty:
        with open_filter_bar():
            filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.0, 1.5, 1.2, 0.9, 0.8])
            with filter_col1:
                dept_options = ["全部", *sorted(retail_display["所属部门"].dropna().unique().tolist())]
                st.selectbox("所属部门", dept_options, key="retail_dept_filter")
            with filter_col2:
                st.multiselect("门店", sorted(retail_display["门店"].dropna().unique().tolist()), key="retail_store_filter")
            with filter_col3:
                rate_options = ["全部", "超额完成 ≥100%", "达标 85-100%", "偏低 70-85%", "未达标 <70%"]
                st.selectbox("达成状态", rate_options, key="retail_rate_filter")
            with filter_col4:
                st.button("清除筛选", key="retail_clear_filters", use_container_width=True, on_click=reset_retail_filters)
            with filter_col5:
                st.markdown(f"<div class='legacy-filter-count'>共 {len(retail_display)} 家</div>", unsafe_allow_html=True)
        retail_display = filter_retail_frame(
            retail_display,
            st.session_state.get("retail_dept_filter", "全部"),
            st.session_state.get("retail_store_filter", []),
            st.session_state.get("retail_rate_filter", "全部"),
        )
        if not retail_cost_display.empty:
            retail_cost_display = retail_cost_display[retail_cost_display["门店"].isin(retail_display["门店"].tolist())]
    retail_quadrant_frame = build_retail_quadrant_frame(retail_display)
    with open_card():
        render_table_block("零售门店综合分析", display_retail_frame(retail_display))
    with open_card():
        render_table_block("补充成本明细（含环比）", display_retail_cost_frame(retail_cost_display))
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        with open_card():
            render_chart_block("门店定单达成分析", build_retail_orders_chart(retail_display))
    with chart_col2:
        with open_card():
            render_chart_block("人均总成本分布", build_retail_cost_distribution_chart(retail_display))
    with open_card():
        render_section_title("人效 vs 人均总成本 · 四象限分析")
        if retail_quadrant_frame.empty:
            render_empty_block("暂无可用于四象限分析的门店数据")
        else:
            st.plotly_chart(build_retail_efficiency_chart(retail_quadrant_frame), width="stretch", config={"displayModeBar": False, "responsive": True})
            render_quadrant_summary(build_retail_quadrant_summary(retail_quadrant_frame))
    with open_card():
        render_table_block("零售战区级支持部门", display_support_frame(support_frame))

with delivery_tab:
    render_summary_cards(delivery_summary_cards, min(4, len(delivery_summary_cards) or 1))
    render_delivery_cards(delivery_store_frame)
    with open_card():
        render_chart_block("两大交付中心对比", build_delivery_chart(delivery_store_frame), delivery_insight)
    with open_card():
        render_table_block("交付战区级（管理人员）", analytics.display_delivery_support_frame(delivery_support_frame))

with personnel_tab:
    render_summary_cards(build_personnel_stats(personnel_frame), 4)
    personnel_display = personnel_frame.copy()
    if not personnel_display.empty:
        with open_filter_bar():
            filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.0, 1.3, 1.2, 1.0, 0.9])
            with filter_col1:
                dept_options = ["全部", *sorted(personnel_display["所属部门"].dropna().unique().tolist())]
                st.selectbox("所属部门", dept_options, key="personnel_dept_filter")
            with filter_col2:
                st.multiselect("门店", sorted(personnel_display["门店"].dropna().unique().tolist()), key="personnel_store_filter")
            with filter_col3:
                title_options = sorted([title for title in personnel_display["岗位"].dropna().unique().tolist() if title])
                st.multiselect("岗位", title_options, key="personnel_title_filter")
            with filter_col4:
                st.selectbox("排序", list(PERSONNEL_SORT_OPTIONS.keys()), index=0, key="personnel_sort_choice")
            with filter_col5:
                st.button("清除筛选", key="personnel_clear_filters", use_container_width=True, on_click=reset_personnel_filters)
        personnel_display = filter_personnel_frame(
            personnel_display,
            st.session_state.get("personnel_dept_filter", "全部"),
            st.session_state.get("personnel_store_filter", []),
            st.session_state.get("personnel_title_filter", []),
        )
    personnel_quadrant_frame = build_personnel_quadrant_frame(personnel_display)
    with open_card():
        render_section_title("个人成本 vs 定单量 四象限分析")
        if personnel_quadrant_frame.empty:
            render_empty_block("暂无可用于四象限分析的人员数据")
        else:
            st.plotly_chart(build_personnel_scatter(personnel_quadrant_frame), width="stretch", config={"displayModeBar": False, "responsive": True})
            render_quadrant_summary(build_personnel_quadrant_summary(personnel_quadrant_frame))
    sort_column, ascending = PERSONNEL_SORT_OPTIONS[st.session_state.get("personnel_sort_choice", "门店")]
    personnel_table = personnel_quadrant_frame.copy() if not personnel_quadrant_frame.empty else personnel_display.copy()
    if not personnel_table.empty:
        personnel_table = sort_personnel_frame(personnel_table, sort_column, ascending=ascending)
    with open_card():
        render_table_block("人员明细列表", display_personnel_frame(personnel_table))

with annual_tab:
    with open_card():
        render_section_title("1–12月数据汇总")
        render_annual_table(display_annual_summary(annual_frame))
    with open_card():
        render_chart_block("年度趋势", build_annual_trend_chart(annual_trend_frame))

st.markdown(
    f"<div class='legacy-footer-note'>当前月零售门店 {_safe_text(len(month_data.get('retailStores') or []))} 家，员工 {_safe_text(len(month_data.get('employees') or []))} 人，待补齐个人定单 {_safe_text(len(month_data.get('_pendingEmployeeOrders') or {}))} 人。</div>",
    unsafe_allow_html=True,
)
