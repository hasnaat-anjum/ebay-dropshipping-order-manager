"""Tests for eBay fee and profit maths (fees.py)."""

import unittest

from order_manager.fees import (ebay_fee, fee_breakdown, margin_pct, profit,
                                total_cost, total_revenue)
from order_manager.models import Order, Settings


def _order(**overrides):
    base = dict(order_id="12-1", sale_date="2026-11-19", item_title="Widget",
                sale_price=20.00, shipping_charged=0.0,
                supplier_cost=8.00, shipping_cost=1.50)
    base.update(overrides)
    return Order(**base)


class TestEbayFee(unittest.TestCase):
    def test_fee_is_13_25_percent_plus_30c(self):
        # 13.25% of $20.00 = $2.65, plus $0.30 = $2.95
        self.assertEqual(ebay_fee(20.00), 2.95)

    def test_fee_includes_shipping_charged(self):
        # 13.25% of ($20 + $5) = $3.31, plus $0.30 = $3.61
        self.assertEqual(ebay_fee(20.00, 5.00), 3.61)

    def test_fee_is_zero_for_free_order(self):
        self.assertEqual(ebay_fee(0.0), 0.30)

    def test_custom_fee_settings(self):
        settings = Settings(fee_rate=0.10, fee_fixed=0.50)
        self.assertEqual(ebay_fee(20.00, settings=settings), 2.50)


class TestProfit(unittest.TestCase):
    def test_profit_subtracts_fee_and_costs(self):
        # revenue 20.00 - fee 2.95 - supplier 8.00 - shipping 1.50 = 7.55
        self.assertEqual(profit(_order()), 7.55)

    def test_profit_can_be_negative(self):
        order = _order(sale_price=10.00, supplier_cost=9.00, shipping_cost=2.00)
        # fee = 13.25% of $10 + $0.30 = $1.63; 10 - 1.63 - 9 - 2 = -2.63
        self.assertEqual(profit(order), -2.63)

    def test_free_shipping_order(self):
        order = _order(sale_price=24.99, supplier_cost=11.50, shipping_cost=2.10)
        # fee 3.61; 24.99 - 3.61 - 11.50 - 2.10 = 7.78
        self.assertEqual(profit(order), 7.78)

    def test_margin_pct(self):
        # 7.55 profit on 20.00 revenue = 37.8%
        self.assertEqual(margin_pct(_order()), 37.8)

    def test_margin_zero_revenue(self):
        self.assertEqual(margin_pct(_order(sale_price=0.0)), 0.0)

    def test_total_revenue_includes_shipping(self):
        self.assertEqual(total_revenue(_order(shipping_charged=5.00)), 25.00)

    def test_breakdown_adds_up(self):
        order = _order()
        bd = fee_breakdown(order)
        self.assertEqual(round(bd["revenue"] - bd["total_cost"], 2),
                         bd["profit"])
        self.assertEqual(bd["ebay_fee"], 2.95)
        self.assertEqual(bd["supplier_cost"], 8.00)


if __name__ == "__main__":
    unittest.main()
