"""Command-line interface for the eBay Dropshipping Order Manager.

Usage examples (run from the project root):
    python -m order_manager add --id 12-12345-67890 --date 2026-11-19 \\
        --item "Wireless Earbuds Pro" --price 24.99 --supplier AliExpress \\
        --supplier-cost 11.50 --shipping-cost 2.10
    python -m order_manager list --status shipped
    python -m order_manager update 12-12345-67890 --status shipped \\
        --tracking 1Z999AA10123456784
    python -m order_manager dashboard
    python -m order_manager alerts
    python -m order_manager suppliers
    python -m order_manager import examples/demo_orders.csv
    python -m order_manager export --format html --out report.html
    python -m order_manager demo        # load the built-in demo dataset

All data is stored in a local JSON file (default ``data/orders.json``);
use ``--data`` to point at another file.  No account, API key or
internet connection is needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .fees import fee_breakdown
from .import_csv import export_orders_csv, import_sales_csv
from .models import ALLOWED_TRANSITIONS, STATUSES, Order
from .reports import (alerts, dashboard, html_report, orders_table,
                      supplier_stats)
from .store import DuplicateOrderError, OrderNotFoundError, Store

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "orders.json"
DEMO_PATH = Path(__file__).resolve().parent.parent / "examples" / "demo_orders.csv"


def _money(value: float, symbol: str = "$") -> str:
    return f"{symbol}{value:,.2f}"


def _today() -> date:
    return date.today()


# ----------------------------------------------------------------------
# Subcommand handlers (each takes parsed args + store, returns exit code)
# ----------------------------------------------------------------------

def cmd_add(args, store: Store) -> int:
    order = Order(
        order_id=args.id,
        sale_date=args.date or _today().isoformat(),
        item_title=args.item,
        buyer=args.buyer or "",
        sale_price=args.price,
        shipping_charged=args.shipping_charged,
        supplier=args.supplier or "",
        supplier_cost=args.supplier_cost,
        shipping_cost=args.shipping_cost,
        supplier_order_id=args.supplier_order_id or "",
        tracking_number=args.tracking or "",
        status=args.status,
        shipped_date=args.shipped_date or "",
        delivered_date=args.delivered_date or "",
        notes=args.notes or "",
    )
    try:
        store.add(order)
    except DuplicateOrderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    money = fee_breakdown(order, store.settings)
    print(f"Added order {order.order_id} — {order.item_title}")
    print(f"  Revenue { _money(money['revenue'], store.settings.currency_symbol)}"
          f"  eBay fee {_money(money['ebay_fee'], store.settings.currency_symbol)}"
          f"  Profit {_money(money['profit'], store.settings.currency_symbol)}"
          f" ({money['margin_pct']}%)")
    return 0


def cmd_list(args, store: Store) -> int:
    orders = store.list_orders(status=args.status, supplier=args.supplier,
                               query=args.search)
    if args.limit:
        orders = orders[:args.limit]
    if not orders:
        print("No orders match.")
        return 0
    sym = store.settings.currency_symbol
    print(f"{'Order ID':<22} {'Date':<11} {'Item':<34} {'Status':<10} "
          f"{'Profit':>9}")
    print("-" * 92)
    for o in orders:
        from .fees import profit
        print(f"{o.order_id:<22} {o.sale_date:<11} {o.item_title[:32]:<34} "
              f"{o.status:<10} {_money(profit(o, store.settings), sym):>9}")
    print(f"\n{len(orders)} order(s)")
    return 0


def cmd_show(args, store: Store) -> int:
    try:
        order = store.require(args.id)
    except OrderNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    sym = store.settings.currency_symbol
    money = fee_breakdown(order, store.settings)
    print(f"Order {order.order_id}")
    print(f"  Item:      {order.item_title}")
    print(f"  Buyer:     {order.buyer or '—'}")
    print(f"  Sale date: {order.sale_date}   Status: {order.status}")
    print(f"  Supplier:  {order.supplier or '—'}"
          f"   Supplier order: {order.supplier_order_id or '—'}")
    print(f"  Tracking:  {order.tracking_number or '—'}")
    if order.shipped_date:
        print(f"  Shipped:   {order.shipped_date}")
    if order.delivered_date:
        print(f"  Delivered: {order.delivered_date}"
              f" ({order.delivery_days()} days)")
    print("  Money:")
    print(f"    Sale price        {_money(money['sale_price'], sym):>10}")
    print(f"    Shipping charged  {_money(money['shipping_charged'], sym):>10}")
    print(f"    eBay fee          {_money(-money['ebay_fee'], sym):>10}")
    print(f"    Supplier cost     {_money(-money['supplier_cost'], sym):>10}")
    print(f"    Shipping cost     {_money(-money['shipping_cost'], sym):>10}")
    print(f"    Profit            {_money(money['profit'], sym):>10}"
          f"  ({money['margin_pct']}% margin)")
    if order.notes:
        print(f"  Notes:     {order.notes}")
    return 0


def cmd_update(args, store: Store) -> int:
    try:
        order = store.require(args.id)
    except OrderNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.status:
        if args.status not in STATUSES:
            print(f"Error: unknown status {args.status!r} "
                  f"(valid: {', '.join(STATUSES)})", file=sys.stderr)
            return 1
        allowed = ALLOWED_TRANSITIONS.get(order.status, ())
        if args.status not in allowed and order.status != args.status:
            print(f"Error: cannot move {order.status!r} -> "
                  f"{args.status!r} (allowed: "
                  f"{', '.join(allowed) or 'none'})", file=sys.stderr)
            return 1
        if args.status == "shipped" and not args.shipped_date:
            args.shipped_date = _today().isoformat()
        if args.status == "delivered" and not args.delivered_date:
            args.delivered_date = _today().isoformat()
    changes = {
        "status": args.status,
        "tracking_number": args.tracking,
        "supplier_cost": args.supplier_cost,
        "shipping_cost": args.shipping_cost,
        "supplier_order_id": args.supplier_order_id,
        "shipped_date": args.shipped_date,
        "delivered_date": args.delivered_date,
        "notes": args.notes,
    }
    store.update(args.id, **changes)
    print(f"Updated order {args.id} — status is now "
          f"{store.require(args.id).status}")
    return 0


def cmd_remove(args, store: Store) -> int:
    try:
        order = store.remove(args.id)
    except OrderNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Removed order {order.order_id} — {order.item_title}")
    return 0


def cmd_dashboard(args, store: Store) -> int:
    dash = dashboard(store.orders, store.settings)
    sym = store.settings.currency_symbol
    print("eBay Dropshipping — Dashboard")
    print(f"  Orders:    {dash['total_orders']} total, "
          f"{dash['open_orders']} open, {dash['returned_orders']} returned, "
          f"{dash['cancelled_orders']} cancelled")
    print(f"  Revenue:   {_money(dash['revenue'], sym)}")
    print(f"  Costs:     {_money(dash['costs'], sym)}")
    print(f"  Profit:    {_money(dash['profit'], sym)}"
          f" ({dash['margin_pct']}% margin)")
    if dash["avg_delivery_days"] is not None:
        print(f"  Avg delivery: {dash['avg_delivery_days']} days")
    print("  By status: " + ", ".join(
        f"{s}={n}" for s, n in sorted(dash["status_counts"].items())))
    if dash["monthly"]:
        print("  Monthly:")
        for month, vals in dash["monthly"].items():
            print(f"    {month}: {vals['orders']} orders, "
                  f"{_money(vals['revenue'], sym)} revenue, "
                  f"{_money(vals['profit'], sym)} profit")
    return 0


def cmd_alerts(args, store: Store) -> int:
    found = alerts(store.orders, store.settings)
    if not found:
        print("All clear — no orders need attention.")
        return 0
    print(f"{len(found)} alert(s):")
    for alert in found:
        print(f"  [{alert['severity'].upper():6}] {alert['order_id']}: "
              f"{alert['message']}")
    return 0


def cmd_suppliers(args, store: Store) -> int:
    rows = supplier_stats(store.orders, store.settings)
    if not rows:
        print("No suppliers yet — add an order with --supplier first.")
        return 0
    sym = store.settings.currency_symbol
    print(f"{'Supplier':<16} {'Orders':>6} {'Profit':>10} "
          f"{'Avg profit':>11} {'Avg days':>8} {'On time':>8} {'Returns':>8}")
    print("-" * 76)
    for r in rows:
        days = (f"{r['avg_delivery_days']}" if r["avg_delivery_days"] is not None
                else "—")
        on_time = (f"{r['on_time_pct']}%" if r["on_time_pct"] is not None
                   else "—")
        print(f"{r['supplier']:<16} {r['orders']:>6} "
              f"{_money(r['profit'], sym):>10} "
              f"{_money(r['avg_profit'], sym):>11} {days:>8} {on_time:>8} "
              f"{r['return_rate_pct']}%".rstrip())
    return 0


def cmd_import(args, store: Store) -> int:
    orders, errors = import_sales_csv(args.file)
    added = skipped = 0
    for order in orders:
        try:
            store.add(order)
            added += 1
        except DuplicateOrderError:
            skipped += 1
    for err in errors:
        print(f"Warning: {err}", file=sys.stderr)
    print(f"Imported {added} order(s), skipped {skipped} duplicate(s), "
          f"{len(errors)} row error(s).")
    return 0


def cmd_export(args, store: Store) -> int:
    orders = store.list_orders()
    rows = orders_table(orders, store.settings)
    if args.format == "json":
        out = args.out or "orders.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
    elif args.format == "html":
        out = args.out or "report.html"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html_report(orders, store.settings))
    else:
        out = args.out or "orders.csv"
        try:
            export_orders_csv(orders, rows, out)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    print(f"Exported {len(rows)} order(s) to {out}")
    return 0


def cmd_demo(args, store: Store) -> int:
    orders, errors = import_sales_csv(DEMO_PATH)
    added = skipped = 0
    for order in orders:
        try:
            store.add(order)
            added += 1
        except DuplicateOrderError:
            skipped += 1
    print(f"Demo data loaded: {added} order(s) added, "
          f"{skipped} already present.")
    print("Try: python -m order_manager dashboard")
    print("     python -m order_manager alerts")
    print("     python -m order_manager suppliers")
    return 0


def cmd_config(args, store: Store) -> int:
    if args.show:
        print(json.dumps(store.settings.to_dict(), indent=2))
        return 0
    if args.fee_rate is not None:
        store.settings.fee_rate = args.fee_rate
    if args.fee_fixed is not None:
        store.settings.fee_fixed = args.fee_fixed
    if args.handling_days is not None:
        store.settings.handling_days = args.handling_days
    if args.transit_days is not None:
        store.settings.transit_alert_days = args.transit_days
    if args.currency:
        store.settings.currency = args.currency
    if args.symbol:
        store.settings.currency_symbol = args.symbol
    store.save()
    print("Settings saved.")
    print(json.dumps(store.settings.to_dict(), indent=2))
    return 0


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="order-manager",
        description="Manage eBay dropshipping orders: track sales, supplier "
                    "purchases, profit and delivery — no API key needed.")
    parser.add_argument("--data", default=str(DEFAULT_DATA),
                        help="path to the orders JSON file "
                             f"(default: {DEFAULT_DATA})")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="record a new eBay sale / dropship order")
    p.add_argument("--id", required=True, help="eBay order number")
    p.add_argument("--date", help="sale date YYYY-MM-DD (default: today)")
    p.add_argument("--item", required=True, help="item title")
    p.add_argument("--buyer", help="buyer username")
    p.add_argument("--price", type=float, required=True,
                   help="sale price (what the buyer paid for the item)")
    p.add_argument("--shipping-charged", type=float, default=0.0,
                   help="shipping the buyer paid (default: 0)")
    p.add_argument("--supplier", help="supplier name, e.g. AliExpress")
    p.add_argument("--supplier-cost", type=float, default=0.0,
                   help="what the item cost from the supplier")
    p.add_argument("--shipping-cost", type=float, default=0.0,
                   help="what the supplier charged to ship it")
    p.add_argument("--supplier-order-id", help="order number at the supplier")
    p.add_argument("--tracking", help="tracking number")
    p.add_argument("--status", default="new", choices=list(STATUSES))
    p.add_argument("--shipped-date", help="YYYY-MM-DD")
    p.add_argument("--delivered-date", help="YYYY-MM-DD")
    p.add_argument("--notes", help="free-text note")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="list orders, newest first")
    p.add_argument("--status", choices=list(STATUSES))
    p.add_argument("--supplier", help="filter by supplier name")
    p.add_argument("--search", help="search item, buyer, order ID or tracking")
    p.add_argument("--limit", type=int, help="show at most N orders")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one order with full money breakdown")
    p.add_argument("id", help="eBay order number")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("update", help="update an order (status, tracking, costs)")
    p.add_argument("id", help="eBay order number")
    p.add_argument("--status", choices=list(STATUSES))
    p.add_argument("--tracking", help="tracking number")
    p.add_argument("--supplier-cost", type=float)
    p.add_argument("--shipping-cost", type=float)
    p.add_argument("--supplier-order-id", help="order number at the supplier")
    p.add_argument("--shipped-date", help="YYYY-MM-DD")
    p.add_argument("--delivered-date", help="YYYY-MM-DD")
    p.add_argument("--notes", help="free-text note")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("remove", help="delete an order")
    p.add_argument("id", help="eBay order number")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("dashboard", help="revenue, profit, open orders, monthly totals")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("alerts", help="orders that need attention right now")
    p.set_defaults(func=cmd_alerts)

    p = sub.add_parser("suppliers", help="supplier performance scorecard")
    p.set_defaults(func=cmd_suppliers)

    p = sub.add_parser("import", help="import eBay sales from a CSV file")
    p.add_argument("file", help="CSV file (eBay Orders export format)")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export", help="export orders to CSV, JSON or HTML")
    p.add_argument("--format", choices=["csv", "json", "html"], default="csv")
    p.add_argument("--out", help="output file (default: orders.<format>)")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("demo", help="load the built-in demo dataset")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("config", help="view or change store settings")
    p.add_argument("--show", action="store_true", help="show current settings")
    p.add_argument("--fee-rate", type=float, help="eBay fee rate, e.g. 0.1325")
    p.add_argument("--fee-fixed", type=float, help="eBay fixed fee per order")
    p.add_argument("--handling-days", type=int, help="handling-time promise in days")
    p.add_argument("--transit-days", type=int, help="in-transit alert threshold")
    p.add_argument("--currency", help="currency code, e.g. USD")
    p.add_argument("--symbol", help="currency symbol, e.g. $")
    p.set_defaults(func=cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store(args.data)
    return args.func(args, store)


if __name__ == "__main__":
    sys.exit(main())
