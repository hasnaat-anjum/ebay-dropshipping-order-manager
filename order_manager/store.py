"""JSON persistence for orders and settings.

All data lives in one JSON file (default ``data/orders.json`` next to the
project, overridable with ``--data``).  The file is written atomically
(write to a temp file, then rename) so a crash mid-save never corrupts
the store, and every save keeps one ``.bak`` copy of the previous state.

File layout:
    {
      "version": 1,
      "settings": { ... Settings ... },
      "orders": [ { ... Order ... }, ... ]
    }
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .models import Order, Settings

STORE_VERSION = 1


class DuplicateOrderError(ValueError):
    """Raised when adding an order whose ID already exists."""


class OrderNotFoundError(KeyError):
    """Raised when an order ID is not in the store."""


class Store:
    """A tiny JSON-backed store for orders + settings."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.settings = Settings()
        self.orders: list[Order] = []
        self.load()

    # -- loading / saving ----------------------------------------------

    def load(self) -> None:
        """Load from disk; a missing file means an empty store."""
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self.settings = Settings.from_dict(raw.get("settings", {}))
        self.orders = [Order.from_dict(o) for o in raw.get("orders", [])]

    def save(self) -> None:
        """Save atomically, keeping a .bak of the previous file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STORE_VERSION,
            "settings": self.settings.to_dict(),
            "orders": [o.to_dict() for o in self.orders],
        }
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            if self.path.exists():
                shutil.copy2(self.path, str(self.path) + ".bak")
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- orders ----------------------------------------------------------

    def add(self, order: Order) -> Order:
        """Add an order; duplicate order IDs are rejected."""
        if self.get(order.order_id) is not None:
            raise DuplicateOrderError(
                f"order {order.order_id!r} already exists "
                "(use `update` to change it)"
            )
        self.orders.append(order)
        self.save()
        return order

    def get(self, order_id: str) -> Order | None:
        """Find one order by ID, or None."""
        for order in self.orders:
            if order.order_id == order_id:
                return order
        return None

    def require(self, order_id: str) -> Order:
        """Find one order by ID or raise OrderNotFoundError."""
        order = self.get(order_id)
        if order is None:
            raise OrderNotFoundError(f"no order with ID {order_id!r}")
        return order

    def remove(self, order_id: str) -> Order:
        """Delete an order and return it."""
        order = self.require(order_id)
        self.orders.remove(order)
        self.save()
        return order

    def update(self, order_id: str, **changes) -> Order:
        """Change fields of an order (unknown fields are ignored)."""
        order = self.require(order_id)
        known = set(Order.__dataclass_fields__)
        for key, value in changes.items():
            if key in known and value is not None:
                setattr(order, key, value)
        self.save()
        return order

    def list_orders(self, status: str | None = None,
                    supplier: str | None = None,
                    query: str | None = None) -> list[Order]:
        """All orders, optionally filtered, newest sale first."""
        result = list(self.orders)
        if status:
            result = [o for o in result if o.status == status]
        if supplier:
            needle = supplier.lower()
            result = [o for o in result if needle in o.supplier.lower()]
        if query:
            needle = query.lower()
            result = [o for o in result
                      if needle in o.item_title.lower()
                      or needle in o.order_id.lower()
                      or needle in o.buyer.lower()
                      or needle in o.tracking_number.lower()]
        result.sort(key=lambda o: (o.sale_date, o.order_id), reverse=True)
        return result

    def suppliers(self) -> list[str]:
        """Supplier names in use, alphabetically."""
        return sorted({o.supplier for o in self.orders if o.supplier})

    def count(self) -> int:
        return len(self.orders)
