#!/usr/bin/env python3
"""
bot_status.py

Shows Alpaca account/position/order status and keeps trade_journal.csv updated.

Safe default:
- Reads config.yaml
- Refuses to run against live trading unless --allow-live is provided
- Uses APCA_API_KEY_ID and APCA_API_SECRET_KEY from environment
- Writes/updates trade_journal.csv from Alpaca orders
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


JOURNAL_FIELDS = [
    "synced_at",
    "order_id",
    "parent_order_id",
    "client_order_id",
    "symbol",
    "side",
    "order_type",
    "order_class",
    "status",
    "time_in_force",
    "submitted_at",
    "filled_at",
    "filled_qty",
    "filled_avg_price",
    "limit_price",
    "stop_price",
    "take_profit_limit_price",
    "stop_loss_stop_price",
    "notional",
    "realized_pnl_est",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "null"):
        return default
    try:
        return float(value)
    except Exception:
        return default


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Config file not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def api_base_from_config(cfg: dict, allow_live: bool) -> str:
    paper = cfg.get("alpaca", {}).get("paper", True)

    if paper is not True and not allow_live:
        raise SystemExit(
            "Refusing to use live Alpaca endpoint. "
            "config.yaml has alpaca.paper != true. "
            "Use --allow-live only if you intentionally want live status."
        )

    if paper is True:
        return "https://paper-api.alpaca.markets"

    return "https://api.alpaca.markets"


def alpaca_get(base_url: str, path: str, params: dict | None = None) -> Any:
    key = os.environ.get("APCA_API_KEY_ID", "").strip()
    secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()

    if not key or not secret:
        raise SystemExit(
            "Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY in environment."
        )

    url = base_url + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(
        url,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Alpaca API HTTP {e.code} for {path}:\n{body}") from e
    except Exception as e:
        raise SystemExit(f"Alpaca API request failed for {path}: {e}") from e


def flatten_orders(orders: list[dict]) -> list[dict]:
    """
    Alpaca bracket orders can contain child legs.
    This returns parent orders and child legs as journalable rows.
    """
    out: list[dict] = []

    for order in orders:
        parent_id = order.get("id")
        parent_copy = dict(order)
        parent_copy["_parent_order_id"] = ""
        out.append(parent_copy)

        for leg in order.get("legs") or []:
            leg_copy = dict(leg)
            leg_copy["_parent_order_id"] = parent_id
            out.append(leg_copy)

    return out


def load_existing_journal(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}

    rows: dict[str, dict] = {}

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            oid = row.get("order_id", "")
            if oid:
                rows[oid] = row

    return rows


def estimate_realized_pnl(rows: list[dict]) -> dict[str, float | str]:
    """
    Simple FIFO estimate for long-only filled orders.

    This is an estimate because broker-level realized P&L can differ due to:
    - partial fills
    - fees/adjustments
    - corporate actions
    - order grouping
    """
    filled = []

    for r in rows:
        if r.get("status") != "filled":
            continue

        symbol = r.get("symbol") or ""
        side = r.get("side") or ""
        qty = as_float(r.get("filled_qty"))
        price = as_float(r.get("filled_avg_price"))
        filled_at = r.get("filled_at") or ""

        if not symbol or not side or qty <= 0 or price <= 0 or not filled_at:
            continue

        filled.append((filled_at, r.get("order_id"), symbol, side, qty, price))

    filled.sort(key=lambda x: x[0])

    lots: dict[str, list[list[float]]] = {}
    pnl_by_order: dict[str, float | str] = {}

    for _, order_id, symbol, side, qty, price in filled:
        if not order_id:
            continue

        if side == "buy":
            lots.setdefault(symbol, []).append([qty, price])
            pnl_by_order[order_id] = ""
            continue

        if side != "sell":
            pnl_by_order[order_id] = ""
            continue

        remaining = qty
        realized = 0.0
        lots.setdefault(symbol, [])

        while remaining > 0 and lots[symbol]:
            lot_qty, lot_price = lots[symbol][0]
            matched = min(remaining, lot_qty)
            realized += (price - lot_price) * matched

            lot_qty -= matched
            remaining -= matched

            if lot_qty <= 1e-9:
                lots[symbol].pop(0)
            else:
                lots[symbol][0][0] = lot_qty

        # If no matching buy is found, leave blank instead of lying.
        pnl_by_order[order_id] = realized if remaining < qty else ""

    return pnl_by_order


def order_to_journal_row(order: dict, synced_at: str, realized_pnl: Any = "") -> dict:
    qty = as_float(order.get("filled_qty"))
    price = as_float(order.get("filled_avg_price"))
    notional = qty * price if qty > 0 and price > 0 else ""

    take_profit = order.get("take_profit") or {}
    stop_loss = order.get("stop_loss") or {}

    return {
        "synced_at": synced_at,
        "order_id": order.get("id", ""),
        "parent_order_id": order.get("_parent_order_id", ""),
        "client_order_id": order.get("client_order_id", ""),
        "symbol": order.get("symbol", ""),
        "side": order.get("side", ""),
        "order_type": order.get("type", ""),
        "order_class": order.get("order_class", ""),
        "status": order.get("status", ""),
        "time_in_force": order.get("time_in_force", ""),
        "submitted_at": order.get("submitted_at", ""),
        "filled_at": order.get("filled_at", ""),
        "filled_qty": order.get("filled_qty", ""),
        "filled_avg_price": order.get("filled_avg_price", ""),
        "limit_price": order.get("limit_price", ""),
        "stop_price": order.get("stop_price", ""),
        "take_profit_limit_price": take_profit.get("limit_price", ""),
        "stop_loss_stop_price": stop_loss.get("stop_price", ""),
        "notional": f"{notional:.2f}" if isinstance(notional, float) else "",
        "realized_pnl_est": (
            f"{realized_pnl:.2f}" if isinstance(realized_pnl, float) else ""
        ),
    }


def update_trade_journal(path: str, orders: list[dict]) -> int:
    journal_path = Path(path)
    synced_at = now_iso()

    flat_orders = flatten_orders(orders)
    existing = load_existing_journal(journal_path)

    temp_rows = []
    for order in flat_orders:
        temp_rows.append(
            order_to_journal_row(order=order, synced_at=synced_at, realized_pnl="")
        )

    pnl_estimates = estimate_realized_pnl(temp_rows)

    for order in flat_orders:
        oid = order.get("id", "")
        if not oid:
            continue

        row = order_to_journal_row(
            order=order,
            synced_at=synced_at,
            realized_pnl=pnl_estimates.get(oid, ""),
        )
        existing[oid] = row

    all_rows = list(existing.values())
    all_rows.sort(key=lambda r: (r.get("submitted_at", ""), r.get("order_id", "")))

    with journal_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
        writer.writeheader()
        writer.writerows(all_rows)

    return len(all_rows)


def money(value: Any) -> str:
    return f"${as_float(value):,.2f}"


def print_account(account: dict) -> None:
    print("=" * 80)
    print("ALPACA ACCOUNT")
    print("=" * 80)
    print(f"status:             {account.get('status')}")
    print(f"trading_blocked:    {account.get('trading_blocked')}")
    print(f"account_blocked:    {account.get('account_blocked')}")
    print(f"cash:               {money(account.get('cash'))}")
    print(f"equity:             {money(account.get('equity'))}")
    print(f"buying_power:       {money(account.get('buying_power'))}")
    print(f"portfolio_value:    {money(account.get('portfolio_value'))}")
    print(f"pattern_day_trader: {account.get('pattern_day_trader')}")
    print()


def print_positions(positions: list[dict]) -> None:
    print("=" * 80)
    print("OPEN POSITIONS")
    print("=" * 80)

    if not positions:
        print("No open positions.")
        print()
        return

    print(f"{'Symbol':<8}{'Qty':>12}{'Avg Entry':>14}{'Market Value':>16}{'Unreal P/L':>14}")
    print("-" * 80)

    for p in positions:
        print(
            f"{p.get('symbol', ''):<8}"
            f"{as_float(p.get('qty')):>12.4f}"
            f"{money(p.get('avg_entry_price')):>14}"
            f"{money(p.get('market_value')):>16}"
            f"{money(p.get('unrealized_pl')):>14}"
        )
    print()


def print_orders(orders: list[dict], limit: int = 10) -> None:
    print("=" * 80)
    print(f"RECENT ORDERS latest {limit}")
    print("=" * 80)

    flat = flatten_orders(orders)

    if not flat:
        print("No recent orders.")
        print()
        return

    flat_sorted = sorted(
        flat,
        key=lambda o: o.get("submitted_at") or "",
        reverse=True,
    )

    print(f"{'Submitted':<25}{'Symbol':<8}{'Side':<6}{'Status':<14}{'Qty':>10}{'Fill':>12}")
    print("-" * 80)

    for o in flat_sorted[:limit]:
        print(
            f"{(o.get('submitted_at') or '')[:24]:<25}"
            f"{o.get('symbol', ''):<8}"
            f"{o.get('side', ''):<6}"
            f"{o.get('status', ''):<14}"
            f"{o.get('filled_qty') or o.get('qty') or '':>10}"
            f"{o.get('filled_avg_price') or '':>12}"
        )

    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--journal", default="trade_journal.csv")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    base_url = api_base_from_config(cfg, allow_live=args.allow_live)

    account = alpaca_get(base_url, "/v2/account")
    positions = alpaca_get(base_url, "/v2/positions")
    orders = alpaca_get(
        base_url,
        "/v2/orders",
        {
            "status": "all",
            "limit": args.limit,
            "direction": "desc",
            "nested": "true",
        },
    )

    if not isinstance(positions, list):
        positions = []

    if not isinstance(orders, list):
        orders = []

    print_account(account)
    print_positions(positions)
    print_orders(orders, limit=10)

    count = update_trade_journal(args.journal, orders)
    print("=" * 80)
    print("TRADE JOURNAL")
    print("=" * 80)
    print(f"journal file:       {args.journal}")
    print(f"journal rows:       {count}")
    print(f"synced at:          {now_iso()}")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
