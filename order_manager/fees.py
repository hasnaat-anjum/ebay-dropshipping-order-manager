"""eBay fee and profit maths.

Everything money-related in the app funnels through here so a fee change
in one place updates the dashboard, the per-order profit, the supplier
report and the exports at the same time.

Fee model (US eBay defaults, configurable in Settings):
    final value fee = fee_rate * (sale price + shipping charged)
                    + fee_fixed per order
Real profit of an order:
    sale price + shipping charged
    - eBay fee
    - supplier cost
    - shipping cost
"""

from __future__ import annotations

from .models import Order, Settings

DEFAULT_FEE_RATE = 0.1325   # 13.25% final value fee
DEFAULT_FEE_FIXED = 0.30    # $0.30 per order


def ebay_fee(sale_price: float, shipping_charged: float = 0.0,
             settings: Settings | None = None) -> float:
    """eBay final-value fee for one sale, rounded to cents."""
    settings = settings or Settings()
    fee = settings.fee_rate * (sale_price + shipping_charged) + settings.fee_fixed
    return round(max(fee, 0.0), 2)


def total_revenue(order: Order) -> float:
    """What the buyer paid in total (item + shipping)."""
    return round(order.sale_price + order.shipping_charged, 2)


def total_cost(order: Order, settings: Settings | None = None) -> float:
    """Everything the order cost the seller: eBay fee + supplier + shipping."""
    settings = settings or Settings()
    cost = (ebay_fee(order.sale_price, order.shipping_charged, settings)
            + order.supplier_cost + order.shipping_cost)
    return round(cost, 2)


def profit(order: Order, settings: Settings | None = None) -> float:
    """Real profit of one order, rounded to cents (may be negative)."""
    return round(total_revenue(order) - total_cost(order, settings), 2)


def margin_pct(order: Order, settings: Settings | None = None) -> float:
    """Profit as a percentage of revenue (0 when revenue is 0)."""
    revenue = total_revenue(order)
    if revenue <= 0:
        return 0.0
    return round(100.0 * profit(order, settings) / revenue, 1)


def fee_breakdown(order: Order, settings: Settings | None = None) -> dict:
    """Line-by-line money breakdown for one order (used by `show`)."""
    settings = settings or Settings()
    fee = ebay_fee(order.sale_price, order.shipping_charged, settings)
    return {
        "sale_price": round(order.sale_price, 2),
        "shipping_charged": round(order.shipping_charged, 2),
        "revenue": total_revenue(order),
        "ebay_fee": fee,
        "supplier_cost": round(order.supplier_cost, 2),
        "shipping_cost": round(order.shipping_cost, 2),
        "total_cost": total_cost(order, settings),
        "profit": profit(order, settings),
        "margin_pct": margin_pct(order, settings),
    }
