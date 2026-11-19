"""CSV import: eBay sales exports and supplier order lists.

eBay's "Orders" report and most supplier exports use different column
names, so both importers accept common header aliases and ignore extra
columns instead of failing on them.  Rows that cannot be parsed are
collected and reported, never silently dropped.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import Order

# Header aliases (lowercased, stripped) -> Order field.
SALES_ALIASES = {
    "order id": "order_id", "order number": "order_id", "order#": "order_id",
    "order": "order_id", "order_id": "order_id",
    "sale date": "sale_date", "order date": "sale_date", "date": "sale_date",
    "sold date": "sale_date", "sale_date": "sale_date",
    "item title": "item_title", "title": "item_title",
    "item": "item_title", "item_title": "item_title",
    "buyer": "buyer", "buyer username": "buyer", "buyer Username": "buyer",
    "sale price": "sale_price", "item price": "sale_price",
    "price": "sale_price", "sale_price": "sale_price",
    "shipping charged": "shipping_charged", "shipping": "shipping_charged",
    "shipping charge": "shipping_charged",
    "shipping_charged": "shipping_charged",
    "supplier": "supplier",
    "supplier cost": "supplier_cost", "cost": "supplier_cost",
    "supplier_cost": "supplier_cost",
    "shipping cost": "shipping_cost", "shipping_cost": "shipping_cost",
    "supplier order id": "supplier_order_id",
    "supplier order": "supplier_order_id",
    "supplier_order_id": "supplier_order_id",
    "tracking number": "tracking_number", "tracking": "tracking_number",
    "tracking_number": "tracking_number",
    "status": "status",
    "shipped date": "shipped_date", "shipped_date": "shipped_date",
    "delivered date": "delivered_date", "delivered_date": "delivered_date",
    "notes": "notes",
}


def _to_float(text: str | None, default: float = 0.0) -> float:
    """Parse money like '$12.99', '1,299.00' or '' into a float."""
    if text is None:
        return default
    cleaned = str(text).strip().replace("$", "").replace(",", "")
    if not cleaned:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _normalise_row(row: dict) -> dict:
    """Map a CSV row's headers onto Order field names."""
    mapped: dict = {}
    for raw_key, value in row.items():
        if raw_key is None:
            continue
        key = raw_key.strip().lower()
        field = SALES_ALIASES.get(key)
        if field and value is not None and str(value).strip() != "":
            mapped[field] = str(value).strip()
    return mapped


def import_sales_csv(path: str | Path) -> tuple[list[Order], list[str]]:
    """Read an eBay sales CSV into Orders.

    Returns (orders, errors).  Rows without an order ID or sale date are
    reported in ``errors`` and skipped; everything else imports with
    sensible defaults (status ``new`` unless the CSV says otherwise).
    """
    orders: list[Order] = []
    errors: list[str] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for line_no, raw_row in enumerate(reader, start=2):
            row = _normalise_row(raw_row)
            if not row.get("order_id"):
                errors.append(f"line {line_no}: missing order id, skipped")
                continue
            if not row.get("sale_date"):
                errors.append(f"line {line_no}: order {row['order_id']} "
                              "has no sale date, skipped")
                continue
            try:
                orders.append(Order(
                    order_id=row["order_id"],
                    sale_date=row["sale_date"],
                    item_title=row.get("item_title", "(no title)"),
                    buyer=row.get("buyer", ""),
                    sale_price=_to_float(row.get("sale_price")),
                    shipping_charged=_to_float(row.get("shipping_charged")),
                    supplier=row.get("supplier", ""),
                    supplier_cost=_to_float(row.get("supplier_cost")),
                    shipping_cost=_to_float(row.get("shipping_cost")),
                    supplier_order_id=row.get("supplier_order_id", ""),
                    tracking_number=row.get("tracking_number", ""),
                    status=row.get("status", "new").lower(),
                    shipped_date=row.get("shipped_date", ""),
                    delivered_date=row.get("delivered_date", ""),
                    notes=row.get("notes", ""),
                ))
            except (TypeError, ValueError) as exc:
                errors.append(f"line {line_no}: {exc}, skipped")
    return orders, errors


def export_orders_csv(orders: list[Order], rows: list[dict],
                      path: str | Path) -> None:
    """Write the report rows (from reports.orders_table) to a CSV file."""
    if not rows:
        raise ValueError("nothing to export")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
