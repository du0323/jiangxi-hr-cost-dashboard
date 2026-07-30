from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

ALLOWED_PERSONNEL_TITLES = ["产品专家", "产品专员", "储备管理", "高级产品专家", "资深产品专家", "零售主管"]


def current_month_key(today: date | None = None) -> str:
    current = today or date.today()
    return f"{current.year}-{current.month:02d}"


def previous_month_key(ym: str) -> str | None:
    if not ym or "-" not in ym:
        return None
    year_text, month_text = ym.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    month -= 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}-{month:02d}"


def ym_to_label(ym: str) -> str:
    if not ym:
        return ""
    year, month = ym.split("-", 1)
    return f"{year}年{int(month)}月"


def empty_month(period: str) -> dict[str, Any]:
    return {
        "period": period,
        "retailStores": [],
        "supportDepts": [],
        "deliveryStores": [],
        "deliverySupport": [],
        "employees": [],
    }


def _is_missing(value: Any) -> bool:
    return value is None or pd.isna(value)


def format_number(value: float | int | None) -> str:
    if _is_missing(value):
        return "—"
    return f"{int(round(float(value))):,}"


def format_wan(value: float | int | None, digits: int = 1) -> str:
    if _is_missing(value):
        return "—"
    return f"{float(value) / 10000:.{digits}f}"


def format_percent(value: float | None, digits: int = 1) -> str:
    if _is_missing(value):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def format_delta_percent(current: float | int | None, previous: float | int | None, digits: int = 1) -> str | None:
    if _is_missing(current) or _is_missing(previous) or float(previous) == 0:
        return None
    delta = (float(current) - float(previous)) / float(previous)
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta * 100:.{digits}f}%"


def format_change_text(current: float | int | None, previous: float | int | None, digits: int = 1) -> str:
    if _is_missing(current) or _is_missing(previous) or float(previous) == 0:
        return "—"
    delta = (float(current) - float(previous)) / float(previous)
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta * 100:.{digits}f}%"


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _sum(items: list[dict[str, Any]], field: str) -> float:
    return float(sum(_float(item.get(field)) for item in items))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2)


def _rate_bucket(rate: float | None) -> str:
    if rate is None:
        return "暂无定单"
    if rate >= 1:
        return "超额完成 ≥100%"
    if rate >= 0.85:
        return "达标 85-100%"
    if rate >= 0.70:
        return "偏低 70-85%"
    return "未达标 <70%"


