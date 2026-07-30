from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def current_month_key(today: date | None = None) -> str:
    current = today or date.today()
    return f"{current.year}-{current.month:02d}"


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


def format_number(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{int(round(value)):,}"


def format_wan(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 10000:.1f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _sum(items: list[dict[str, Any]], field: str) -> float:
    return float(sum(float(item.get(field) or 0) for item in items))


def compute_kpis(data: dict[str, Any]) -> dict[str, float | int | None]:
    retail_stores = data.get("retailStores") or []
    support_depts = data.get("supportDepts") or []
    delivery_stores = data.get("deliveryStores") or []
    delivery_support = data.get("deliverySupport") or []

    all_retail = [*retail_stores, *support_depts]
    all_delivery = [*delivery_stores, *delivery_support]
    all_units = [*all_retail, *all_delivery]

    total_labor = _sum(all_units, "labor")
    total_count = int(_sum(all_units, "count"))
    total_fixed = _sum(all_units, "fixed")
    retail_labor = _sum(all_retail, "labor")
    retail_count = int(_sum(all_retail, "count"))
    total_actual = int(sum(int(store.get("orders_actual") or 0) for store in retail_stores if store.get("orders_actual") is not None))
    total_target = int(sum(int(store.get("orders_target") or 0) for store in retail_stores if store.get("orders_target") is not None))
    fixed_ratio = total_fixed / total_labor if total_labor else None
    order_rate = total_actual / total_target if total_target else None
    retail_avg_cost = retail_labor / retail_count if retail_count else None
    store_count = int(sum(int(store.get("count") or 0) for store in retail_stores if (store.get("count") or 0) > 0))
    human_efficiency = total_actual / store_count if store_count else None

    return {
        "total_labor": total_labor,
        "total_count": total_count,
        "fixed_ratio": fixed_ratio,
        "order_rate": order_rate,
        "retail_avg_cost": retail_avg_cost,
        "retail_human_efficiency": human_efficiency,
        "delivery_total": data.get("deliveryTotal"),
    }


def build_module_summary(data: dict[str, Any]) -> pd.DataFrame:
    retail_stores = data.get("retailStores") or []
    support_depts = data.get("supportDepts") or []
    delivery_stores = data.get("deliveryStores") or []
    delivery_support = data.get("deliverySupport") or []

    rows: list[dict[str, Any]] = []
    for label, items in [
        ("零售门店", retail_stores),
        ("零售支持", support_depts),
        ("交付门店", delivery_stores),
        ("交付支持", delivery_support),
    ]:
        labor = _sum(items, "labor")
        fixed = _sum(items, "fixed")
        perf = _sum(items, "perf")
        count = int(_sum(items, "count"))
        actual = int(sum(int(item.get("orders_actual") or 0) for item in items if item.get("orders_actual") is not None))
        target = int(sum(int(item.get("orders_target") or 0) for item in items if item.get("orders_target") is not None))
        rows.append(
            {
                "模块": label,
                "人工成本": labor,
                "固定成本": fixed,
                "绩效成本": perf,
                "人数": count,
                "人均成本": labor / count if count else None,
                "固浮比": fixed / labor if labor else None,
                "定单量": actual,
                "定单目标": target,
                "达成率": actual / target if target else None,
            }
        )

    summary = pd.DataFrame(rows)
    total = pd.DataFrame(
        [
            {
                "模块": "战区合计",
                "人工成本": summary["人工成本"].sum(),
                "固定成本": summary["固定成本"].sum(),
                "绩效成本": summary["绩效成本"].sum(),
                "人数": summary["人数"].sum(),
                "人均成本": summary["人工成本"].sum() / summary["人数"].sum() if summary["人数"].sum() else None,
                "固浮比": summary["固定成本"].sum() / summary["人工成本"].sum() if summary["人工成本"].sum() else None,
                "定单量": summary["定单量"].sum(),
                "定单目标": summary["定单目标"].sum(),
                "达成率": summary["定单量"].sum() / summary["定单目标"].sum() if summary["定单目标"].sum() else None,
            }
        ]
    )
    return pd.concat([summary, total], ignore_index=True)


def build_retail_frame(data: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for store in data.get("retailStores") or []:
        labor = float(store.get("labor") or 0)
        count = int(store.get("count") or 0)
        actual = store.get("orders_actual")
        target = store.get("orders_target")
        rows.append(
            {
                "门店": store.get("name") or "",
                "所属部门": store.get("dept") or "",
                "在编人数": count,
                "实习生人数": int(store.get("intern_count") or 0),
                "人工成本": labor,
                "固定成本": float(store.get("fixed") or 0),
                "绩效成本": float(store.get("perf") or 0),
                "固浮比": float(store.get("fixed") or 0) / labor if labor else None,
                "人均总成本": labor / count if count else None,
                "定单量": int(actual) if actual is not None else None,
                "定单目标": int(target) if target is not None else None,
                "达成率": (int(actual) / int(target)) if actual is not None and target not in (None, 0) else None,
                "人效": (int(actual) / count) if actual is not None and count else None,
                "人力CPS": (labor / int(actual)) if actual not in (None, 0) else None,
                "法定加班费": float(store.get("overtime_legal") or 0),
                "出差津贴": float(store.get("travel") or 0),
                "社保公积金": float(store.get("social") or 0),
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
                "个人成本": float(employee.get("labor") or 0),
                "个人定单量": int(employee.get("orders") or 0) if employee.get("orders") is not None else None,
                "是否实习生": bool(employee.get("isIntern")),
            }
        )
    return pd.DataFrame(rows)


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
    for column in ["人工成本", "固定成本", "绩效成本", "人均成本"]:
        display[column] = display[column].map(format_number)
    for column in ["固浮比", "达成率"]:
        display[column] = display[column].map(format_percent)
    return display


def display_retail_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    for column in ["人工成本", "固定成本", "绩效成本", "人均总成本", "人力CPS", "法定加班费", "出差津贴", "社保公积金"]:
        display[column] = display[column].map(format_number)
    for column in ["固浮比", "达成率"]:
        display[column] = display[column].map(format_percent)
    display["人效"] = display["人效"].map(lambda value: "—" if value is None else f"{value:.2f}")
    return display


def display_personnel_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame.copy()
    display["个人成本"] = display["个人成本"].map(format_number)
    display["个人定单量"] = display["个人定单量"].map(lambda value: "—" if value is None else int(value))
    display = display.drop(columns=["是否实习生"])
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
