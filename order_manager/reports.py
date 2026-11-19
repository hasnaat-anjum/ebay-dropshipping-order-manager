"""Reports: dashboard, alerts, supplier performance, exports.

Every report is a pure function over a list of Orders + Settings, so the
same numbers feed the terminal output, the HTML export and the tests.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .fees import ebay_fee, margin_pct, profit, total_revenue
from .models import OPEN_STATUSES, Order, Settings


def _parse_date(text: str) -> date | None:
    """Parse an ISO date string, tolerating blanks and bad input."""
    if not text:
        return None
    try:
        year, month, day = (int(p) for p in text.split("-"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

def dashboard(orders: list[Order], settings: Settings | None = None,
              today: date | None = None) -> dict:
    """Overall business snapshot: money, open orders, delivery speed."""
    settings = settings or Settings()
    today = today or date.today()
    # Returned orders are excluded from money totals: the buyer was
    # refunded, so that revenue never landed.  Cancelled orders too.
    active = [o for o in orders if o.status not in ("cancelled", "returned")]
    done = [o for o in active if o.status in ("completed", "delivered")]
    open_orders = [o for o in orders if o.status in OPEN_STATUSES]
    returned = [o for o in orders if o.status == "returned"]

    revenue = sum(total_revenue(o) for o in active)
    costs = sum(o.supplier_cost + o.shipping_cost
                + ebay_fee(o.sale_price, o.shipping_charged, settings)
                for o in active)
    total_profit = revenue - costs

    delivery_days = [o.delivery_days() for o in done]
    delivery_days = [d for d in delivery_days if d is not None]
    avg_delivery = (round(sum(delivery_days) / len(delivery_days), 1)
                    if delivery_days else None)

    by_month: dict[str, dict] = defaultdict(
        lambda: {"orders": 0, "revenue": 0.0, "profit": 0.0})
    for o in active:
        month = o.sale_date[:7]  # YYYY-MM
        by_month[month]["orders"] += 1
        by_month[month]["revenue"] += total_revenue(o)
        by_month[month]["profit"] += profit(o, settings)
    monthly = {m: {k: (round(v, 2) if isinstance(v, float) else v)
                   for k, v in vals.items()}
               for m, vals in sorted(by_month.items())}

    return {
        "total_orders": len(orders),
        "active_orders": len(active),
        "open_orders": len(open_orders),
        "returned_orders": len(returned),
        "cancelled_orders": len([o for o in orders
                                 if o.status == "cancelled"]),
        "revenue": round(revenue, 2),
        "costs": round(costs, 2),
        "profit": round(total_profit, 2),
        "margin_pct": (round(100 * total_profit / revenue, 1)
                       if revenue > 0 else 0.0),
        "avg_delivery_days": avg_delivery,
        "status_counts": dict(Counter(o.status for o in orders)),
        "monthly": monthly,
    }


# ----------------------------------------------------------------------
# Alerts
# ----------------------------------------------------------------------

def alerts(orders: list[Order], settings: Settings | None = None,
           today: date | None = None) -> list[dict]:
    """Things that need attention right now, most urgent first.

    Alert types:
      * ``overdue_ship``  — still unshipped past the handling-time promise.
      * ``in_transit``    — shipped but not delivered past the transit limit.
      * ``negative_profit`` — the order loses money as priced.
      * ``no_tracking``   — shipped but no tracking number recorded.
      * ``stale_new``     — a brand-new order untouched for 3+ days.
    """
    settings = settings or Settings()
    today = today or date.today()
    found: list[dict] = []

    for order in orders:
        if order.status in ("cancelled", "completed", "returned"):
            continue
        age = order.days_since_sale(today)
        if order.status == "new" and age > settings.handling_days:
            found.append({"type": "overdue_ship", "order_id": order.order_id,
                          "severity": "high",
                          "message": f"not shipped {age} days after sale "
                                     f"(handling promise: "
                                     f"{settings.handling_days} days)"})
        elif order.status == "new" and age >= 3:
            found.append({"type": "stale_new", "order_id": order.order_id,
                          "severity": "medium",
                          "message": f"new order untouched for {age} days"})
        if order.status == "ordered" and age > settings.handling_days + 2:
            found.append({"type": "overdue_ship", "order_id": order.order_id,
                          "severity": "medium",
                          "message": f"ordered from supplier {age} days ago "
                                     "but not shipped yet"})
        if order.status == "shipped":
            shipped = _parse_date(order.shipped_date) or _parse_date(order.sale_date)
            transit = (today - shipped).days if shipped else 0
            if transit > settings.transit_alert_days:
                found.append({"type": "in_transit", "order_id": order.order_id,
                              "severity": "high",
                              "message": f"in transit {transit} days "
                                         "(no delivery yet)"})
            if not order.tracking_number:
                found.append({"type": "no_tracking", "order_id": order.order_id,
                              "severity": "medium",
                              "message": "shipped but no tracking number "
                                         "recorded"})
        if profit(order, settings) < 0 and order.status != "returned":
            found.append({"type": "negative_profit", "order_id": order.order_id,
                          "severity": "high",
                          "message": f"loses {settings.currency_symbol}"
                                     f"{abs(profit(order, settings)):.2f} "
                                     "at current prices"})

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda a: (severity_rank[a["severity"]], a["order_id"]))
    return found


# ----------------------------------------------------------------------
# Supplier performance
# ----------------------------------------------------------------------

def supplier_stats(orders: list[Order], settings: Settings | None = None,
                   today: date | None = None) -> list[dict]:
    """Per-supplier scorecard, ranked by total profit.

    Includes on-time delivery rate (delivered within 14 days of sale),
    average delivery days, average profit per order and return rate —
    the numbers that decide whether a supplier is worth keeping.
    """
    settings = settings or Settings()
    grouped: dict[str, list[Order]] = defaultdict(list)
    for order in orders:
        if order.supplier:
            grouped[order.supplier].append(order)

    rows = []
    for supplier, sup_orders in grouped.items():
        # Returned/cancelled orders are excluded from money totals, same
        # as the dashboard (a refunded sale is not revenue).
        active = [o for o in sup_orders
                  if o.status not in ("cancelled", "returned")]
        delivered = [o for o in sup_orders if o.delivery_days() is not None]
        on_time = [o for o in delivered if o.delivery_days() <= 14]
        days = [o.delivery_days() for o in delivered]
        rows.append({
            "supplier": supplier,
            "orders": len(sup_orders),
            "active_orders": len(active),
            "revenue": round(sum(total_revenue(o) for o in active), 2),
            "profit": round(sum(profit(o, settings) for o in active), 2),
            "avg_profit": (round(sum(profit(o, settings) for o in active)
                                 / len(active), 2) if active else 0.0),
            "avg_delivery_days": (round(sum(days) / len(days), 1)
                                  if days else None),
            "on_time_pct": (round(100 * len(on_time) / len(delivered), 1)
                            if delivered else None),
            "returns": sum(1 for o in sup_orders if o.status == "returned"),
            "return_rate_pct": (round(100 * sum(
                1 for o in sup_orders if o.status == "returned")
                / len(sup_orders), 1) if sup_orders else 0.0),
        })
    rows.sort(key=lambda r: r["profit"], reverse=True)
    return rows


# ----------------------------------------------------------------------
# Exports
# ----------------------------------------------------------------------

def orders_table(orders: list[Order], settings: Settings | None = None) -> list[dict]:
    """Flat rows for CSV/JSON export: order + money, one row per order."""
    settings = settings or Settings()
    rows = []
    for o in orders:
        rows.append({
            "order_id": o.order_id,
            "sale_date": o.sale_date,
            "item_title": o.item_title,
            "buyer": o.buyer,
            "status": o.status,
            "sale_price": o.sale_price,
            "shipping_charged": o.shipping_charged,
            "revenue": total_revenue(o),
            "ebay_fee": ebay_fee(o.sale_price, o.shipping_charged, settings),
            "supplier": o.supplier,
            "supplier_cost": o.supplier_cost,
            "shipping_cost": o.shipping_cost,
            "profit": profit(o, settings),
            "margin_pct": margin_pct(o, settings),
            "supplier_order_id": o.supplier_order_id,
            "tracking_number": o.tracking_number,
            "shipped_date": o.shipped_date,
            "delivered_date": o.delivered_date,
            "delivery_days": o.delivery_days(),
        })
    return rows


def html_report(orders: list[Order], settings: Settings | None = None,
                today: date | None = None) -> str:
    """A self-contained HTML report: dashboard + orders + suppliers."""
    settings = settings or Settings()
    dash = dashboard(orders, settings, today)
    sup = supplier_stats(orders, settings, today)
    sym = settings.currency_symbol

    def money(value) -> str:
        return f"{sym}{value:,.2f}"

    order_rows = "".join(
        "<tr><td>{order_id}</td><td>{sale_date}</td><td>{item}</td>"
        "<td>{supplier}</td><td>{status}</td>"
        "<td>{revenue}</td><td>{profit}</td><td>{margin}%</td></tr>".format(
            order_id=o["order_id"], sale_date=o["sale_date"],
            item=o["item_title"][:60], supplier=o["supplier"],
            status=o["status"], revenue=money(o["revenue"]),
            profit=money(o["profit"]), margin=o["margin_pct"])
        for o in orders_table(orders, settings))

    supplier_rows = "".join(
        "<tr><td>{s}</td><td>{n}</td><td>{p}</td><td>{d}</td>"
        "<td>{ot}</td><td>{r}%</td></tr>".format(
            s=r["supplier"], n=r["orders"], p=money(r["profit"]),
            d=r["avg_delivery_days"] if r["avg_delivery_days"] is not None else "–",
            ot=(f'{r["on_time_pct"]}%' if r["on_time_pct"] is not None else "–"),
            r=r["return_rate_pct"])
        for r in sup)

    month_rows = "".join(
        "<tr><td>{m}</td><td>{o}</td><td>{r}</td><td>{p}</td></tr>".format(
            m=m, o=v["orders"], r=money(v["revenue"]), p=money(v["profit"]))
        for m, v in dash["monthly"].items())

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>eBay Dropshipping Report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;
padding:0 1rem;color:#1a1a2e}}h1{{color:#0f3460}}h2{{color:#0f3460;
border-bottom:2px solid #e94560;padding-bottom:.3rem}}
.cards{{display:flex;gap:1rem;flex-wrap:wrap}}.card{{background:#f4f6fb;
border-radius:8px;padding:1rem 1.5rem;min-width:140px}}
.card b{{display:block;font-size:1.6rem;color:#0f3460}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{border:1px solid #ddd;padding:.45rem .6rem;text-align:left;font-size:.9rem}}
th{{background:#0f3460;color:#fff}}
tr:nth-child(even){{background:#f8f9fc}}
</style></head><body>
<h1>eBay Dropshipping Order Report</h1>
<p>Generated {(today or date.today()).isoformat()} &middot;
{dash["total_orders"]} orders &middot; {dash["open_orders"]} open</p>
<div class="cards">
<div class="card">Revenue<b>{money(dash["revenue"])}</b></div>
<div class="card">Profit<b>{money(dash["profit"])}</b></div>
<div class="card">Margin<b>{dash["margin_pct"]}%</b></div>
<div class="card">Avg delivery<b>{dash["avg_delivery_days"] or "–"} days</b></div>
</div>
<h2>Monthly breakdown</h2>
<table><tr><th>Month</th><th>Orders</th><th>Revenue</th><th>Profit</th></tr>
{month_rows}</table>
<h2>Supplier performance</h2>
<table><tr><th>Supplier</th><th>Orders</th><th>Profit</th>
<th>Avg delivery</th><th>On time</th><th>Returns</th></tr>
{supplier_rows}</table>
<h2>All orders</h2>
<table><tr><th>Order</th><th>Date</th><th>Item</th><th>Supplier</th>
<th>Status</th><th>Revenue</th><th>Profit</th><th>Margin</th></tr>
{order_rows}</table>
</body></html>
"""
