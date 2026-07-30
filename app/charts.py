from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

QUADRANT_COLORS = {
    "低成本·高人效": "#00726D",
    "高成本·高人效": "#B07030",
    "低成本·低人效": "#5278A0",
    "高成本·低人效": "#DC2626",
    "低成本·高定单": "#00726D",
    "高成本·高定单": "#B07030",
    "低成本·低定单": "#5278A0",
    "高成本·低定单": "#DC2626",
}


def _empty_figure(height: int = 320) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(height=height, margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_fixed_perf_chart(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return _empty_figure(260)
    figure = go.Figure()
    figure.add_bar(x=summary["模块"], y=summary["固定成本"], name="固定成本", marker_color="#00726D")
    figure.add_bar(x=summary["模块"], y=summary["绩效成本"], name="绩效成本", marker_color="#CEA472")
    figure.update_layout(barmode="stack", height=260, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
    figure.update_yaxes(tickformat=",", title_text="成本")
    return figure


def build_business_structure_pie(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return _empty_figure(260)
    figure = px.pie(frame, names="分类", values="人工成本", color="分类", color_discrete_map={"零售": "#00726D", "交付": "#002D28"}, hole=0.45)
    figure.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", y=-0.1))
    return figure


def build_cost_structure_pie(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return _empty_figure(260)
    figure = px.pie(frame, names="分类", values="人工成本", color="分类", color_discrete_map={"固定成本": "#00726D", "绩效成本": "#CEA472"}, hole=0.45)
    figure.update_layout(height=260, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation="h", y=-0.1))
    return figure


def build_store_cost_chart(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return _empty_figure(380)
    figure = go.Figure()
    figure.add_bar(x=frame["门店"], y=frame["固定成本"], name="固定成本", marker_color="#00726D")
    figure.add_bar(x=frame["门店"], y=frame["绩效成本"], name="绩效成本", marker_color="#CEA472")
    figure.update_layout(barmode="stack", height=380, margin=dict(l=20, r=20, t=30, b=20), showlegend=True)
    figure.update_xaxes(tickangle=-35)
    return figure


def build_mom_chart(frame: pd.DataFrame, current_label: str, previous_label: str) -> go.Figure:
    if frame.empty:
        return _empty_figure(280)
    figure = go.Figure()
    figure.add_bar(x=frame["模块"], y=frame["本月"], name=current_label, marker_color="#00726D")
    figure.add_bar(x=frame["模块"], y=frame["上月"], name=previous_label, marker_color="#99C4C2")
    figure.update_layout(barmode="group", height=280, margin=dict(l=20, r=20, t=30, b=20))
    figure.update_xaxes(tickangle=-20)
    return figure


def build_retail_orders_chart(retail_frame: pd.DataFrame) -> go.Figure:
    chart_data = retail_frame.dropna(subset=["定单实际", "定单目标"]).copy()
    if chart_data.empty:
        return _empty_figure(320)
    chart_data = chart_data.sort_values("达成率", ascending=True)
    figure = go.Figure()
    figure.add_bar(
        x=chart_data["门店"],
        y=chart_data["定单实际"],
        name="实际定单",
        marker_color=["#16A34A" if rate is not None and rate >= 1 else "#00726D" for rate in chart_data["达成率"]],
    )
    figure.add_scatter(x=chart_data["门店"], y=chart_data["定单目标"], name="目标定单", mode="lines+markers", line=dict(color="#CEA472", width=2))
    figure.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20))
    figure.update_xaxes(tickangle=-35)
    return figure


def build_retail_cost_distribution_chart(retail_frame: pd.DataFrame) -> go.Figure:
    chart_data = retail_frame.dropna(subset=["人均总成本"]).copy()
    if chart_data.empty:
        return _empty_figure(320)
    average_cost = chart_data["人均总成本"].mean()
    colors = ["rgba(220,38,38,0.6)" if value > average_cost else "rgba(0,114,109,0.55)" for value in chart_data["人均总成本"]]
    figure = go.Figure(
        data=[
            go.Bar(
                x=chart_data["门店"],
                y=chart_data["人均总成本"],
                marker_color=colors,
                name="人均总成本",
            )
        ]
    )
    figure.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20), showlegend=False)
    figure.update_yaxes(tickformat=",")
    figure.update_xaxes(tickangle=-35)
    return figure


def build_retail_efficiency_chart(quadrant_frame: pd.DataFrame) -> go.Figure:
    if quadrant_frame.empty:
        return _empty_figure(420)
    figure = px.scatter(
        quadrant_frame,
        x="人均总成本",
        y="人效(单/人)",
        size="在编人数",
        color="象限",
        color_discrete_map=QUADRANT_COLORS,
        hover_name="门店",
        hover_data={"所属部门": True, "人工成本": ':.0f', "定单实际": True, "人均总成本": ':.0f', "人效(单/人)": ':.2f'},
        height=420,
    )
    med_x = float(quadrant_frame["中位成本"].iloc[0])
    med_y = float(quadrant_frame["中位人效"].iloc[0])
    figure.add_vline(x=med_x, line_dash="dash", line_color="#BBBBBB")
    figure.add_hline(y=med_y, line_dash="dash", line_color="#BBBBBB")
    figure.add_annotation(x=med_x, y=quadrant_frame["人效(单/人)"].min(), text=f"中位 {med_x / 10000:.1f}万", showarrow=False, yshift=-30)
    figure.add_annotation(x=quadrant_frame["人均总成本"].min(), y=med_y, text=f"中位 {med_y:.2f}", showarrow=False, xshift=-40)
    figure.update_layout(margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_delivery_chart(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return _empty_figure(280)
    comparison = pd.DataFrame(
        {
            "指标": ["固定成本(万)", "绩效成本(万)", "人均总成本(千)", "固定比例(%)"],
        }
    )
    figure = go.Figure()
    for index, (_, row) in enumerate(frame.iterrows()):
        figure.add_bar(
            x=comparison["指标"],
            y=[row["固定成本"] / 10000, row["绩效成本"] / 10000, (row["人均总成本"] or 0) / 1000, (row["固浮比"] or 0) * 100],
            name=row["门店"],
            marker_color=["#00726D", "#002D28"][index % 2],
        )
    figure.update_layout(barmode="group", height=280, margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_personnel_scatter(quadrant_frame: pd.DataFrame) -> go.Figure:
    if quadrant_frame.empty:
        return _empty_figure(420)
    figure = px.scatter(
        quadrant_frame,
        x="个人成本",
        y="个人定单量",
        color="象限",
        color_discrete_map=QUADRANT_COLORS,
        hover_name="姓名",
        hover_data={"岗位": True, "门店": True, "所属部门": True, "个人成本": ':.0f', "个人定单量": True},
        height=420,
    )
    med_x = float(quadrant_frame["中位个人成本"].iloc[0])
    med_y = float(quadrant_frame["中位个人定单量"].iloc[0])
    figure.add_vline(x=med_x, line_dash="dash", line_color="#BBBBBB")
    figure.add_hline(y=med_y, line_dash="dash", line_color="#BBBBBB")
    figure.add_annotation(x=med_x, y=quadrant_frame["个人定单量"].min(), text=f"中位 {med_x:,.0f}元", showarrow=False, yshift=-30)
    figure.add_annotation(x=quadrant_frame["个人成本"].min(), y=med_y, text=f"中位 {med_y:.0f}单", showarrow=False, xshift=-40)
    figure.update_layout(margin=dict(l=20, r=20, t=30, b=20))
    return figure


def build_annual_trend_chart(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        return _empty_figure(360)
    figure = go.Figure()
    figure.add_scatter(x=frame["月份"], y=frame["战区总人工成本（万）"], mode="lines+markers", name="战区总人工成本（万）", line=dict(color="#002D28", width=3))
    figure.add_scatter(x=frame["月份"], y=frame["零售总成本（万）"], mode="lines+markers", name="零售总成本（万）", line=dict(color="#00726D", width=2))
    figure.add_scatter(x=frame["月份"], y=frame["交付总成本（万）"], mode="lines+markers", name="交付总成本（万）", line=dict(color="#CEA472", width=2))
    figure.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20))
    return figure