def _retail_groups(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    retail_stores = data.get("retailStores") or []
    support_depts = data.get("supportDepts") or []
    delivery_stores = data.get("deliveryStores") or []
    delivery_support = data.get("deliverySupport") or []
    return retail_stores, support_depts, delivery_stores, delivery_support


def compute_kpis(data: dict[str, Any]) -> dict[str, float | int | None]:
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    all_retail = [*retail_stores, *support_depts]
    all_delivery = [*delivery_stores, *delivery_support]
    all_units = [*all_retail, *all_delivery]

    total_labor = _sum(all_units, "labor")
    total_count = int(_sum(all_units, "count"))
    total_fixed = _sum(all_units, "fixed")
    retail_labor = _sum(all_retail, "labor")
    retail_count = int(_sum(all_retail, "count"))
    delivery_labor = _sum(all_delivery, "labor")
    delivery_count = int(_sum(all_delivery, "count"))
    total_actual = int(sum(_int(store.get("orders_actual")) for store in retail_stores if store.get("orders_actual") is not None))
    total_target = int(sum(_int(store.get("orders_target")) for store in retail_stores if store.get("orders_target") is not None))
    fixed_ratio = total_fixed / total_labor if total_labor else None
    order_rate = total_actual / total_target if total_target else None
    retail_avg_cost = retail_labor / retail_count if retail_count else None
    store_count = int(sum(_int(store.get("count")) for store in retail_stores if _int(store.get("count")) > 0))
    human_efficiency = total_actual / store_count if store_count else None

    return {
        "total_labor": total_labor,
        "total_count": total_count,
        "fixed_ratio": fixed_ratio,
        "order_rate": order_rate,
        "retail_avg_cost": retail_avg_cost,
        "retail_human_efficiency": human_efficiency,
        "delivery_total": data.get("deliveryTotal"),
        "retail_labor": retail_labor,
        "retail_count": retail_count,
        "delivery_labor": delivery_labor,
        "delivery_count": delivery_count,
        "total_actual": total_actual,
        "total_target": total_target,
    }


def build_kpi_cards(data: dict[str, Any], prev_data: dict[str, Any] | None = None) -> list[dict[str, str | None]]:
    current = compute_kpis(data)
    previous = compute_kpis(prev_data or {}) if prev_data else {}
    fixed_ratio = current["fixed_ratio"]
    fixed_ratio_badge = "合理"
    if fixed_ratio is not None and fixed_ratio > 0.70:
        fixed_ratio_badge = "固定偏高"
    elif fixed_ratio is not None and fixed_ratio > 0.60:
        fixed_ratio_badge = "偏高"

    return [
        {
            "label": "战区总人工成本",
            "value": f"{format_wan(current['total_labor'])} 万",
            "delta": format_delta_percent(current["total_labor"], previous.get("total_labor")),
            "delta_color": "inverse",
            "help": f"零售 {format_wan(current['retail_labor'])}万 / 交付 {format_wan(current['delivery_labor'])}万",
        },
        {
            "label": "战区在编人数",
            "value": str(current["total_count"]),
            "delta": format_delta_percent(current["total_count"], previous.get("total_count")),
            "delta_color": "normal",
            "help": f"零售 {current['retail_count']}人 / 交付 {current['delivery_count']}人",
        },
        {
            "label": "战区固浮比（固定:绩效）",
            "value": format_percent(current["fixed_ratio"]),
            "delta": format_delta_percent(current["fixed_ratio"], previous.get("fixed_ratio")),
            "delta_color": "inverse",
            "help": f"基准40:60 · {fixed_ratio_badge}",
        },
        {
            "label": "零售定单达成",
            "value": format_percent(current["order_rate"]),
            "delta": format_delta_percent(current["order_rate"], previous.get("order_rate")),
            "delta_color": "normal",
            "help": f"实际 {current['total_actual']}单 / 目标 {current['total_target']}单",
        },
        {
            "label": "零售人均总成本",
            "value": "—" if current["retail_avg_cost"] is None else f"{current['retail_avg_cost'] / 10000:.2f} 万/人",
            "delta": format_delta_percent(current["retail_avg_cost"], previous.get("retail_avg_cost")),
            "delta_color": "inverse",
            "help": "—"
            if current["retail_human_efficiency"] is None
            else f"零售人效 {current['retail_human_efficiency']:.2f}单/人（店端）",
        },
    ]


def build_module_summary(data: dict[str, Any], prev_data: dict[str, Any] | None = None, zone_name: str = "战区") -> pd.DataFrame:
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    prev_retail, prev_support, prev_delivery, prev_delivery_support = _retail_groups(prev_data or {})

    retail_depts = sorted({str(store.get("dept") or "").strip() for store in retail_stores if str(store.get("dept") or "").strip()})
    rows: list[dict[str, Any]] = []

    def add_row(label: str, items: list[dict[str, Any]], prev_items: list[dict[str, Any]], indent: int = 0) -> None:
        labor = _sum(items, "labor")
        fixed = _sum(items, "fixed")
        perf = _sum(items, "perf")
        count = int(_sum(items, "count"))
        prev_labor = _sum(prev_items, "labor") if prev_items else None
        rows.append(
            {
                "模块": label,
                "缩进": indent,
                "人数": count,
                "本月人工成本": labor,
                "上月人工成本": prev_labor,
                "环比": format_change_text(labor, prev_labor),
                "固定成本": fixed,
                "绩效成本": perf,
                "固浮比": fixed / labor if labor else None,
                "人均总成本": labor / count if count else None,
            }
        )

    retail_all = [*retail_stores, *support_depts]
    prev_retail_all = [*prev_retail, *prev_support]
    delivery_all = [*delivery_stores, *delivery_support]
    prev_delivery_all = [*prev_delivery, *prev_delivery_support]

    add_row("🏪 零售（含战区级）", retail_all, prev_retail_all)
    for dept in retail_depts:
        add_row(
            f"{dept}（门店）",
            [item for item in retail_stores if str(item.get("dept") or "").strip() == dept],
            [item for item in prev_retail if str(item.get("dept") or "").strip() == dept],
            1,
        )
    add_row("零售战区支持", support_depts, prev_support, 1)
    add_row("🚗 交付（含战区级）", delivery_all, prev_delivery_all)
    add_row("交付门店", delivery_stores, prev_delivery, 1)
    add_row("交付战区支持", delivery_support, prev_delivery_support, 1)
    add_row(f"📊 {zone_name}合计", [*retail_all, *delivery_all], [*prev_retail_all, *prev_delivery_all])

    return pd.DataFrame(rows)


def build_fixed_perf_frame(data: dict[str, Any]) -> pd.DataFrame:
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    retail_all = [*retail_stores, *support_depts]
    delivery_all = [*delivery_stores, *delivery_support]
    rows = [
        {"模块": "零售（含战区级）", "固定成本": _sum(retail_all, "fixed"), "绩效成本": _sum(retail_all, "perf")},
        {"模块": "交付（含战区级）", "固定成本": _sum(delivery_all, "fixed"), "绩效成本": _sum(delivery_all, "perf")},
        {
            "模块": "战区合计",
            "固定成本": _sum([*retail_all, *delivery_all], "fixed"),
            "绩效成本": _sum([*retail_all, *delivery_all], "perf"),
        },
    ]
    return pd.DataFrame(rows)


def build_business_structure_frame(data: dict[str, Any]) -> pd.DataFrame:
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    retail_all = [*retail_stores, *support_depts]
    delivery_all = [*delivery_stores, *delivery_support]
    return pd.DataFrame(
        [
            {"分类": "零售", "人工成本": _sum(retail_all, "labor")},
            {"分类": "交付", "人工成本": _sum(delivery_all, "labor")},
        ]
    )


def build_cost_structure_frame(data: dict[str, Any]) -> pd.DataFrame:
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    all_units = [*retail_stores, *support_depts, *delivery_stores, *delivery_support]
    return pd.DataFrame(
        [
            {"分类": "固定成本", "人工成本": _sum(all_units, "fixed")},
            {"分类": "绩效成本", "人工成本": _sum(all_units, "perf")},
        ]
    )


def build_store_cost_frame(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for store in data.get("retailStores") or []:
        rows.append(
            {
                "门店": str(store.get("name") or "").replace("零售中心", "").replace("（外展店）", "[外展]"),
                "固定成本": _float(store.get("fixed")),
                "绩效成本": _float(store.get("perf")),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("固定成本", ascending=False)


def build_mom_comparison_frame(data: dict[str, Any], prev_data: dict[str, Any] | None = None) -> pd.DataFrame:
    if not prev_data:
        return pd.DataFrame(columns=["模块", "本月", "上月", "环比", "差值"])
    retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
    prev_retail, prev_support, prev_delivery, prev_delivery_support = _retail_groups(prev_data)
    retail_depts = sorted({str(store.get("dept") or "").strip() for store in retail_stores if str(store.get("dept") or "").strip()})
    labels: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for dept in retail_depts[:2]:
        labels.append(
            (
                f"{dept}（门店）",
                [item for item in retail_stores if str(item.get('dept') or '').strip() == dept],
                [item for item in prev_retail if str(item.get('dept') or '').strip() == dept],
            )
        )
    labels.extend(
        [
            ("零售战区支持", support_depts, prev_support),
            ("交付门店", delivery_stores, prev_delivery),
            ("交付战区支持", delivery_support, prev_delivery_support),
        ]
    )
    rows = []
    for label, current_items, previous_items in labels:
        current_value = _sum(current_items, "labor")
        previous_value = _sum(previous_items, "labor")
        rows.append(
            {
                "模块": label,
                "本月": current_value,
                "上月": previous_value,
                "环比": format_change_text(current_value, previous_value),
                "差值": current_value - previous_value,
            }
        )
    return pd.DataFrame(rows)


def build_retail_summary_cards(data: dict[str, Any]) -> list[dict[str, str]]:
    retail_stores, support_depts, _, _ = _retail_groups(data)
    retail_all = [*retail_stores, *support_depts]
    labor = _sum(retail_all, "labor")
    fixed = _sum(retail_all, "fixed")
    perf = _sum(retail_all, "perf")
    count = int(_sum(retail_all, "count"))
    actual = int(sum(_int(store.get("orders_actual")) for store in retail_stores if store.get("orders_actual") is not None))
    target = int(sum(_int(store.get("orders_target")) for store in retail_stores if store.get("orders_target") is not None))
    rate = actual / target if target else None
    return [
        {"label": "零售总人工成本", "value": f"{format_wan(labor)} 万"},
        {"label": "零售总固定成本", "value": f"{format_wan(fixed)} 万"},
        {"label": "零售总绩效成本", "value": f"{format_wan(perf)} 万"},
        {"label": "零售在编人数", "value": f"{count} 人"},
        {"label": "实际定单", "value": f"{actual} 单"},
        {"label": "定单达成率", "value": format_percent(rate)},
    ]


def build_retail_notice(data: dict[str, Any]) -> str:
    retail_stores = data.get("retailStores") or []
    missing_orders = [store for store in retail_stores if store.get("orders_actual") is None]
    notice = f"数据说明：共 {len(retail_stores)} 家门店有成本数据"
    if missing_orders:
        notice += f"；其中 {len(missing_orders)} 家暂无定单数据"
    return notice


def build_retail_frame(data: dict[str, Any], prev_data: dict[str, Any] | None = None) -> pd.DataFrame:
    prev_map = {str(store.get("name") or ""): store for store in (prev_data or {}).get("retailStores") or []}
    rows = []
    for store in data.get("retailStores") or []:
        labor = _float(store.get("labor"))
        fixed = _float(store.get("fixed"))
        perf = _float(store.get("perf"))
        count = _int(store.get("count"))
        actual = store.get("orders_actual")
        target = store.get("orders_target")
        prev_store = prev_map.get(str(store.get("name") or ""))
        prev_labor = _float(prev_store.get("labor")) if prev_store else None
        rate = (_int(actual) / _int(target)) if actual is not None and target not in (None, 0) else None
        avg_total = labor / count if count else None
        human_eff = (_int(actual) / count) if actual is not None and count else None
        rows.append(
            {
                "门店": store.get("name") or "",
                "所属部门": store.get("dept") or "",
                "在编人数": count,
                "实习生人数": _int(store.get("intern_count")),
                "人数": f"{count} (+{_int(store.get('intern_count'))}习)" if _int(store.get("intern_count")) else str(count),
                "人工成本": labor,
                "上月成本": prev_labor,
                "环比": format_change_text(labor, prev_labor),
                "固定成本": fixed,
                "绩效成本": perf,
                "固浮比": fixed / labor if labor else None,
                "人均固定成本": fixed / count if count else None,
                "人均变动成本": perf / count if count else None,
                "定单实际": _int(actual) if actual is not None else None,
                "定单目标": _int(target) if target is not None else None,
                "达成率": rate,
                "人均总成本": avg_total,
                "人效(单/人)": human_eff,
                "人力CPS": (labor / _int(actual)) if actual not in (None, 0) else None,
                "达成状态": _rate_bucket(rate),
                "法定加班": _float(store.get("overtime_legal")),
                "出差津贴": _float(store.get("travel")),
                "社保公积金(企)": _float(store.get("social")),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["所属部门", "人工成本"], ascending=[True, False]).reset_index(drop=True)


def filter_retail_frame(frame: pd.DataFrame, dept: str = "全部", stores: list[str] | None = None, rate_status: str = "全部") -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = frame.copy()
    if dept and dept != "全部":
        filtered = filtered[filtered["所属部门"] == dept]
    if stores:
        filtered = filtered[filtered["门店"].isin(stores)]
    if rate_status and rate_status != "全部":
        filtered = filtered[filtered["达成状态"] == rate_status]
    return filtered.reset_index(drop=True)


def add_retail_total_row(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if len(frame) == 1:
        return frame
    total_labor = frame["人工成本"].sum()
    total_fixed = frame["固定成本"].sum()
    total_perf = frame["绩效成本"].sum()
    total_count = int(frame["在编人数"].sum())
    total_intern = int(frame["实习生人数"].sum())
    total_actual = int(frame["定单实际"].fillna(0).sum())
    total_target = int(frame["定单目标"].fillna(0).sum())
    total_row = pd.DataFrame(
        [
            {
                "门店": f"筛选合计（{len(frame)}家）",
                "所属部门": "",
                "在编人数": total_count,
                "实习生人数": total_intern,
                "人数": f"{total_count} (+{total_intern}习)" if total_intern else str(total_count),
                "人工成本": total_labor,
                "上月成本": None,
                "环比": "—",
                "固定成本": total_fixed,
                "绩效成本": total_perf,
                "固浮比": total_fixed / total_labor if total_labor else None,
                "人均固定成本": total_fixed / total_count if total_count else None,
                "人均变动成本": total_perf / total_count if total_count else None,
                "定单实际": total_actual,
                "定单目标": total_target,
                "达成率": (total_actual / total_target) if total_target else None,
                "人均总成本": total_labor / total_count if total_count else None,
                "人效(单/人)": (total_actual / total_count) if total_count and total_actual else None,
                "人力CPS": (total_labor / total_actual) if total_actual else None,
                "达成状态": "—",
                "法定加班": frame["法定加班"].sum(),
                "出差津贴": frame["出差津贴"].sum(),
                "社保公积金(企)": frame["社保公积金(企)"].sum(),
            }
        ]
    )
    return pd.concat([frame, total_row], ignore_index=True)


def build_retail_cost_frame(data: dict[str, Any], prev_data: dict[str, Any] | None = None) -> pd.DataFrame:
    prev_map = {str(store.get("name") or ""): store for store in (prev_data or {}).get("retailStores") or []}
    rows = []
    for store in data.get("retailStores") or []:
        prev_store = prev_map.get(str(store.get("name") or ""))
        overtime = _float(store.get("overtime_legal"))
        travel = _float(store.get("travel"))
        social = _float(store.get("social"))
        prev_overtime = _float(prev_store.get("overtime_legal")) if prev_store else None
        prev_travel = _float(prev_store.get("travel")) if prev_store else None
        prev_social = _float(prev_store.get("social")) if prev_store else None
        rows.append(
            {
                "门店": store.get("name") or "",
                "所属部门": store.get("dept") or "",
                "人数": f"{_int(store.get('count'))} (+{_int(store.get('intern_count'))}习)" if _int(store.get("intern_count")) else str(_int(store.get("count"))),
                "法定加班": overtime,
                "上月法定加班": prev_overtime,
                "法定加班环比": format_change_text(overtime, prev_overtime),
                "出差津贴": travel,
                "上月出差津贴": prev_travel,
                "出差津贴环比": format_change_text(travel, prev_travel),
                "社保公积金(企)": social,
                "上月社保": prev_social,
                "社保环比": format_change_text(social, prev_social),
            }
        )
    return pd.DataFrame(rows)


def add_retail_cost_total_row(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    if len(frame) == 1:
        return frame
    total_row = pd.DataFrame(
        [
            {
                "门店": f"筛选合计（{len(frame)}家）",
                "所属部门": "",
                "人数": "—",
                "法定加班": frame["法定加班"].sum(),
                "上月法定加班": None,
                "法定加班环比": "—",
                "出差津贴": frame["出差津贴"].sum(),
                "上月出差津贴": None,
                "出差津贴环比": "—",
                "社保公积金(企)": frame["社保公积金(企)"].sum(),
                "上月社保": None,
                "社保环比": "—",
            }
        ]
    )
    return pd.concat([frame, total_row], ignore_index=True)


def build_retail_quadrant_frame(retail_frame: pd.DataFrame) -> pd.DataFrame:
    if retail_frame.empty:
        return pd.DataFrame()
    frame = retail_frame.dropna(subset=["人均总成本", "人效(单/人)"]).copy()
    if frame.empty:
        return frame
    med_x = _median(frame["人均总成本"].tolist())
    med_y = _median(frame["人效(单/人)"].tolist())
    labels = {
        1: "低成本·高人效",
        2: "高成本·高人效",
        3: "低成本·低人效",
        4: "高成本·低人效",
    }
    quadrants = []
    for _, row in frame.iterrows():
        hi_cost = _float(row["人均总成本"]) > med_x
        hi_eff = _float(row["人效(单/人)"]) > med_y
        quadrant = 2 if hi_cost and hi_eff else 4 if hi_cost else 1 if hi_eff else 3
        quadrants.append(quadrant)
    frame["象限编号"] = quadrants
    frame["象限"] = [labels[number] for number in quadrants]
    frame["中位成本"] = med_x
    frame["中位人效"] = med_y
    return frame


def build_retail_quadrant_summary(quadrant_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if quadrant_frame.empty:
        return []
    definitions = {
        1: ("⭐", "低成本·高人效", "成本控制好且人效突出，是当前的标杆门店，可作为经验推广参考。"),
        2: ("📈", "高成本·高人效", "人效表现出色但成本偏高，建议深挖成本结构，优化固浮比或人员配置。"),
        3: ("⚡", "低成本·低人效", "成本可控，但单量产出不足，建议聚焦订单获取能力及员工激励机制。"),
        4: ("⚠️", "高成本·低人效", "高投入低产出，需重点排查人员结构及运营效率，优先制定改善方案。"),
    }
    items = []
    for quadrant in [1, 2, 3, 4]:
        icon, title, description = definitions[quadrant]
        stores = quadrant_frame[quadrant_frame["象限编号"] == quadrant]["门店"].tolist()
        items.append({"icon": icon, "title": title, "description": description, "count": len(stores), "items": stores})
    return items


def build_support_frame(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in data.get("supportDepts") or []:
        labor = _float(item.get("labor"))
        count = _int(item.get("count"))
        rows.append(
            {
                "部门": item.get("name") or "",
                "人数": count,
                "人工成本": labor,
                "固定成本": _float(item.get("fixed")),
                "绩效成本": _float(item.get("perf")),
                "固浮比": (_float(item.get("fixed")) / labor) if labor else None,
                "人均总成本": labor / count if count else None,
            }
        )
    return pd.DataFrame(rows)


def build_delivery_summary_cards(data: dict[str, Any]) -> list[dict[str, str]]:
    delivery_stores = data.get("deliveryStores") or []
    labor = _sum(delivery_stores, "labor")
    fixed = _sum(delivery_stores, "fixed")
    perf = _sum(delivery_stores, "perf")
    count = int(_sum(delivery_stores, "count"))
    cards = [
        {"label": "交付总人工成本", "value": f"{format_wan(labor)} 万"},
        {"label": "交付总固定成本", "value": f"{format_wan(fixed)} 万"},
        {"label": "交付总绩效成本", "value": f"{format_wan(perf)} 万"},
        {"label": "交付在编人数", "value": f"{count} 人"},
    ]
    if data.get("deliveryTotal") is not None:
        cards.append({"label": "总交付量", "value": f"{_int(data.get('deliveryTotal'))} 单"})
    return cards


def build_delivery_store_frame(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for store in data.get("deliveryStores") or []:
        labor = _float(store.get("labor"))
        count = _int(store.get("count"))
        fixed = _float(store.get("fixed"))
        perf = _float(store.get("perf"))
        rows.append(
            {
                "门店": store.get("name") or "",
                "在编人数": count,
                "人工成本": labor,
                "固定成本": fixed,
                "绩效成本": perf,
                "法定加班费": _float(store.get("overtime_legal")),
                "出差津贴": _float(store.get("travel")),
                "社保公积金（企业）": _float(store.get("social")),
                "人均总成本": labor / count if count else None,
                "人均固定成本": fixed / count if count else None,
                "人均绩效成本": perf / count if count else None,
                "固浮比": fixed / labor if labor else None,
            }
        )
    return pd.DataFrame(rows)


def build_delivery_insight(frame: pd.DataFrame) -> str:
    if frame.empty or len(frame) < 2:
        return "暂无足够交付门店数据生成对比洞察。"
    first = frame.iloc[0]
    second = frame.iloc[1]
    avg_first = _float(first["人均总成本"])
    avg_second = _float(second["人均总成本"])
    ratio_first = _float(first["固浮比"])
    ratio_second = _float(second["固浮比"])
    higher_cost = second["门店"] if avg_second > avg_first else first["门店"]
    lower_cost = first["门店"] if higher_cost == second["门店"] else second["门店"]
    higher_perf = second["门店"] if (1 - ratio_second) > (1 - ratio_first) else first["门店"]
    return (
        f"{higher_cost} 人均成本更高，{lower_cost} 相对更低；"
        f"{higher_perf} 的绩效占比更高，激励导向更强。"
    )


def build_delivery_support_frame(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for item in data.get("deliverySupport") or []:
        labor = _float(item.get("labor"))
        count = _int(item.get("count"))
        rows.append(
            {
                "类别": item.get("name") or "",
                "人数": count,
                "人工成本": labor,
                "固定成本": _float(item.get("fixed")),
                "绩效成本": _float(item.get("perf")),
                "固浮比": (_float(item.get("fixed")) / labor) if labor else None,
                "人均总成本": labor / count if count else None,
            }
        )
    return pd.DataFrame(rows)


def build_personnel_frame(data: dict[str, Any], exclude_interns: bool = True) -> pd.DataFrame:
    rows = []
    for employee in data.get("employees") or []:
        if exclude_interns and employee.get("isIntern") is True:
            continue
        rows.append(
            {
                "工号": employee.get("id") or "",
                "姓名": employee.get("name") or "",
                "岗位": employee.get("title") or "",
                "门店": employee.get("store") or "",
                "所属部门": employee.get("dept") or "",
                "分类": employee.get("cat") or "",
                "个人成本": _float(employee.get("labor")),
                "个人定单量": _int(employee.get("orders")) if employee.get("orders") is not None else 0,
                "有定单": employee.get("orders") is not None and _int(employee.get("orders")) > 0,
            }
        )
    return pd.DataFrame(rows)


def filter_personnel_frame(
    frame: pd.DataFrame,
    dept: str = "全部",
    stores: list[str] | None = None,
    titles: list[str] | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    filtered = frame.copy()
    filtered = filtered[filtered["姓名"].astype(str).str.strip() != ""]
    if dept and dept != "全部":
        filtered = filtered[filtered["所属部门"] == dept]
    if stores:
        filtered = filtered[filtered["门店"].isin(stores)]
    if titles:
        filtered = filtered[filtered["岗位"].isin(titles)]
    elif filtered["岗位"].astype(str).str.strip().any():
        filtered = filtered[filtered["岗位"].isin(ALLOWED_PERSONNEL_TITLES)]
    return filtered.reset_index(drop=True)


def build_personnel_stats(frame: pd.DataFrame) -> list[dict[str, str]]:
    if frame.empty:
        return [
            {"label": "分析人数", "value": "0 人"},
            {"label": "有定单人数", "value": "0 人"},
            {"label": "人均成本", "value": "—"},
            {"label": "人均定单", "value": "—"},
        ]
    total_people = len(frame)
    with_orders = int(frame[frame["有定单"]].shape[0])
    avg_cost = frame["个人成本"].mean() if total_people else None
    avg_orders = frame[frame["有定单"]]["个人定单量"].mean() if with_orders else None
    return [
        {"label": "分析人数", "value": f"{total_people} 人"},
        {"label": "有定单人数", "value": f"{with_orders} 人"},
        {"label": "人均成本", "value": "—" if avg_cost is None else f"{format_number(avg_cost)} 元"},
        {"label": "人均定单", "value": "—" if avg_orders is None else f"{avg_orders:.1f} 单"},
    ]


def build_personnel_quadrant_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    valid = frame.copy()
    valid = valid[valid["个人成本"] > 0]
    if valid.empty:
        return valid
    med_x = _median(valid["个人成本"].tolist())
    med_y = _median(valid["个人定单量"].tolist())
    labels = {
        1: "低成本·高定单",
        2: "高成本·高定单",
        3: "低成本·低定单",
        4: "高成本·低定单",
    }
    quadrants = []
    for _, row in valid.iterrows():
        hi_cost = _float(row["个人成本"]) > med_x
        hi_orders = _float(row["个人定单量"]) > med_y
        quadrant = 2 if hi_cost and hi_orders else 4 if hi_cost else 1 if hi_orders else 3
        quadrants.append(quadrant)
    valid["象限编号"] = quadrants
    valid["象限"] = [labels[number] for number in quadrants]
    valid["中位个人成本"] = med_x
    valid["中位个人定单量"] = med_y
    return valid


def build_personnel_quadrant_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    definitions = {
        1: ("⭐", "优秀员工 · 低成本高定单", "成本控制好且产出突出，是当前的标杆员工，可作经验推广。"),
        2: ("📈", "核心骨干 · 高成本高定单", "产出出色但成本偏高，建议深挖成本结构，优化薪酬配置。"),
        3: ("⚡", "潜力新人 · 低成本低定单", "成本可控但单量不足，建议加强培训和订单获取能力。"),
        4: ("⚠️", "需关注 · 高成本低定单", "高投入低产出，需重点排查，优先制定改善或汰换方案。"),
    }
    items = []
    for quadrant in [1, 2, 3, 4]:
        icon, title, description = definitions[quadrant]
        people = frame[frame["象限编号"] == quadrant]
        labels = [f"{row['姓名']}({int(row['个人定单量'])}单/{format_number(row['个人成本'])}元)" for _, row in people.iterrows()]
        items.append({"icon": icon, "title": title, "description": description, "count": len(labels), "items": labels})
    return items


def sort_personnel_frame(frame: pd.DataFrame, sort_by: str = "门店", ascending: bool = True) -> pd.DataFrame:
    if frame.empty or sort_by not in frame.columns:
        return frame
    return frame.sort_values(sort_by, ascending=ascending).reset_index(drop=True)


def build_annual_summary(month_payloads: list[tuple[str, dict[str, Any]]]) -> pd.DataFrame:
    rows = []
    for ym, data in sorted(month_payloads, key=lambda item: item[0]):
        retail_stores, support_depts, delivery_stores, delivery_support = _retail_groups(data)
        all_units = [*retail_stores, *support_depts, *delivery_stores, *delivery_support]
        retail_all = [*retail_stores, *support_depts]
        delivery_all = [*delivery_stores, *delivery_support]
        retail_orders = int(sum(_int(store.get("orders_actual")) for store in retail_stores if store.get("orders_actual") is not None))
        delivery_orders = _int(data.get("deliveryTotal")) if data.get("deliveryTotal") is not None else int(sum(_int(store.get("orders_actual")) for store in delivery_stores if store.get("orders_actual") is not None))
        overall_count = int(_sum(all_units, "count"))
        retail_count = int(_sum(retail_all, "count"))
        delivery_count = int(_sum(delivery_all, "count"))
        rows.append(
            {
                "月份": data.get("period") or ym_to_label(ym),
                "年月": ym,
                "战区总人工成本（万）": _sum(all_units, "labor") / 10000,
                "战区固定（万）": _sum(all_units, "fixed") / 10000,
                "战区绩效（万）": _sum(all_units, "perf") / 10000,
                "战区人数": overall_count,
                "零售总成本（万）": _sum(retail_all, "labor") / 10000,
                "零售固定（万）": _sum(retail_all, "fixed") / 10000,
                "零售绩效（万）": _sum(retail_all, "perf") / 10000,
                "零售人数": retail_count,
                "零售总定单量": retail_orders,
                "零售人效（单/人）": (retail_orders / retail_count) if retail_count else None,
                "交付总成本（万）": _sum(delivery_all, "labor") / 10000,
                "交付固定（万）": _sum(delivery_all, "fixed") / 10000,
                "交付绩效（万）": _sum(delivery_all, "perf") / 10000,
                "交付人数": delivery_count,
                "总交付量": delivery_orders,
                "交付人效（单/人）": (delivery_orders / delivery_count) if delivery_count else None,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    total_row = pd.DataFrame(
        [
            {
                "月份": "累计合计",
                "年月": "9999-12",
                "战区总人工成本（万）": frame["战区总人工成本（万）"].sum(),
                "战区固定（万）": frame["战区固定（万）"].sum(),
                "战区绩效（万）": frame["战区绩效（万）"].sum(),
                "战区人数": None,
                "零售总成本（万）": frame["零售总成本（万）"].sum(),
                "零售固定（万）": frame["零售固定（万）"].sum(),
                "零售绩效（万）": frame["零售绩效（万）"].sum(),
                "零售人数": None,
                "零售总定单量": int(frame["零售总定单量"].fillna(0).sum()),
                "零售人效（单/人）": None,
                "交付总成本（万）": frame["交付总成本（万）"].sum(),
                "交付固定（万）": frame["交付固定（万）"].sum(),
                "交付绩效（万）": frame["交付绩效（万）"].sum(),
                "交付人数": None,
                "总交付量": int(frame["总交付量"].fillna(0).sum()),
                "交付人效（单/人）": None,
            }
        ]
    )
    return pd.concat([frame, total_row], ignore_index=True)


def build_annual_trend_frame(annual_frame: pd.DataFrame) -> pd.DataFrame:
    if annual_frame.empty:
        return annual_frame
    frame = annual_frame[annual_frame["月份"] != "累计合计"].copy()
    return frame[["月份", "战区总人工成本（万）", "零售总成本（万）", "交付总成本（万）", "零售总定单量", "总交付量"]]


def build_cost_preview(data: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "工号": employee.get("id") or "—",
            "姓名": employee.get("name") or "—",
            "部门": employee.get("dept") or employee.get("cat") or "—",
            "门店": employee.get("store") or "—",
            "人工成本": employee.get("labor") or 0,
        }
        for employee in (data.get("employees") or [])[:50]
    ]
    return pd.DataFrame(rows)


def build_order_preview(data: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "门店": store.get("name") or "—",
            "部门": store.get("dept") or "—",
            "定单量": store.get("orders_actual"),
            "目标": store.get("orders_target"),
            "达成率": (store.get("orders_actual") / store.get("orders_target"))
            if store.get("orders_actual") is not None and store.get("orders_target") not in (None, 0)
            else None,
        }
        for store in (data.get("retailStores") or [])[:50]
    ]
    return pd.DataFrame(rows)


def build_personal_preview(data: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {
            "工号": employee.get("id") or "—",
            "姓名": employee.get("name") or "—",
            "岗位": employee.get("title") or "—",
            "门店": employee.get("store") or "—",
            "个人定单量": employee.get("orders"),
        }
        for employee in (data.get("employees") or [])
        if employee.get("orders") is not None
    ]
    return pd.DataFrame(rows[:50])


def display_module_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    display["模块"] = display.apply(lambda row: f"　{row['模块']}" if row.get("缩进") else row["模块"], axis=1)
    display = display.drop(columns=["缩进"], errors="ignore")
    for column in ["本月人工成本", "上月人工成本", "固定成本", "绩效成本", "人均总成本"]:
        display[column] = display[column].map(format_number)
    display["固浮比"] = display["固浮比"].map(format_percent)
    return display


def display_retail_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    display = add_retail_total_row(display)
    keep_columns = [
        "门店",
        "所属部门",
        "人数",
        "人工成本",
        "上月成本",
        "环比",
        "固定成本",
        "绩效成本",
        "固浮比",
        "人均固定成本",
        "人均变动成本",
        "定单实际",
        "定单目标",
        "达成率",
        "人均总成本",
        "人效(单/人)",
        "人力CPS",
    ]
    display = display[keep_columns]
    for column in ["人工成本", "上月成本", "固定成本", "绩效成本", "人均固定成本", "人均变动成本", "人均总成本", "人力CPS"]:
        display[column] = display[column].map(format_number)
    display["固浮比"] = display["固浮比"].map(format_percent)
    display["达成率"] = display["达成率"].map(format_percent)
    display["人效(单/人)"] = display["人效(单/人)"].map(lambda value: "—" if value is None else f"{value:.2f}")
    display["定单实际"] = display["定单实际"].map(lambda value: "—" if value is None else int(value))
    display["定单目标"] = display["定单目标"].map(lambda value: "—" if value is None else int(value))
    return display


def display_retail_cost_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = add_retail_cost_total_row(frame.copy())
    for column in ["法定加班", "上月法定加班", "出差津贴", "上月出差津贴", "社保公积金(企)", "上月社保"]:
        display[column] = display[column].map(format_number)
    return display


def display_support_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ["人工成本", "固定成本", "绩效成本", "人均总成本"]:
        display[column] = display[column].map(format_number)
    display["固浮比"] = display["固浮比"].map(format_percent)
    return display


def display_delivery_store_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ["人工成本", "固定成本", "绩效成本", "法定加班费", "出差津贴", "社保公积金（企业）", "人均总成本", "人均固定成本", "人均绩效成本"]:
        display[column] = display[column].map(format_number)
    display["固浮比"] = display["固浮比"].map(format_percent)
    return display


def display_delivery_support_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ["人工成本", "固定成本", "绩效成本", "人均总成本"]:
        display[column] = display[column].map(format_number)
    display["固浮比"] = display["固浮比"].map(format_percent)
    return display


def display_personnel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    if "有定单" in display.columns:
        display = display.drop(columns=["有定单"])
    if "象限编号" in display.columns:
        display = display.drop(columns=["象限编号", "中位个人成本", "中位个人定单量"], errors="ignore")
    display["个人成本"] = display["个人成本"].map(format_number)
    display["个人定单量"] = display["个人定单量"].map(lambda value: "—" if value is None else int(value))
    return display


def display_annual_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in [
        "战区总人工成本（万）",
        "战区固定（万）",
        "战区绩效（万）",
        "零售总成本（万）",
        "零售固定（万）",
        "零售绩效（万）",
        "交付总成本（万）",
        "交付固定（万）",
        "交付绩效（万）",
    ]:
        display[column] = display[column].map(lambda value: "—" if value is None else f"{value:.1f}")
    for column in ["零售人效（单/人）", "交付人效（单/人）"]:
        display[column] = display[column].map(lambda value: "—" if value is None else f"{value:.2f}")
    display = display.drop(columns=["年月"], errors="ignore")
    return display


def display_preview_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ["人工成本", "定单量", "目标", "个人定单量"]:
        if column in display.columns:
            display[column] = display[column].map(lambda value: "—" if value is None else int(value))
    if "达成率" in display.columns:
        display["达成率"] = display["达成率"].map(format_percent)
    return display
