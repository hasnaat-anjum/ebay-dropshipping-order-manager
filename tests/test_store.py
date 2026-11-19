"""Tests for the JSON store (store.py) and the Order model."""

import json
import tempfile
import unittest
from pathlib import Path

from order_manager.models import ALLOWED_TRANSITIONS, Order, Settings
from order_manager.store import (DuplicateOrderError, OrderNotFoundError,
                                 Store)


def _order(order_id="12-1", **overrides):
    base = dict(order_id=order_id, sale_date="2026-11-19",
                item_title="Widget", sale_price=20.00)
    base.update(overrides)
    return Order(**base)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "orders.json"
        self.store = Store(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_get(self):
        self.store.add(_order())
        found = self.store.get("12-1")
        self.assertIsNotNone(found)
        self.assertEqual(found.item_title, "Widget")

    def test_duplicate_id_rejected(self):
        self.store.add(_order())
        with self.assertRaises(DuplicateOrderError):
            self.store.add(_order())

    def test_require_raises_for_unknown_id(self):
        with self.assertRaises(OrderNotFoundError):
            self.store.require("nope")

    def test_remove(self):
        self.store.add(_order())
        removed = self.store.remove("12-1")
        self.assertEqual(removed.order_id, "12-1")
        self.assertEqual(self.store.count(), 0)

    def test_update_changes_fields(self):
        self.store.add(_order(status="new"))
        self.store.update("12-1", status="shipped",
                          tracking_number="1Z999")
        updated = self.store.require("12-1")
        self.assertEqual(updated.status, "shipped")
        self.assertEqual(updated.tracking_number, "1Z999")

    def test_update_ignores_unknown_fields(self):
        self.store.add(_order())
        self.store.update("12-1", not_a_field="x")
        self.assertEqual(self.store.require("12-1").item_title, "Widget")

    def test_persistence_round_trip(self):
        self.store.add(_order(supplier="AliExpress", supplier_cost=8.50))
        self.store.settings.fee_rate = 0.10
        self.store.save()  # settings changes need an explicit save
        reloaded = Store(self.path)
        self.assertEqual(reloaded.count(), 1)
        self.assertEqual(reloaded.require("12-1").supplier, "AliExpress")
        self.assertEqual(reloaded.settings.fee_rate, 0.10)

    def test_backup_created_on_second_save(self):
        self.store.add(_order())
        self.store.add(_order("12-2"))
        self.assertTrue(Path(str(self.path) + ".bak").exists())

    def test_list_filters(self):
        self.store.add(_order("12-1", status="new", supplier="AliExpress"))
        self.store.add(_order("12-2", status="shipped", supplier="Amazon",
                              sale_date="2026-11-18"))
        self.store.add(_order("12-3", status="shipped", supplier="AliExpress",
                              sale_date="2026-11-17"))
        self.assertEqual(len(self.store.list_orders(status="shipped")), 2)
        self.assertEqual(len(self.store.list_orders(supplier="aliexpress")), 2)
        self.assertEqual(len(self.store.list_orders(query="12-2")), 1)
        # newest sale first
        self.assertEqual(self.store.list_orders()[0].order_id, "12-1")

    def test_suppliers_list(self):
        self.store.add(_order("12-1", supplier="Walmart"))
        self.store.add(_order("12-2", supplier="AliExpress"))
        self.assertEqual(self.store.suppliers(), ["AliExpress", "Walmart"])


class TestOrderModel(unittest.TestCase):
    def test_delivery_days(self):
        order = _order(sale_date="2026-11-10", delivered_date="2026-11-15")
        self.assertEqual(order.delivery_days(), 5)

    def test_delivery_days_none_when_not_delivered(self):
        self.assertIsNone(_order().delivery_days())

    def test_from_dict_ignores_unknown_keys(self):
        order = Order.from_dict({"order_id": "12-9", "sale_date": "2026-11-19",
                                 "item_title": "X", "surprise": 1})
        self.assertEqual(order.order_id, "12-9")

    def test_status_pipeline_is_connected(self):
        # every non-terminal status can reach a later status
        for status, allowed in ALLOWED_TRANSITIONS.items():
            if status in ("completed", "returned", "cancelled"):
                self.assertEqual(allowed, ())
            else:
                self.assertTrue(len(allowed) >= 1)


if __name__ == "__main__":
    unittest.main()
