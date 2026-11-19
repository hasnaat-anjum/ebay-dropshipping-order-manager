"""Tests for CSV import (import_csv.py) and the CLI end to end."""

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

from order_manager.cli import main
from order_manager.import_csv import import_sales_csv
from order_manager.store import Store

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo_orders.csv"
SAMPLE = ROOT / "examples" / "ebay_export_sample.csv"


class TestImport(unittest.TestCase):
    def test_demo_file_imports_all_rows(self):
        orders, errors = import_sales_csv(DEMO)
        self.assertEqual(len(orders), 12)
        self.assertEqual(errors, [])
        first = orders[0]
        self.assertEqual(first.order_id, "12-11001-00001")
        self.assertEqual(first.supplier, "AliExpress")
        self.assertEqual(first.status, "completed")

    def test_ebay_style_headers_are_recognised(self):
        # eBay's own export uses different column names; aliases must map.
        orders, errors = import_sales_csv(SAMPLE)
        self.assertEqual(errors, [])
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].order_id, "12-22001-00001")
        self.assertEqual(orders[0].sale_price, 22.99)
        self.assertEqual(orders[0].shipping_charged, 0.0)
        self.assertEqual(orders[1].shipping_charged, 2.99)
        self.assertEqual(orders[1].supplier_cost, 7.80)

    def test_money_with_dollar_sign_and_commas(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                         delete=False) as fh:
            fh.write('order_id,sale_date,item_title,sale_price\n'
                     '12-9,2026-11-19,Big Item,"$1,299.00"\n')
            path = fh.name
        orders, errors = import_sales_csv(path)
        self.assertEqual(errors, [])
        self.assertEqual(orders[0].sale_price, 1299.00)

    def test_rows_missing_id_or_date_are_reported(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                         delete=False) as fh:
            fh.write("order_id,sale_date,item_title,sale_price\n"
                     ",2026-11-19,No ID,5.00\n"
                     "12-8,,No Date,5.00\n"
                     "12-7,2026-11-19,Good,5.00\n")
            path = fh.name
        orders, errors = import_sales_csv(path)
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(errors), 2)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = str(Path(self.tmp.name) / "orders.json")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        with mock.patch("sys.stdout", new=StringIO()) as out, \
             mock.patch("sys.stderr", new=StringIO()) as err:
            code = main(["--data", self.data, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_full_order_lifecycle(self):
        code, _, _ = self.run_cli(
            "add", "--id", "12-1", "--item", "Test Widget",
            "--price", "20.00", "--supplier", "AliExpress",
            "--supplier-cost", "8.00", "--shipping-cost", "1.50")
        self.assertEqual(code, 0)

        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("Test Widget", out)

        code, out, _ = self.run_cli("show", "12-1")
        self.assertEqual(code, 0)
        self.assertIn("$7.55", out)  # profit: 20 - 2.95 - 8 - 1.50

        code, _, _ = self.run_cli("update", "12-1", "--status", "ordered")
        self.assertEqual(code, 0)
        code, _, _ = self.run_cli("update", "12-1", "--status", "shipped",
                                   "--tracking", "1Z999")
        self.assertEqual(code, 0)

        code, out, _ = self.run_cli("dashboard")
        self.assertEqual(code, 0)
        self.assertIn("Profit", out)

        code, _, _ = self.run_cli("remove", "12-1")
        self.assertEqual(code, 0)
        self.assertEqual(Store(self.data).count(), 0)

    def test_invalid_status_transition_rejected(self):
        self.run_cli("add", "--id", "12-1", "--item", "Widget",
                     "--price", "20.00")
        # new -> delivered skips steps; must be rejected
        code, _, err = self.run_cli("update", "12-1", "--status", "delivered")
        self.assertEqual(code, 1)
        self.assertIn("cannot move", err)
        self.assertEqual(Store(self.data).require("12-1").status, "new")

    def test_duplicate_add_rejected(self):
        self.run_cli("add", "--id", "12-1", "--item", "Widget",
                     "--price", "20.00")
        code, _, err = self.run_cli("add", "--id", "12-1", "--item", "Widget",
                                    "--price", "20.00")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_demo_and_alerts_and_export(self):
        code, out, _ = self.run_cli("demo")
        self.assertEqual(code, 0)
        self.assertIn("12 order(s) added", out)

        code, out, _ = self.run_cli("alerts")
        self.assertEqual(code, 0)
        self.assertIn("4 alert(s)", out)

        code, out, _ = self.run_cli("suppliers")
        self.assertEqual(code, 0)
        self.assertIn("Amazon", out)

        out_path = str(Path(self.tmp.name) / "report.html")
        code, out, _ = self.run_cli("export", "--format", "html",
                                    "--out", out_path)
        self.assertEqual(code, 0)
        self.assertIn("$259.90", Path(out_path).read_text())

    def test_config_show_and_change(self):
        code, out, _ = self.run_cli("config", "--show")
        self.assertEqual(code, 0)
        self.assertIn("0.1325", out)
        code, out, _ = self.run_cli("config", "--fee-rate", "0.10")
        self.assertEqual(code, 0)
        self.assertEqual(Store(self.data).settings.fee_rate, 0.10)


if __name__ == "__main__":
    unittest.main()
