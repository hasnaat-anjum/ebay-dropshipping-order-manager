# eBay Dropshipping Order Manager

Track every eBay dropshipping order from sale to delivery — with real profit per order, overdue alerts, and supplier performance — in one free, offline tool. No API key, no monthly fee, no account.

## The problem it solves

Dropshippers sell on eBay but buy from a supplier (AliExpress, Amazon, Walmart, CJdropshipping…). Every order lives in two places: the eBay sale and the supplier purchase. The tools that join them up are paid SaaS — AutoDS, Easync and Yaballe start around $26/month and charge per automatic order — or developer-only automation scripts with no dashboard at all. There is no free, local, eBay-focused order manager that tells you, at a glance, which orders are late, which ones lose money, and which supplier is worth keeping.

This tool fills that gap: one command shows your profit, your overdue orders, and your best and worst suppliers.

## What it does

- **Order tracking** — record each eBay sale with its supplier purchase in one record; follow the real pipeline `new → ordered → shipped → delivered → completed` (plus `returned` / `cancelled`), with invalid jumps rejected.
- **Real profit per order** — sale price + shipping charged, minus the eBay final-value fee (13.25% + $0.30 by default, configurable), supplier cost and shipping cost. Negative-margin orders are flagged.
- **Alerts** — orders past your handling-time promise, parcels in transit too long, shipped orders with no tracking number, and orders that lose money.
- **Supplier scorecard** — profit, average profit per order, average delivery days, on-time rate and return rate per supplier, ranked by profit.
- **Dashboard** — revenue, profit, margin %, open/returned/cancelled counts, average delivery time, and a monthly breakdown.
- **CSV import** — import eBay sales exports (flexible headers: "Order number", "Item price", "Shipping charge"… all recognised) and supplier order lists.
- **Exports** — orders to CSV, JSON or a self-contained HTML report.
- **Demo data** — 12 realistic orders across 4 suppliers, so you can try everything in one minute.

## Who it helps

- **eBay dropshippers** juggling orders across several suppliers and needing to know what is late and what actually makes money.
- **Small sellers** who want profit tracking without paying $26+/month for a SaaS dashboard.
- **Freelancers / virtual assistants** who manage a client's eBay store and need a clean daily report.

## How to use

Requires Python 3.10+ and nothing else — standard library only, no dependencies to install.

```bash
# load the demo dataset and see it in action
python -m order_manager demo
python -m order_manager dashboard
python -m order_manager alerts
python -m order_manager suppliers

# record a sale
python -m order_manager add --id 12-12345-67890 --item "Wireless Earbuds Pro" \
    --price 24.99 --supplier AliExpress --supplier-cost 11.50 \
    --shipping-cost 2.10 --supplier-order-id AE-88412031

# move it through the pipeline
python -m order_manager update 12-12345-67890 --status ordered
python -m order_manager update 12-12345-67890 --status shipped \
    --tracking LY123456789CN

# check one order in detail
python -m order_manager show 12-12345-67890

# import your eBay sales export
python -m order_manager import my-ebay-orders.csv

# export a report
python -m order_manager export --format html --out report.html
python -m order_manager export --format csv --out orders.csv

# use a different data file
python -m order_manager --data ~/my-store.json dashboard
```

### All commands

| Command | What it does |
|---|---|
| `add` | Record a new order (sale + supplier purchase) |
| `list [--status] [--supplier] [--search] [--limit]` | List orders, newest first |
| `show <id>` | Full money breakdown for one order |
| `update <id> [--status] [--tracking] …` | Change status, tracking, costs, dates |
| `remove <id>` | Delete an order |
| `dashboard` | Revenue, profit, margin, monthly totals |
| `alerts` | Overdue, in-transit, untracked, loss-making orders |
| `suppliers` | Supplier performance scorecard |
| `import <file.csv>` | Import eBay sales from CSV |
| `export [--format csv\|json\|html] [--out]` | Export orders / HTML report |
| `demo` | Load the 12-order demo dataset |
| `config [--show] [--fee-rate] [--handling-days] …` | View/change fees and thresholds |

### Settings

eBay's fee and your handling promise differ by store — change them once and every report follows:

```bash
python -m order_manager config --fee-rate 0.1325 --fee-fixed 0.30 \
    --handling-days 2 --transit-days 14
python -m order_manager config --show
```

## Demo data

`examples/demo_orders.csv` holds 12 realistic November 2026 orders from AliExpress, Amazon, Walmart and CJdropshipping — including one order that is 3 days overdue, one parcel in transit for 16 days with no tracking, one returned order, and one order that loses $2.93. Load it with `python -m order_manager demo`, then run `dashboard`, `alerts` and `suppliers` to see the tool work. Expected demo results: $259.90 revenue, $63.74 profit (24.5% margin), 4 alerts, average delivery 6.6 days.

`examples/ebay_export_sample.csv` shows the eBay-style headers the importer accepts.

## Data storage

Everything lives in one local JSON file (`data/orders.json` by default). Every save is atomic and keeps a `.bak` copy of the previous state, so a crash can never corrupt your orders. Your data never leaves your machine.

## Technologies

Python 3.10+, standard library only (argparse, dataclasses, csv, json). No external dependencies, no network calls.

## Tests

```bash
python run_tests.py        # 50 tests: fees, store, reports, import, CLI
```

## Project structure

```
ebay-dropshipping-order-manager/
├── order_manager/
│   ├── __init__.py        # version
│   ├── __main__.py        # `python -m order_manager`
│   ├── cli.py             # argument parsing + all subcommands
│   ├── models.py          # Order / Settings + status pipeline
│   ├── fees.py            # eBay fee + profit maths (single source of truth)
│   ├── store.py           # atomic JSON persistence
│   ├── reports.py         # dashboard, alerts, supplier stats, HTML export
│   └── import_csv.py      # eBay CSV import with header aliases
├── tests/                 # unittest suite (fees, store, reports, import, CLI)
├── examples/
│   ├── demo_orders.csv        # 12-order demo dataset
│   └── ebay_export_sample.csv # eBay-style headers the importer accepts
├── data/                  # your orders live here (created on first use)
├── run_tests.py
├── requirements.txt       # stdlib only — intentionally empty
└── LICENSE                # MIT
```

## License

MIT — free for personal and commercial use.
