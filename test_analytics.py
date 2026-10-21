from __future__ import annotations

from copy import deepcopy
import unittest

import pandas as pd

from app.analytics import (
    build_delivery_support_frame,
    build_module_summary,
    build_order_preview,
    build_personal_preview,
    build_personnel_frame,
    build_retail_frame,
    build_support_frame,
    compute_kpis,
    display_personnel_frame,
    display_preview_frame,
    display_retail_frame,
)
from app.charts import build_retail_orders_chart
from app.importers import merge_order_import, process_cost_data
from app.normalize import normalize_month_data


class SavedMonthTests(unittest.TestCase):
    def test_legacy_orders_render_without_losing_missing_values(self):
        values = [("12.0", "24"), ("—", "N/A"), (float("nan"), 10), (float("inf"), 4), (2, 0)]
        stores = [
            {"name": f"门店{i}", "dept": "零售", "labor": 1200, "fixed": 900, "perf": 300,
             "count": 2, "orders_actual": actual, "orders_target": target}
            for i, (actual, target) in enumerate(values)
        ]
        month = {"retailStores": stores}
        preview = display_preview_frame(build_order_preview(month))
        self.assertEqual(preview["定单量"].tolist(), [12, "—", "—", "—", 2])
        self.assertEqual(preview["目标"].tolist(), [24, "—", 10, 4, 0])
        self.assertEqual(preview["达成率"].iloc[0], "50.0%")
        self.assertEqual(preview["达成率"].iloc[-1], "—")
        retail = build_retail_frame(month)
        self.assertEqual(display_retail_frame(retail)["定单实际"].iloc[:5].tolist(), [12, "—", "—", "—", 2])
        self.assertTrue(pd.isna(retail.loc[retail["门店"] == "门店4", "达成率"].iloc[0]))
        self.assertEqual(retail.loc[retail["门店"] == "门店4", "人力CPS"].iloc[0], 600)
        self.assertEqual(len(build_retail_orders_chart(retail).data), 2)
        self.assertEqual(len(build_retail_orders_chart(pd.DataFrame()).data), 0)
        self.assertEqual(compute_kpis(month)["total_actual"], 14)

    def test_personal_order_preview_with_invalid_saved_values(self):
        month = {"employees": [{"id": "001", "name": "甲", "orders": "N/A", "cat": "零售"},
                                {"id": "002", "name": "乙", "orders": "12.0", "cat": "零售"}]}
        preview = display_preview_frame(build_personal_preview(month))
        self.assertEqual(preview["个人定单量"].tolist(), ["—", 12])
        self.assertEqual(display_personnel_frame(build_personnel_frame(month))["个人定单量"].tolist(), [0, 12])

    def test_historical_support_view_preserves_source_and_totals(self):
        month = {
            "retailStores": [{"name": "零售门店", "dept": "零售", "count": 1, "labor": 100}],
            "supportDepts": [
                {"name": "旧零售一部", "labor": 1000, "fixed": 700, "perf": 300, "count": 1},
                {"name": "旧零售二部", "labor": 2000, "fixed": 1200, "perf": 800, "count": 2},
            ],
            "deliveryStores": [],
            "deliverySupport": [{"name": "交付", "labor": 900, "fixed": 600, "perf": 300, "count": 1}],
            "employees": [
                {"id": "", "name": "甲", "store": "旧零售一部", "cat": "零售", "labor": 1000},
                {"id": "", "name": "乙", "store": "交付", "cat": "交付", "labor": 900},
                {"id": "001", "name": "丙", "store": "零售门店", "cat": "零售", "labor": 100},
            ],
        }
        month = normalize_month_data(month)
        before = deepcopy(month)
        kpis = compute_kpis(month)
        summary = build_module_summary(month)
        retail = build_support_frame(month)
        delivery = build_delivery_support_frame(month)
        people = build_personnel_frame(month)
        self.assertEqual(retail["部门"].tolist(), ["零售战区支持"])
        self.assertEqual(delivery["类别"].tolist(), ["交付战区支持"])
        for source, display in ((month["supportDepts"], retail), (month["deliverySupport"], delivery)):
            for field, column in (("labor", "人工成本"), ("fixed", "固定成本"),
                                  ("perf", "绩效成本"), ("count", "人数")):
                self.assertAlmostEqual(display[column].iloc[0], sum(item.get(field, 0) for item in source))
        self.assertTrue((people.loc[people["分类"] == "交付", "门店"] == "交付战区支持").any())
        self.assertEqual(people.loc[people["姓名"] == "甲", "门店"].iloc[0], "零售战区支持")
        self.assertEqual(people.loc[people["姓名"] == "丙", "门店"].iloc[0], "零售门店")
        self.assertEqual(compute_kpis(month), kpis)
        self.assertTrue(build_module_summary(month).equals(summary))
        self.assertEqual(month, before)
        display_preview_frame(build_order_preview(month))
        display_retail_frame(build_retail_frame(month))

    def test_new_import_and_partial_order_match(self):
        rows = [
            ["二级部门", "三级部门", "四级部门", "员工ID", "姓名", "职务（岗位）", "人工成本", "是否计数", "所属周期"],
            ["江西", "零售", "南昌零售中心", "001", "甲", "产品专家", 100, "是", "2026/09"],
            ["江西", "零售", None, "002", "乙", "产品专家", 80, "是", "2026/09"],
            ["江西", "交付", float("nan"), "003", "丙", "区域交付负责人", 90, "是", "2026/09"],
            ["江西", "零售", "赣州零售中心", "004", "丁", "产品专家", 60, "是", "2026/09"],
        ]
        month = process_cost_data(rows)
        self.assertEqual([item["id"] for item in month["employees"]], ["001", "002", "003", "004"])
        self.assertEqual(build_support_frame(month)["部门"].tolist(), ["零售战区支持"])
        self.assertEqual(build_delivery_support_frame(month)["类别"].tolist(), ["交付战区支持"])
        merged, counts = merge_order_import(month, {"map": {"南昌零售中心": {"actual": 4, "target": 5}}}, "2026年9月")
        self.assertEqual(counts["unmatched"], 1)
        self.assertIn("—", display_preview_frame(build_order_preview(merged))["定单量"].tolist())
        display_retail_frame(build_retail_frame(merged))


if __name__ == "__main__":
    unittest.main()
