from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from typing import Any, Optional

import pandas as pd


def read_excel_rows(file_content: bytes) -> list[list[Any]]:
    workbook = pd.read_excel(BytesIO(file_content), sheet_name=0, header=None)
    return workbook.where(pd.notna(workbook), None).values.tolist()


def format_period(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    matched = pd.Series([text]).str.extract(r"(\d{4})/(\d{2})", expand=True)
    year = matched.iloc[0, 0]
    month = matched.iloc[0, 1]
    if not isinstance(year, str) or not isinstance(month, str):
        return text or None
    return f"{year}年{int(month)}月"


def normalize_store_name(name: Any) -> str:
    return (
        str(name or "")
        .strip()
        .replace(" ", "")
        .replace("　", "")
        .replace("(", "（")
        .replace(")", "）")
        .replace("（外展店）", "")
    )


def build_order_store_index(order_map: dict[str, dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    index: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for name, value in (order_map or {}).items():
        key = normalize_store_name(name)
        if not key:
            continue
        existing = index.get(key)
        if existing and existing.get("sourceName") != name:
            index.pop(key, None)
            ambiguous.add(key)
            continue
        if key not in ambiguous:
            index[key] = {**value, "sourceName": name}
    return index, ambiguous


def collect_employee_orders_by_id(data: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    orders_by_id: dict[str, dict[str, Any]] = {}
    payload = data or {}
    for employee in payload.get("employees") or []:
        employee_id = str(employee.get("id") or "").strip()
        if not employee_id or employee.get("orders") is None:
            continue
        orders_by_id[employee_id] = {
            "id": employee_id,
            "name": str(employee.get("name") or "").strip(),
            "orders": employee.get("orders"),
        }
    for entry in (payload.get("_pendingEmployeeOrders") or {}).values():
        employee_id = str((entry or {}).get("id") or "").strip()
        if not employee_id or entry.get("orders") is None:
            continue
        orders_by_id[employee_id] = {
            "id": employee_id,
            "name": str(entry.get("name") or "").strip(),
            "orders": entry.get("orders"),
        }
    return orders_by_id


def apply_employee_orders(
    employees: Optional[list[dict[str, Any]]],
    orders_by_id: Optional[dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    remaining = deepcopy(orders_by_id or {})
    for employee in employees or []:
        employee_id = str(employee.get("id") or "").strip()
        if not employee_id or employee_id not in remaining:
            continue
        employee["orders"] = remaining[employee_id].get("orders")
        remaining.pop(employee_id, None)

    employee_name_counts: dict[str, int] = {}
    pending_name_counts: dict[str, int] = {}

    for employee in employees or []:
        name = str(employee.get("name") or "").strip()
        if name:
            employee_name_counts[name] = employee_name_counts.get(name, 0) + 1

    for entry in remaining.values():
        name = str((entry or {}).get("name") or "").strip()
        if name:
            pending_name_counts[name] = pending_name_counts.get(name, 0) + 1

    for employee_id, entry in list(remaining.items()):
        name = str((entry or {}).get("name") or "").strip()
        if not name:
            continue
        if employee_name_counts.get(name) != 1 or pending_name_counts.get(name) != 1:
            continue
        target = next(
            (
                employee
                for employee in employees or []
                if str(employee.get("name") or "").strip() == name and employee.get("orders") is None
            ),
            None,
        )
        if not target:
            continue
        target["orders"] = entry.get("orders")
        remaining.pop(employee_id, None)

    return remaining


def process_cost_data(rows: list[list[Any]], zone_name: str = "江西战区") -> Optional[dict[str, Any]]:
    if not rows:
        return None

    header_idx = -1
    for idx in range(min(5, len(rows))):
        row = rows[idx] or []
        if any(cell is not None and "人工成本" in str(cell) for cell in row):
            header_idx = idx
            break

    if header_idx < 0:
        for idx in range(min(5, len(rows))):
            row = rows[idx] or []
            if any(cell is not None and ("二级部门" in str(cell) or "所属周期" in str(cell)) for cell in row):
                header_idx = idx
                break

    if header_idx < 0:
        return None

    header = rows[header_idx] or []
    if not header:
        return None

    def ci(name: str) -> int:
        for idx, cell in enumerate(header):
            if cell is not None and name in str(cell):
                return idx
        return -1

    i_d2 = ci("二级部门")
    if i_d2 < 0:
        i_d2 = 0
    i_d3 = ci("三级部门")
    if i_d3 < 0:
        i_d3 = 1
    i_d4 = ci("四级部门")
    if i_d4 < 0:
        i_d4 = 2

    i_id = ci("工号")
    i_name = ci("姓名")
    i_title = ci("职务（岗位）")
    i_labor = ci("人工成本")
    i_perf_bonus = ci("店端绩效奖金")
    i_q_bonus = ci("季度奖金应发")
    i_overtime_legal = ci("法定加班费")
    i_travel = ci("出差津贴")
    i_social = ci("社保公积金（企业）")
    i_accrual = ci("奖金计提")
    i_car_bonus = ci("二手车置换奖金")
    i_count = ci("是否计数")
    i_period = ci("所属周期")

    if i_labor < 0:
        return None

    period = None
    if i_period >= 0:
        for row in rows[header_idx + 1 :]:
            if i_period >= len(row):
                continue
            value = row[i_period]
            if value is None:
                continue
            text = str(value)
            if pd.Series([text]).str.contains(r"\d{4}/\d{2}", regex=True).iloc[0]:
                period = format_period(text)
                break

    def classify(dept3: Any, dept4: Any) -> str:
        level4 = str(dept4 or "")
        level3 = str(dept3 or "")
        if "零售中心" in level4 or "零售展厅" in level4:
            return "零售"
        if "交付中心" in level4:
            return "交付"
        if not dept4 and level3 == "交付":
            return "交付"
        return "零售"

    def get_store(dept3: Any, dept4: Any) -> str:
        if dept4 is not None and str(dept4).strip():
            return str(dept4).strip()
        if dept3 is not None and str(dept3).strip():
            return str(dept3).strip()
        return f"{zone_name}总部"

    def get_dept(dept3: Any, dept4: Any) -> str:
        return str(dept3 or "") if dept4 is not None and str(dept4).strip() else "战区直属"

    def number_at(row: list[Any], index: int) -> float:
        if index < 0 or index >= len(row):
            return 0.0
        value = row[index]
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    stores: dict[str, dict[str, Any]] = {}
    employees: list[dict[str, Any]] = []

    for row in rows[header_idx + 1 :]:
        if i_d2 >= len(row) or not row[i_d2]:
            continue
        dept3 = row[i_d3] if i_d3 < len(row) else None
        dept4 = row[i_d4] if i_d4 < len(row) else None
        category = classify(dept3, dept4)
        store = get_store(dept3, dept4)
        dept = get_dept(dept3, dept4)
        is_store = bool(dept4 is not None and str(dept4).strip())
        not_counted = str(row[i_count]) != "是" if i_count >= 0 and i_count < len(row) else True
        title = str(row[i_title] or "").strip() if i_title >= 0 and i_title < len(row) else ""
        is_intern = not_counted and title == "实习生"

        if store not in stores:
            stores[store] = {
                "cat": category,
                "dept": dept,
                "isStore": is_store,
                "labor": 0.0,
                "perf_bonus": 0.0,
                "q_bonus": 0.0,
                "accrual": 0.0,
                "car_bonus": 0.0,
                "overtime_legal": 0.0,
                "travel": 0.0,
                "social": 0.0,
                "count": 0,
                "intern_count": 0,
                "intern_labor": 0.0,
            }

        store_item = stores[store]
        labor = number_at(row, i_labor)
        store_item["labor"] += labor
        store_item["perf_bonus"] += number_at(row, i_perf_bonus)
        store_item["q_bonus"] += number_at(row, i_q_bonus)
        store_item["overtime_legal"] += number_at(row, i_overtime_legal)
        store_item["travel"] += number_at(row, i_travel)
        store_item["social"] += number_at(row, i_social)
        store_item["accrual"] += number_at(row, i_accrual)
        store_item["car_bonus"] += number_at(row, i_car_bonus)

        if is_intern:
            store_item["intern_count"] += 1
            store_item["intern_labor"] += labor
        else:
            store_item["count"] += 1

        employees.append(
            {
                "id": str(row[i_id] or "").strip() if i_id >= 0 and i_id < len(row) else "",
                "name": str(row[i_name] or "").strip() if i_name >= 0 and i_name < len(row) else "",
                "title": title,
                "store": store,
                "dept": dept,
                "cat": category,
                "labor": labor,
                "isIntern": is_intern,
                "orders": None,
            }
        )

    retail_stores: list[dict[str, Any]] = []
    delivery_stores: list[dict[str, Any]] = []
    support_depts: list[dict[str, Any]] = []
    delivery_support: list[dict[str, Any]] = []

    for name, store_item in stores.items():
        perf = (
            store_item["perf_bonus"]
            + store_item["q_bonus"]
            + store_item["accrual"]
            + store_item["car_bonus"]
        )
        fixed = store_item["labor"] - perf
        item = {
            "name": name,
            "dept": store_item["dept"],
            "labor": round(store_item["labor"]),
            "fixed": round(fixed),
            "perf": round(perf),
            "count": store_item["count"],
            "intern_count": store_item["intern_count"],
            "intern_labor": round(store_item["intern_labor"]),
            "overtime_legal": round(store_item["overtime_legal"]),
            "travel": round(store_item["travel"]),
            "social": round(store_item["social"]),
            "orders_actual": None,
            "orders_target": None,
        }
        if store_item["cat"] == "零售" and store_item["isStore"]:
            retail_stores.append(item)
        elif store_item["cat"] == "交付" and store_item["isStore"]:
            delivery_stores.append({**item})
        elif store_item["cat"] == "零售":
            support_depts.append({**item})
        else:
            delivery_support.append({**item})

    return {
        "retailStores": retail_stores,
        "supportDepts": support_depts,
        "deliveryStores": delivery_stores,
        "deliverySupport": delivery_support,
        "period": period,
        "employees": employees,
    }


def process_order_data(rows: list[list[Any]]) -> Optional[dict[str, Any]]:
    if not rows or len(rows) < 2:
        return None
    order_map: dict[str, dict[str, Any]] = {}
    delivery_total = None
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        name = str(row[0]).strip()
        if not name or name == "总计":
            continue
        if name in {"交付量总计", "交付量合计"}:
            try:
                delivery_total = int(float(row[1] or 0))
            except (TypeError, ValueError):
                delivery_total = 0
            continue
        actual = 0
        target = 0
        try:
            actual = int(float(row[1] or 0))
        except (TypeError, ValueError):
            actual = 0
        try:
            target = int(float(row[2] or 0))
        except (TypeError, ValueError, IndexError):
            target = 0
        order_map[name] = {"actual": actual, "target": target}
    if not order_map:
        return None
    return {"map": order_map, "deliveryTotal": delivery_total}


def process_personal_order_data(rows: list[list[Any]]) -> Optional[dict[str, dict[str, Any]]]:
    if not rows or len(rows) < 2:
        return None
    header = rows[0] or []
    if not header:
        return None

    def ci(name: str) -> int:
        for idx, cell in enumerate(header):
            if cell is not None and name in str(cell):
                return idx
        return -1

    i_id = ci("工号") if ci("工号") >= 0 else ci("专家工号") if ci("专家工号") >= 0 else 0
    i_name = ci("姓名") if ci("姓名") >= 0 else ci("专家姓名") if ci("专家姓名") >= 0 else 1
    i_orders = ci("净锁单") if ci("净锁单") >= 0 else ci("定单") if ci("定单") >= 0 else 2

    order_map: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        if i_id >= len(row) or not row[i_id]:
            continue
        employee_id = str(row[i_id]).strip()
        if not employee_id:
            continue
        name = str(row[i_name] or "").strip() if i_name < len(row) else ""
        try:
            orders = int(float(row[i_orders] or 0)) if i_orders < len(row) else 0
        except (TypeError, ValueError):
            orders = 0
        order_map[employee_id] = {"id": employee_id, "name": name, "orders": orders}

    return order_map or None


def build_empty_month(period: str) -> dict[str, Any]:
    return {
        "period": period,
        "retailStores": [],
        "supportDepts": [],
        "deliveryStores": [],
        "deliverySupport": [],
        "employees": [],
    }


def merge_cost_import(
    existing_data: Optional[dict[str, Any]],
    parsed_cost_data: dict[str, Any],
    period_label: str,
) -> dict[str, Any]:
    existing = deepcopy(existing_data or {})
    new_data = {
        "period": parsed_cost_data.get("period") or period_label,
        "retailStores": deepcopy(parsed_cost_data.get("retailStores") or []),
        "supportDepts": deepcopy(parsed_cost_data.get("supportDepts") or []),
        "deliveryStores": deepcopy(parsed_cost_data.get("deliveryStores") or []),
        "deliverySupport": deepcopy(parsed_cost_data.get("deliverySupport") or []),
        "employees": deepcopy(parsed_cost_data.get("employees") or []),
    }

    for store in new_data["retailStores"]:
        previous = next(
            (item for item in existing.get("retailStores") or [] if item.get("name") == store.get("name")),
            None,
        )
        if previous and previous.get("orders_actual") is not None:
            store["orders_actual"] = previous.get("orders_actual")
            store["orders_target"] = previous.get("orders_target")

    if existing.get("deliveryTotal") is not None:
        new_data["deliveryTotal"] = existing.get("deliveryTotal")

    remaining_orders = apply_employee_orders(
        new_data["employees"],
        collect_employee_orders_by_id(existing),
    )
    if remaining_orders:
        new_data["_pendingEmployeeOrders"] = remaining_orders

    return new_data


def merge_order_import(
    existing_data: Optional[dict[str, Any]],
    order_result: dict[str, Any],
    period_label: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    month_data = build_empty_month(period_label)
    month_data.update(deepcopy(existing_data or {}))
    month_data.setdefault("employees", [])
    month_data.setdefault("retailStores", [])
    month_data.setdefault("supportDepts", [])
    month_data.setdefault("deliveryStores", [])
    month_data.setdefault("deliverySupport", [])

    order_map = deepcopy(order_result.get("map") or {})
    delivery_total = order_result.get("deliveryTotal")
    order_index, ambiguous = build_order_store_index(order_map)

    unmatched = 0
    ambiguous_count = 0
    for store in month_data["retailStores"]:
        key = normalize_store_name(store.get("name"))
        if key in ambiguous:
            store["orders_actual"] = None
            store["orders_target"] = None
            ambiguous_count += 1
            continue
        match = order_index.get(key)
        if match:
            store["orders_actual"] = match.get("actual")
            store["orders_target"] = match.get("target")
        else:
            store["orders_actual"] = None
            store["orders_target"] = None
            unmatched += 1

    if delivery_total is not None:
        month_data["deliveryTotal"] = delivery_total

    return month_data, {"unmatched": unmatched, "ambiguous": ambiguous_count}


def merge_personal_order_import(
    existing_data: Optional[dict[str, Any]],
    order_map: dict[str, dict[str, Any]],
    period_label: str,
) -> tuple[dict[str, Any], dict[str, int]]:
    month_data = build_empty_month(period_label)
    month_data.update(deepcopy(existing_data or {}))
    month_data.setdefault("employees", [])
    month_data.setdefault("retailStores", [])
    month_data.setdefault("supportDepts", [])
    month_data.setdefault("deliveryStores", [])
    month_data.setdefault("deliverySupport", [])

    matched = 0
    pending = deepcopy(month_data.get("_pendingEmployeeOrders") or {})
    employees = month_data["employees"]

    for employee in employees:
        employee_id = str(employee.get("id") or "").strip()
        if not employee_id or employee_id not in order_map:
            continue
        employee["orders"] = order_map[employee_id].get("orders")
        pending.pop(employee_id, None)
        matched += 1

    existing_ids = {str(employee.get("id") or "").strip() for employee in employees}
    for entry in order_map.values():
        entry_id = str(entry.get("id") or "").strip()
        if entry_id and entry_id not in existing_ids:
            pending[entry_id] = deepcopy(entry)

    if pending:
        month_data["_pendingEmployeeOrders"] = pending
    else:
        month_data.pop("_pendingEmployeeOrders", None)

    return month_data, {"matched": matched, "pending": len(pending)}
