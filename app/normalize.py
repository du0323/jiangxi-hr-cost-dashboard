from __future__ import annotations

from copy import deepcopy
from typing import Any


def pick_preferred_employee(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if not current:
        return candidate

    def score(employee: dict[str, Any] | None) -> int:
        value = 0
        if employee and str(employee.get("store") or "").strip():
            value += 4
        if employee and str(employee.get("dept") or "").strip():
            value += 2
        if employee and str(employee.get("cat") or "").strip():
            value += 2
        if employee and float(employee.get("labor") or 0) > 0:
            value += 8
        if employee and str(employee.get("title") or "").strip():
            value += 1
        return value

    return candidate if score(candidate) > score(current) else current


def normalize_employees(
    employees: list[dict[str, Any]] | None,
    pending_source: dict[str, dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    pending = deepcopy(pending_source or {})
    deduped_by_id: dict[str, dict[str, Any]] = {}
    others: list[dict[str, Any]] = []

    for raw in employees or []:
        employee = deepcopy(raw)
        employee_id = str(employee.get("id") or "").strip()
        store = str(employee.get("store") or "").strip()
        dept = str(employee.get("dept") or "").strip()
        cat = str(employee.get("cat") or "").strip()
        labor = float(employee.get("labor") or 0)
        orders = employee.get("orders")
        is_placeholder = labor == 0 and not store and not dept and not cat

        if is_placeholder:
            if employee_id and orders is not None:
                pending[employee_id] = {
                    "id": employee_id,
                    "name": str(employee.get("name") or "").strip(),
                    "orders": orders,
                }
            continue

        if not employee_id:
            others.append(employee)
            continue

        existing = deduped_by_id.get(employee_id)
        preferred = pick_preferred_employee(existing, employee)
        secondary = existing if preferred is employee else employee
        if secondary and secondary.get("orders") is not None and preferred.get("orders") is None:
            preferred["orders"] = secondary["orders"]
        deduped_by_id[employee_id] = preferred

    normalized = [*others, *deduped_by_id.values()]
    for employee in normalized:
        employee_id = str(employee.get("id") or "").strip()
        if not employee_id:
            continue
        pending_entry = pending.get(employee_id)
        if not pending_entry or pending_entry.get("orders") is None or employee.get("orders") is not None:
            continue
        employee["orders"] = pending_entry["orders"]
        pending.pop(employee_id, None)

    employee_name_counts: dict[str, int] = {}
    pending_name_counts: dict[str, int] = {}
    for employee in normalized:
        name = str(employee.get("name") or "").strip()
        if name:
            employee_name_counts[name] = employee_name_counts.get(name, 0) + 1

    for entry in pending.values():
        name = str(entry.get("name") or "").strip()
        if name:
            pending_name_counts[name] = pending_name_counts.get(name, 0) + 1

    for employee_id, entry in list(pending.items()):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        if employee_name_counts.get(name) != 1 or pending_name_counts.get(name) != 1:
            continue
        target = next(
            (
                employee
                for employee in normalized
                if str(employee.get("name") or "").strip() == name and employee.get("orders") is None
            ),
            None,
        )
        if not target:
            continue
        target["orders"] = entry["orders"]
        pending.pop(employee_id, None)

    return normalized, pending


def normalize_month_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return data

    normalized = {
        **deepcopy(data),
        "retailStores": deepcopy(data.get("retailStores") or []),
        "supportDepts": deepcopy(data.get("supportDepts") or []),
        "deliveryStores": deepcopy(data.get("deliveryStores") or []),
        "deliverySupport": deepcopy(data.get("deliverySupport") or []),
        "employees": deepcopy(data.get("employees") or []),
    }
    employees, pending = normalize_employees(
        normalized.get("employees") or [],
        normalized.get("_pendingEmployeeOrders") or {},
    )
    normalized["employees"] = employees
    if pending:
        normalized["_pendingEmployeeOrders"] = pending
    else:
        normalized.pop("_pendingEmployeeOrders", None)
    return normalized
