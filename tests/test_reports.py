"""Tests for reports: dashboard, alerts, supplier stats, exports.

All expectations are computed by hand from examples/demo_orders.csv
(12 orders, one returned) with "today" fixed at 2026-11-19.
"""

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from order_manager.import_csv import export_orders_csv, import_sales_csv
from order_manager.models import Settings
from order_manager.reports import (alerts, dashboard, html_report,
                                   orders_table, supplier_stats)

TODAY = date(2026, 11, 19)
DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo_orders.csv"


def load_demo():
    orders, errors = import_sales_csv(DEMO)
    assert not errors, errors
    return orders


class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.orders = load_demo()

    def test_counts(self):
        dash = dashboard(self.orders, today=TODAY)
        self.assertEqual(dash["total_orders"], 12)
        # open = new (2) + ordered (1) + shipped (3) + delivered (1)
        self.assertEqual(dash["open_orders"], 7)
        self.assertEqual(dash["returned_orders"], 1)
        self.assertEqual(dash["cancelled_orders"], 0)

    def test_money_excludes_returned_order(self):
        dash = dashboard(self.orders, today=TODAY)
        # revenue of the 11 non-returned orders
        self.assertEqual(dash["revenue"], 259.90)
        self.assertEqual(dash["profit"], 63.74)
        self.assertEqual(dash["margin_pct"], 24.5)

    def test_avg_delivery_days(self):
        # delivered in 9, 10, 6, 5 and 3 days -> 33/5 = 6.6
        dash = dashboard(self.orders, today=TODAY)
        self.assertEqual(dash["avg_delivery_days"], 6.6)

    def test_status_counts(self):
        dash = dashboard(self.orders, today=TODAY)
        self.assertEqual(dash["status_counts"]["completed"], 4)
        self.assertEqual(dash["status_counts"]["shipped"], 3)
        self.assertEqual(dash["status_counts"]["new"], 2)

    def test_monthly_breakdown(self):
        dash = dashboard(self.orders, today=TODAY)
        self.assertEqual(set(dash["monthly"]), {"2026-11"})
        self.assertEqual(dash["monthly"]["2026-11"]["orders"], 11)

    def test_empty_store(self):
        dash = dashboard([], today=TODAY)
        self.assertEqual(dash["total_orders"], 0)
        self.assertEqual(dash["profit"], 0.0)
        self.assertIsNone(dash["avg_delivery_days"])


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.orders = load_demo()

    def test_alert_types_present(self):
        found = alerts(self.orders, today=TODAY)
        by_type = {a["type"] for a in found}
        self.assertIn("overdue_ship", by_type)      # mini projector, new 3 days
        self.assertIn("in_transit", by_type)        # garden lights, 16 days
        self.assertIn("no_tracking", by_type)       # garden lights, no tracking
        self.assertIn("negative_profit", by_type)   # LED strip loses $2.93

    def test_alert_count_and_order(self):
        found = alerts(self.orders, today=TODAY)
        self.assertEqual(len(found), 4)
        # high severity first
        self.assertEqual([a["severity"] for a in found],
                         ["high", "high", "high", "medium"])

    def test_no_alerts_when_everything_is_fine(self):
        orders, _ = import_sales_csv(DEMO)
        # keep only the healthy completed orders
        healthy = [o for o in orders if o.status == "completed"]
        self.assertEqual(alerts(healthy, today=TODAY), [])

    def test_custom_handling_days(self):
        settings = Settings(handling_days=10)
        found = alerts(self.orders, settings, today=TODAY)
        self.assertNotIn("overdue_ship", {a["type"] for a in found})


class TestSupplierStats(unittest.TestCase):
    def setUp(self):
        self.orders = load_demo()

    def test_ranked_by_profit(self):
        rows = supplier_stats(self.orders, today=TODAY)
        self.assertEqual([r["supplier"] for r in rows],
                         ["Amazon", "AliExpress", "Walmart", "CJdropshipping"])
        self.assertEqual(rows[0]["profit"], 23.77)

    def test_aliexpress_numbers(self):
        rows = supplier_stats(self.orders, today=TODAY)
        ali = next(r for r in rows if r["supplier"] == "AliExpress")
        self.assertEqual(ali["orders"], 5)
        self.assertEqual(ali["profit"], 21.11)
        # delivery days include the returned order (it was delivered in 6
        # days before being returned): (9 + 10 + 6) / 3 = 8.3
        self.assertEqual(ali["avg_delivery_days"], 8.3)
        self.assertEqual(ali["on_time_pct"], 100.0)
        self.assertEqual(ali["return_rate_pct"], 20.0)

    def test_supplier_with_no_deliveries(self):
        rows = supplier_stats(self.orders, today=TODAY)
        cj = next(r for r in rows if r["supplier"] == "CJdropshipping")
        self.assertIsNone(cj["avg_delivery_days"])
        self.assertIsNone(cj["on_time_pct"])


class TestExports(unittest.TestCase):
    def setUp(self):
        self.orders = load_demo()

    def test_orders_table_rows(self):
        rows = orders_table(self.orders)
        self.assertEqual(len(rows), 12)
        strip = next(r for r in rows
                     if r["order_id"] == "12-11010-00010")
        self.assertEqual(strip["profit"], -2.93)
        self.assertEqual(strip["margin_pct"], -18.3)

    def test_csv_export_round_trip(self):
        rows = orders_table(self.orders)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            export_orders_csv(self.orders, rows, path)
            with open(path, newline="", encoding="utf-8") as fh:
                read_back = list(csv.DictReader(fh))
        self.assertEqual(len(read_back), 12)
        self.assertEqual(read_back[0]["order_id"], "12-11001-00001")

    def test_html_report_contains_key_numbers(self):
        html = html_report(self.orders, today=TODAY)
        self.assertIn("$259.90", html)
        self.assertIn("$63.74", html)
        self.assertIn("Amazon", html)
        self.assertIn("Wireless Earbuds Pro", html)


if __name__ == "__main__":
    unittest.main()
