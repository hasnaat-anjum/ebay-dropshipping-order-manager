"""Data models for the eBay Dropshipping Order Manager.

An Order is one eBay sale that a dropshipper fulfils by buying the item
from a third-party supplier (AliExpress, Amazon, Walmart, CJdropshipping,
...).  The sale and the supplier purchase live in the same record so the
real profit of every order is always one calculation away.

Statuses follow the real fulfilment pipeline:

    new -> ordered -> shipped -> delivered -> completed
                                  \-> returned
    any -> cancelled

Dates are ISO strings (YYYY-MM-DD).  Money is stored as plain floats in
the store currency (USD by default); all fee/profit maths lives in
``fees.py`` so the numbers stay consistent everywhere.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

# The fulfilment pipeline, in order.  ``returned`` and ``cancelled`` are
# terminal states that can be reached from any open status.
STATUSES = (
    "new",
    "ordered",
    "shipped",
    "delivered",
    "completed",
    "returned",
    "cancelled",
)

# Statuses that still need work (counted as "open" on the dashboard).
OPEN_STATUSES = ("new", "ordered", "shipped", "delivered")

# Which status may follow which.  ``None`` means "no restriction" and is
# only used for the terminal states, which are reachable from anywhere.
ALLOWED_TRANSITIONS = {
    "new": ("ordered", "cancelled"),
    "ordered": ("shipped", "cancelled"),
    "shipped": ("delivered", "returned", "cancelled"),
    "delivered": ("completed", "returned"),
    "completed": (),
    "returned": (),
    "cancelled": (),
}


@dataclass
class Order:
    """One eBay sale and the supplier purchase that fulfils it."""

    order_id: str                    # eBay order number, e.g. "12-12345-67890"
    sale_date: str                   # YYYY-MM-DD
    item_title: str
    buyer: str = ""
    sale_price: float = 0.0          # what the buyer paid for the item
    shipping_charged: float = 0.0    # shipping the buyer paid (0 = free shipping)
    supplier: str = ""               # supplier name, e.g. "AliExpress"
    supplier_cost: float = 0.0       # what the item cost from the supplier
    shipping_cost: float = 0.0       # what the supplier charged to ship it
    supplier_order_id: str = ""      # order number at the supplier
    tracking_number: str = ""
    status: str = "new"
    shipped_date: str = ""           # YYYY-MM-DD, when the supplier shipped it
    delivered_date: str = ""         # YYYY-MM-DD, when the buyer received it
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialise to a plain dict for the JSON store."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        """Build an Order from a stored dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)

    # -- derived values -------------------------------------------------

    def days_since_sale(self, today: date | None = None) -> int:
        """Whole days between the sale date and ``today`` (default: today)."""
        today = today or date.today()
        year, month, day = (int(p) for p in self.sale_date.split("-"))
        return (today - date(year, month, day)).days

    def delivery_days(self) -> int | None:
        """Days from sale to delivery, or None if not delivered yet."""
        if not self.delivered_date:
            return None
        s = [int(p) for p in self.sale_date.split("-")]
        d = [int(p) for p in self.delivered_date.split("-")]
        return (date(*d) - date(*s)).days


@dataclass
class Settings:
    """Store-wide settings, saved next to the orders in the JSON file."""

    currency: str = "USD"
    currency_symbol: str = "$"
    # eBay final-value fee: percentage of (sale price + shipping charged)
    # plus a fixed per-order fee.  Defaults are the common US rates;
    # change them with `order-manager config` if your store differs.
    fee_rate: float = 0.1325
    fee_fixed: float = 0.30
    # Handling-time promise: orders still unshipped after this many days
    # are flagged as overdue.  eBay's usual expectation is 1-2 days.
    handling_days: int = 2
    # In-transit alert: shipped orders not delivered after this many days.
    transit_alert_days: int = 14

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)
