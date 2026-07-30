from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


THEME = {
    "零售门店": "#00726D",
    "零售支持": "#6AA84F",
    "交付门店": "#C9A227",
    "交付支持": "#B45F06",
    "战区合计": "#1F2937",
}


def build_module_cost_chart(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return go.Figure()
    chart_data = summary[summary["模块"] != "战区合计"].copy()
    figure = go.Figure()
    figure.add_bar(
        x=chart_data["模块"],
        y=chart_data["固定成本"],
        name="固定成本",
        marker_color="#0F766E",
    )
    figure.add_bar(
        x=chart_data["模块"],
        y=chart_data["绩效成本"],
        name="绩效成本",
        marker_color="#D4A017",
    )
    figure.update_layout(barmode="stack", height=360, margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_retail_orders_chart(retail_frame: pd.DataFrame) -> go.Figure:
    chart_data = retail_frame.dropna(subset=["定单量", "定单目标"]).copy()
    if chart_data.empty:
        return go.Figure()
    chart_data = chart_data.sort_values("定单量", ascending=False).head(15)
    figure = go.Figure()
    figure.add_bar(x=chart_data["门店"], y=chart_data["定单量"], name="实际", marker_color="#00726D")
    figure.add_bar(x=chart_data["门店"], y=chart_data["定单目标"], name="目标", marker_color="#C9A227")
    figure.update_layout(barmode="group", height=380, margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_retail_efficiency_chart(retail_frame: pd.DataFrame) -> go.Figure:
    chart_data = retail_frame.dropna(subset=["人均总成本", "人效"]).copy()
    if chart_data.empty:
        return go.Figure()
    figure = px.scatter(
        chart_data,
        x="人均总成本",
        y="人效",
        size="定单量",
        color="所属部门",
        hover_name="门店",
        hover_data={"人工成本": True, "在编人数": True, "定单量": True, "人均总成本": ':.0f', "人效": ':.2f'},
        height=420,
    )
    figure.update_layout(margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_personnel_scatter(personnel_frame: pd.DataFrame) -> go.Figure:
    chart_data = personnel_frame.dropna(subset=["个人成本", "个人定单量"]).copy()
    if chart_data.empty:
        return go.Figure()
    figure = px.scatter(
        chart_data,
        x="个人成本",
        y="个人定单量",
        color="所属部门",
        hover_name="姓名",
        hover_data={"岗位": True, "门店": True, "个人成本": ':.0f', "个人定单量": True},
        height=420,
    )
    figure.update_layout(margin=dict(l=20, r=20, t=30, b=20))
    return figure
