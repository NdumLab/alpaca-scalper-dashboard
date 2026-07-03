#!/usr/bin/env python3
"""
Lightweight Alpaca Scalper Dashboard

Endpoints:
  /          Browser dashboard
  /healthz   Health check
  /api/status JSON status

Uses:
  - config.yaml
  - trade_journal.csv
  - APCA_API_KEY_ID
  - APCA_API_SECRET_KEY

Safe behavior:
  - Refuses to use live endpoint unless config.yaml has alpaca.paper: true
"""

from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from market_events import EventRisk
from market_regime import MarketRegime


PORT = int(os.environ.get("DASHBOARD_PORT", "8080"))
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "config.yaml"))
JOURNAL_PATH = Path(os.environ.get("JOURNAL_PATH", "trade_journal.csv"))
LOG_PATH = Path(os.environ.get("LOG_PATH", "bot.log"))
STATE_PATH = Path(os.environ.get("STATE_PATH", "bot_state.json"))
RUNTIME_DIR = Path(os.environ.get("RUNTIME_DIR", "runtime"))
HEARTBEAT_PATH = RUNTIME_DIR / "heartbeat.json"
PAUSE_PATH = RUNTIME_DIR / "paused"
RESTART_PATH = RUNTIME_DIR / "restart_requested"
ET = ZoneInfo("America/New_York")
MIN_DISPLAY_YEAR = int(os.environ.get("MIN_DISPLAY_YEAR", "2026"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "null"):
        return default
    try:
        return float(value)
    except Exception:
        return default


def money(value: Any) -> str:
    return f"${as_float(value):,.2f}"


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None

    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(ET)


def period_key(dt: datetime, period: str) -> str:
    if period == "week":
        start = dt.date()
        start = start.fromordinal(start.toordinal() - start.weekday())
        return start.isoformat()
    if period == "month":
        return f"{dt.year:04d}-{dt.month:02d}"
    return dt.date().isoformat()


def is_display_year(value: Any) -> bool:
    parsed = parse_timestamp(value)
    return bool(parsed and parsed.year >= MIN_DISPLAY_YEAR)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"error": f"Missing config file: {CONFIG_PATH}"}

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def alpaca_base_url(cfg: dict) -> str:
    paper = cfg.get("alpaca", {}).get("paper", True)

    if paper is not True:
        raise RuntimeError("Refusing to run dashboard against live Alpaca config. Set alpaca.paper: true.")

    return "https://paper-api.alpaca.markets"


def alpaca_get(base_url: str, path: str, params: dict | None = None) -> Any:
    key = os.environ.get("APCA_API_KEY_ID", "").strip()
    secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()

    if not key or not secret:
        raise RuntimeError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY environment variables.")

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

    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def alpaca_request(base_url: str, path: str, method: str, payload: dict | None = None) -> Any:
    key = os.environ.get("APCA_API_KEY_ID", "").strip()
    secret = os.environ.get("APCA_API_SECRET_KEY", "").strip()

    if not key or not secret:
        raise RuntimeError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY environment variables.")

    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url + path,
        data=body,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {"ok": True}


def read_json_file(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def tail_lines(path: Path, limit: int = 80) -> list[str]:
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-limit:]
    except Exception as e:
        return [f"Could not read {path}: {e}"]


def load_runtime() -> dict:
    heartbeat = read_json_file(HEARTBEAT_PATH, {})
    state = read_json_file(STATE_PATH, {})
    hb_time = parse_timestamp(heartbeat.get("time"))
    age_seconds = None
    stale = True
    if hb_time:
        age_seconds = max(0, int((datetime.now(ET) - hb_time).total_seconds()))
        stale = age_seconds > 45

    return {
        "heartbeat": heartbeat,
        "heartbeat_age_seconds": age_seconds,
        "stale": stale,
        "paused": PAUSE_PATH.exists() or bool(heartbeat.get("paused")),
        "state": state,
        "logs": tail_lines(LOG_PATH, 80),
    }


def load_journal() -> dict:
    if not JOURNAL_PATH.exists():
        return {
            "exists": False,
            "rows": 0,
            "realized_pnl_est": 0.0,
            "recent": [],
            "today": [],
            "paired_trades": [],
            "by_symbol": {},
            "by_day": {},
            "by_week": {},
            "by_month": {},
            "daily": [],
        }

    rows = []

    with JOURNAL_PATH.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    visible_rows = [
        row for row in rows
        if is_display_year(row.get("submitted_at") or row.get("synced_at"))
    ]

    realized = 0.0
    by_symbol: dict[str, float] = {}
    by_day: dict[str, float] = {}
    by_week: dict[str, float] = {}
    by_month: dict[str, float] = {}

    for row in visible_rows:
        pnl = as_float(row.get("realized_pnl_est"), 0.0)
        realized += pnl

        symbol = row.get("symbol") or "UNKNOWN"
        by_symbol[symbol] = by_symbol.get(symbol, 0.0) + pnl

        submitted = parse_timestamp(row.get("submitted_at") or row.get("synced_at"))
        if submitted:
            day = period_key(submitted, "day")
            week = period_key(submitted, "week")
            month = period_key(submitted, "month")
            by_day[day] = by_day.get(day, 0.0) + pnl
            by_week[week] = by_week.get(week, 0.0) + pnl
            by_month[month] = by_month.get(month, 0.0) + pnl

    recent = sorted(
        visible_rows,
        key=lambda r: r.get("submitted_at") or r.get("synced_at") or "",
        reverse=True,
    )[:15]

    today = datetime.now(ET).date().isoformat()
    today_rows = [
        row for row in visible_rows
        if (parse_timestamp(row.get("submitted_at") or row.get("synced_at"))
            and parse_timestamp(row.get("submitted_at") or row.get("synced_at")).date().isoformat() == today)
    ]
    today_rows = sorted(
        today_rows,
        key=lambda r: r.get("submitted_at") or r.get("synced_at") or "",
        reverse=True,
    )

    daily = [
        {"day": day, "realized_pnl": round(pnl, 2)}
        for day, pnl in sorted(by_day.items(), reverse=True)
    ][:20]

    paired_trades = build_trade_pairs(visible_rows)

    return {
        "exists": True,
        "rows": len(visible_rows),
        "realized_pnl_est": realized,
        "recent": recent,
        "today": today_rows,
        "paired_trades": paired_trades,
        "by_symbol": by_symbol,
        "by_day": by_day,
        "by_week": by_week,
        "by_month": by_month,
        "daily": daily,
    }


def build_trade_pairs(rows: list[dict]) -> list[dict]:
    filled = [
        row for row in rows
        if row.get("status") == "filled" and as_float(row.get("filled_qty"), 0.0) > 0
    ]
    filled.sort(key=lambda r: r.get("filled_at") or r.get("submitted_at") or "")

    open_entries: dict[str, list[dict]] = {}
    pairs: list[dict] = []

    for row in filled:
        symbol = row.get("symbol") or "UNKNOWN"
        side = (row.get("side") or "").lower()

        if side == "buy":
            open_entries.setdefault(symbol, []).append(row)
            continue

        if side != "sell" or not open_entries.get(symbol):
            continue

        entry = open_entries[symbol].pop(0)
        qty = min(as_float(entry.get("filled_qty")), as_float(row.get("filled_qty")))
        entry_price = as_float(entry.get("filled_avg_price"))
        exit_price = as_float(row.get("filled_avg_price"))
        pnl = (exit_price - entry_price) * qty if qty and entry_price and exit_price else 0.0
        exit_dt = parse_timestamp(row.get("filled_at") or row.get("submitted_at"))

        pairs.append({
            "day": exit_dt.date().isoformat() if exit_dt else "",
            "symbol": symbol,
            "qty": int(qty) if qty else "",
            "entry_time": entry.get("filled_at") or entry.get("submitted_at"),
            "entry": round(entry_price, 4) if entry_price else "",
            "exit_time": row.get("filled_at") or row.get("submitted_at"),
            "exit": round(exit_price, 4) if exit_price else "",
            "pnl": round(pnl, 2),
        })

    return sorted(pairs, key=lambda r: r.get("exit_time") or "", reverse=True)[:20]


def build_pnl_summary(journal: dict, positions: list[dict]) -> dict:
    now = datetime.now(ET)
    today = period_key(now, "day")
    week = period_key(now, "week")
    month = period_key(now, "month")
    open_pnl = sum(as_float(p.get("unrealized_pl"), 0.0) for p in positions)

    def period(realized_by: dict, key: str) -> dict:
        realized = as_float(realized_by.get(key), 0.0)
        return {
            "realized_pnl": round(realized, 2),
            "open_pnl": round(open_pnl, 2),
            "live_pnl": round(realized + open_pnl, 2),
        }

    daily = []
    for row in journal.get("daily", []):
        day = row["day"]
        realized = as_float(row.get("realized_pnl"), 0.0)
        day_open = open_pnl if day == today else 0.0
        daily.append({
            "day": day,
            "realized_pnl": round(realized, 2),
            "open_pnl": round(day_open, 2),
            "live_pnl": round(realized + day_open, 2),
        })

    return {
        "today": {"key": today, **period(journal.get("by_day", {}), today)},
        "week": {"key": week, **period(journal.get("by_week", {}), week)},
        "month": {"key": month, **period(journal.get("by_month", {}), month)},
        "daily": daily,
    }


def build_risk_exposure(account: dict, positions: list[dict], cfg: dict, runtime: dict,
                        pnl_summary: dict) -> dict:
    risk_cfg = cfg.get("risk", {})
    state = runtime.get("state", {})
    equity = as_float(account.get("equity"))
    daily_loss_limit = equity * as_float(risk_cfg.get("max_daily_loss_pct"), 0.0) / 100
    today_live = as_float(pnl_summary.get("today", {}).get("live_pnl"), 0.0)
    remaining_loss = max(0.0, daily_loss_limit + today_live)
    market_value = sum(abs(as_float(p.get("market_value"), 0.0)) for p in positions)
    open_pnl = sum(as_float(p.get("unrealized_pl"), 0.0) for p in positions)
    exposure_pct = (market_value / equity * 100) if equity else 0.0

    return {
        "open_positions": len(positions),
        "market_value": round(market_value, 2),
        "portfolio_exposure_pct": round(exposure_pct, 2),
        "open_pnl": round(open_pnl, 2),
        "daily_loss_limit": round(daily_loss_limit, 2),
        "daily_loss_remaining": round(remaining_loss, 2),
        "daily_trades_used": int(state.get("daily_trade_count", 0) or 0),
        "max_daily_trades": int(risk_cfg.get("max_daily_trades", 0) or 0),
        "halted": bool(state.get("halted", False)),
    }


def handle_control(action: str) -> dict:
    cfg = load_config()
    if "error" in cfg:
        raise RuntimeError(cfg["error"])

    base_url = alpaca_base_url(cfg)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    if action == "pause":
        PAUSE_PATH.write_text(datetime.now(ET).isoformat(timespec="seconds"), encoding="utf-8")
        return {"ok": True, "message": "Bot paused. Existing Alpaca orders/positions are unchanged."}

    if action == "resume":
        if PAUSE_PATH.exists():
            PAUSE_PATH.unlink()
        return {"ok": True, "message": "Bot resumed."}

    if action == "restart":
        RESTART_PATH.write_text(datetime.now(ET).isoformat(timespec="seconds"), encoding="utf-8")
        return {"ok": True, "message": "Restart requested. Compose restart policy should bring the bot back."}

    if action == "flatten":
        cancel_result = alpaca_request(base_url, "/v2/orders", "DELETE")
        close_result = alpaca_request(base_url, "/v2/positions?cancel_orders=true", "DELETE")
        return {
            "ok": True,
            "message": "Flatten requested: canceled orders and requested all paper positions closed.",
            "cancel_result": cancel_result,
            "close_result": close_result,
        }

    raise RuntimeError(f"Unknown control action: {action}")


def collect_status() -> dict:
    cfg = load_config()

    if "error" in cfg:
        return {
            "ok": False,
            "time": utc_now(),
            "error": cfg["error"],
        }

    base_url = alpaca_base_url(cfg)

    account = alpaca_get(base_url, "/v2/account")
    positions = alpaca_get(base_url, "/v2/positions")
    orders = alpaca_get(
        base_url,
        "/v2/orders",
        {
            "status": "all",
            "limit": 25,
            "direction": "desc",
            "nested": "true",
        },
    )

    if not isinstance(positions, list):
        positions = []

    if not isinstance(orders, list):
        orders = []

    orders = [
        order for order in orders
        if is_display_year(order.get("submitted_at"))
    ]

    journal = load_journal()
    pnl_summary = build_pnl_summary(journal, positions)
    runtime = load_runtime()
    risk_exposure = build_risk_exposure(account, positions, cfg, runtime, pnl_summary)
    event_risk = EventRisk(cfg).status(datetime.now(ET))
    market_regime = runtime.get("heartbeat", {}).get("market_regime") or MarketRegime(cfg).status()
    today = datetime.now(ET).date().isoformat()
    today_orders = [
        order for order in orders
        if (parse_timestamp(order.get("submitted_at"))
            and parse_timestamp(order.get("submitted_at")).date().isoformat() == today)
    ]

    return {
        "ok": True,
        "time": utc_now(),
        "mode": "paper" if cfg.get("alpaca", {}).get("paper", True) else "live",
        "account": {
            "status": account.get("status"),
            "trading_blocked": account.get("trading_blocked"),
            "account_blocked": account.get("account_blocked"),
            "cash": account.get("cash"),
            "equity": account.get("equity"),
            "buying_power": account.get("buying_power"),
            "portfolio_value": account.get("portfolio_value"),
            "pattern_day_trader": account.get("pattern_day_trader"),
        },
        "positions": positions,
        "orders": orders,
        "today_orders": today_orders,
        "journal": journal,
        "pnl_summary": pnl_summary,
        "runtime": runtime,
        "risk_exposure": risk_exposure,
        "event_risk": event_risk,
        "market_regime": market_regime,
        "config": {
            "symbols": cfg.get("symbols", []),
            "risk": cfg.get("risk", {}),
            "strategy": cfg.get("strategy", {}),
            "event_risk": cfg.get("event_risk", {}),
            "market_regime": cfg.get("market_regime", {}),
        },
    }


def html_page() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Alpaca Scalper Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      background: #0f172a;
      color: #e5e7eb;
    }
    header {
      padding: 20px;
      background: #111827;
      border-bottom: 1px solid #334155;
    }
    h1 {
      margin: 0;
      font-size: 24px;
    }
    .sub {
      color: #94a3b8;
      margin-top: 6px;
    }
    main {
      padding: 20px;
      display: grid;
      gap: 16px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }
    .card {
      background: #111827;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    }
    .label {
      color: #94a3b8;
      font-size: 13px;
    }
    .value {
      font-size: 24px;
      margin-top: 6px;
      font-weight: bold;
    }
    .value.small {
      font-size: 18px;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }
    button {
      border: 1px solid #475569;
      background: #1e293b;
      color: #e5e7eb;
      border-radius: 8px;
      padding: 9px 12px;
      cursor: pointer;
      font-weight: 700;
    }
    button:hover { background: #334155; }
    button.danger {
      border-color: #ef4444;
      color: #fecaca;
    }
    .pill {
      display: inline-block;
      border: 1px solid #475569;
      border-radius: 999px;
      padding: 4px 9px;
      margin: 4px 6px 0 0;
      color: #cbd5e1;
      background: #020617;
      font-size: 13px;
    }
    .good { color: #22c55e; }
    .bad { color: #ef4444; }
    .warn { color: #f59e0b; }
    .muted { color: #94a3b8; }
    .side-buy { color: #38bdf8; font-weight: 700; }
    .side-sell { color: #f472b6; font-weight: 700; }
    .status-filled { color: #22c55e; font-weight: 700; }
    .status-canceled, .status-expired { color: #94a3b8; }
    .status-new, .status-accepted, .status-pending_new {
      color: #f59e0b;
      font-weight: 700;
    }
    .pnl-positive { color: #22c55e; font-weight: 700; }
    .pnl-negative { color: #ef4444; font-weight: 700; }
    .pnl-empty { color: #94a3b8; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      padding: 8px;
      border-bottom: 1px solid #334155;
      text-align: left;
    }
    th {
      color: #93c5fd;
      font-weight: 600;
    }
    .date-row td {
      background: #1e293b;
      color: #bfdbfe;
      font-weight: 700;
      letter-spacing: 0;
      padding-top: 12px;
      padding-bottom: 12px;
      border-top: 1px solid #60a5fa;
      border-bottom: 1px solid #60a5fa;
    }
    code {
      color: #93c5fd;
    }
    pre {
      white-space: pre-wrap;
      overflow-x: auto;
      background: #020617;
      padding: 12px;
      border-radius: 8px;
      border: 1px solid #334155;
    }
    .log-lines {
      max-height: 340px;
      overflow: auto;
      font-size: 13px;
      line-height: 1.45;
    }
  </style>
</head>
<body>
  <header>
    <h1>Alpaca Scalper Dashboard</h1>
    <div class="sub">Paper trading monitor. Auto-refreshes every 10 seconds.</div>
  </header>

  <main>
    <div id="error"></div>

    <section class="grid">
      <div class="card">
        <div class="label">Bot heartbeat</div>
        <div class="value" id="bot_status">...</div>
        <div class="sub" id="bot_heartbeat">...</div>
      </div>
      <div class="card">
        <div class="label">Paused</div>
        <div class="value" id="paused">...</div>
      </div>
      <div class="card">
        <div class="label">Last refresh</div>
        <div class="value small" id="last_refresh">...</div>
      </div>
      <div class="card">
        <div class="label">Notifications</div>
        <div class="actions">
          <button onclick="enableNotifications()">Enable alerts</button>
        </div>
      </div>
    </section>

    <section class="card">
      <h2>Controls</h2>
      <div class="actions">
        <button onclick="controlBot('pause')">Pause entries</button>
        <button onclick="controlBot('resume')">Resume entries</button>
        <button onclick="controlBot('restart')">Restart bot</button>
        <button class="danger" onclick="confirmControl('flatten', 'Cancel all paper orders and close all paper positions?')">Flatten all</button>
      </div>
      <div class="sub" id="control_result"></div>
    </section>

    <section class="grid">
      <div class="card">
        <div class="label">Mode</div>
        <div class="value" id="mode">...</div>
      </div>
      <div class="card">
        <div class="label">Equity</div>
        <div class="value" id="equity">...</div>
      </div>
      <div class="card">
        <div class="label">Buying power</div>
        <div class="value" id="buying_power">...</div>
      </div>
      <div class="card">
        <div class="label">Journal realized P&L estimate</div>
        <div class="value" id="journal_pnl">...</div>
      </div>
      <div class="card">
        <div class="label">Portfolio exposed</div>
        <div class="value" id="portfolio_exposed">...</div>
        <div class="sub" id="portfolio_exposed_pct">...</div>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <div class="label">Today realized P&L</div>
        <div class="value" id="today_realized">...</div>
      </div>
      <div class="card">
        <div class="label">Today live P&L</div>
        <div class="value" id="today_live">...</div>
      </div>
      <div class="card">
        <div class="label">Week live P&L</div>
        <div class="value" id="week_live">...</div>
      </div>
      <div class="card">
        <div class="label">Week realized P&L</div>
        <div class="value" id="week_realized">...</div>
      </div>
      <div class="card">
        <div class="label">Month live P&L</div>
        <div class="value" id="month_live">...</div>
      </div>
      <div class="card">
        <div class="label">Month realized P&L</div>
        <div class="value" id="month_realized">...</div>
      </div>
    </section>

    <section class="card">
      <h2>Daily P&L</h2>
      <div id="daily_pnl"></div>
    </section>

    <section class="card">
      <h2>Risk Exposure</h2>
      <div id="risk_exposure"></div>
    </section>

    <section class="card">
      <h2>Market Events</h2>
      <div id="event_risk"></div>
    </section>

    <section class="card">
      <h2>Market Regime</h2>
      <div id="market_regime"></div>
    </section>

    <section class="card">
      <h2>Today Orders</h2>
      <div id="today_orders"></div>
    </section>

    <section class="card">
      <h2>Today Journal Rows</h2>
      <div id="today_journal"></div>
    </section>

    <section class="card">
      <h2>Symbols</h2>
      <div id="symbols"></div>
    </section>

    <section class="card">
      <h2>Open Positions</h2>
      <div id="positions"></div>
    </section>

    <section class="card">
      <h2>Paired Trades</h2>
      <div id="paired_trades"></div>
    </section>

    <section class="card">
      <h2>Recent Orders</h2>
      <div id="orders"></div>
    </section>

    <section class="card">
      <h2>Recent Journal Rows</h2>
      <div id="journal"></div>
    </section>

    <section class="card">
      <h2>Latest Bot Events</h2>
      <pre class="log-lines" id="bot_logs"></pre>
    </section>

    <section class="card">
      <h2>Risk Settings</h2>
      <pre id="risk"></pre>
    </section>

    <section class="card">
      <h2>Strategy Settings</h2>
      <pre id="strategy"></pre>
    </section>
  </main>

<script>
function money(x) {
  const n = Number(x || 0);
  return "$" + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

let previousSignature = null;
let previousBotStale = null;

function pnlClass(value) {
  return Number(value || 0) >= 0 ? "value good" : "value bad";
}

function setPnl(id, value) {
  const el = document.getElementById(id);
  el.textContent = money(value);
  el.className = pnlClass(value);
}

function safe(v) {
  return v === null || v === undefined || v === "" ? "-" : v;
}

function formatEt(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  const date = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(parsed);
  const time = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(parsed);
  return date + " " + time + " ET";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cellValue(row, key) {
  return safe(row[key]);
}

function statusClass(value) {
  return "status-" + String(value || "").toLowerCase().replaceAll(" ", "_");
}

function formatCell(row, header) {
  const value = cellValue(row, header.key);
  const display = header.time ? formatEt(value) : value;
  const escaped = escapeHtml(display);

  if (value === "-") {
    return '<span class="muted">-</span>';
  }

  if (header.key === "side") {
    const side = String(value).toLowerCase();
    if (side === "buy" || side === "sell") {
      return '<span class="side-' + side + '">' + escaped + '</span>';
    }
  }

  if (header.key === "status") {
    return '<span class="' + statusClass(value) + '">' + escaped + '</span>';
  }

  if (header.money) {
    const n = Number(value);
    if (Number.isNaN(n)) {
      return '<span class="pnl-empty">' + escaped + '</span>';
    }
    const cls = n >= 0 ? "pnl-positive" : "pnl-negative";
    return '<span class="' + cls + '">' + escapeHtml(money(n)) + '</span>';
  }

  if (header.key === "realized_pnl_est" || header.key === "unrealized_pl") {
    const n = Number(value);
    if (Number.isNaN(n)) {
      return '<span class="pnl-empty">' + escaped + '</span>';
    }
    const cls = n >= 0 ? "pnl-positive" : "pnl-negative";
    return '<span class="' + cls + '">' + escaped + '</span>';
  }

  return escaped;
}

function table(headers, rows) {
  if (!rows || rows.length === 0) {
    return "<p>No rows.</p>";
  }

  let h = "<table><thead><tr>";
  for (const header of headers) {
    h += "<th>" + header.label + "</th>";
  }
  h += "</tr></thead><tbody>";

  for (const row of rows) {
    h += "<tr>";
    for (const header of headers) {
      h += "<td>" + formatCell(row, header) + "</td>";
    }
    h += "</tr>";
  }

  h += "</tbody></table>";
  return h;
}

function tradingDate(value) {
  if (!value) {
    return "Unknown date";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).split("T")[0] || "Unknown date";
  }

  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(parsed);
}

function datedTable(headers, rows) {
  if (!rows || rows.length === 0) {
    return "<p>No rows.</p>";
  }

  let h = "<table><thead><tr>";
  for (const header of headers) {
    h += "<th>" + header.label + "</th>";
  }
  h += "</tr></thead><tbody>";

  let lastDate = null;
  for (const row of rows) {
    const rowDate = tradingDate(row.submitted_at || row.synced_at || row.exit_time || row.entry_time || row.day);
    if (rowDate !== lastDate) {
      h += '<tr class="date-row"><td colspan="' + headers.length + '">Trading day: ' + escapeHtml(rowDate) + '</td></tr>';
      lastDate = rowDate;
    }

    h += "<tr>";
    for (const header of headers) {
      h += "<td>" + formatCell(row, header) + "</td>";
    }
    h += "</tr>";
  }

  h += "</tbody></table>";
  return h;
}

function keyValueTable(items) {
  return table(
    [
      {key: "label", label: "Metric"},
      {key: "value", label: "Value", money: false}
    ],
    items
  );
}

function notify(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") {
    return;
  }
  new Notification(title, {body});
}

async function enableNotifications() {
  if (!("Notification" in window)) {
    document.getElementById("control_result").textContent = "This browser does not support notifications.";
    return;
  }
  const result = await Notification.requestPermission();
  document.getElementById("control_result").textContent = "Notification permission: " + result;
}

function maybeNotify(data) {
  const latestOrder = data.orders && data.orders.length ? data.orders[0] : null;
  const signature = JSON.stringify({
    order: latestOrder ? latestOrder.id + ":" + latestOrder.status : "",
    positions: (data.positions || []).map(p => p.symbol + ":" + p.qty + ":" + p.unrealized_pl).join("|")
  });

  if (previousSignature && signature !== previousSignature) {
    notify("Alpaca bot update", latestOrder ? latestOrder.symbol + " " + latestOrder.side + " " + latestOrder.status : "Position state changed");
  }
  previousSignature = signature;

  if (previousBotStale === false && data.runtime.stale) {
    notify("Alpaca bot heartbeat stale", "No fresh bot heartbeat detected.");
  }
  previousBotStale = data.runtime.stale;
}

async function controlBot(action) {
  const res = await fetch("/api/control", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action})
  });
  const data = await res.json();
  document.getElementById("control_result").textContent = data.message || data.error || JSON.stringify(data);
  await loadStatus();
}

function confirmControl(action, message) {
  if (window.confirm(message)) {
    controlBot(action);
  }
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    if (!data.ok) {
      document.getElementById("error").innerHTML =
        '<div class="card bad"><b>Error:</b> ' + data.error + '</div>';
      return;
    }

    document.getElementById("error").innerHTML = "";
    maybeNotify(data);

    const statusText = data.runtime.stale ? "STALE" : "LIVE";
    document.getElementById("bot_status").textContent = statusText;
    document.getElementById("bot_status").className = data.runtime.stale ? "value bad" : "value good";
    document.getElementById("bot_heartbeat").textContent =
      "Heartbeat age: " + safe(data.runtime.heartbeat_age_seconds) + "s";
    document.getElementById("paused").textContent = data.runtime.paused ? "YES" : "NO";
    document.getElementById("paused").className = data.runtime.paused ? "value warn" : "value good";
    document.getElementById("last_refresh").textContent = formatEt(data.time);

    document.getElementById("mode").textContent = data.mode.toUpperCase();
    document.getElementById("mode").className = data.mode === "paper" ? "value good" : "value bad";

    document.getElementById("equity").textContent = money(data.account.equity);
    document.getElementById("buying_power").textContent = money(data.account.buying_power);
    document.getElementById("portfolio_exposed").textContent = money(data.risk_exposure.market_value);
    document.getElementById("portfolio_exposed").className =
      data.risk_exposure.portfolio_exposure_pct > 0 ? "value warn" : "value good";
    document.getElementById("portfolio_exposed_pct").textContent =
      data.risk_exposure.portfolio_exposure_pct.toFixed(2) + "% of equity";

    const pnl = Number(data.journal.realized_pnl_est || 0);
    document.getElementById("journal_pnl").textContent = money(pnl);
    document.getElementById("journal_pnl").className = pnl >= 0 ? "value good" : "value bad";

    setPnl("today_realized", data.pnl_summary.today.realized_pnl);
    setPnl("today_live", data.pnl_summary.today.live_pnl);
    setPnl("week_realized", data.pnl_summary.week.realized_pnl);
    setPnl("week_live", data.pnl_summary.week.live_pnl);
    setPnl("month_realized", data.pnl_summary.month.realized_pnl);
    setPnl("month_live", data.pnl_summary.month.live_pnl);

    document.getElementById("risk").textContent = JSON.stringify(data.config.risk, null, 2);
    document.getElementById("strategy").textContent = JSON.stringify(data.config.strategy, null, 2);
    document.getElementById("symbols").innerHTML = data.config.symbols.map(s => "<code>" + s + "</code>").join(" ");

    document.getElementById("daily_pnl").innerHTML = table(
      [
        {key: "day", label: "Trading day"},
        {key: "realized_pnl", label: "Realized P&L", money: true},
        {key: "open_pnl", label: "Open P&L", money: true},
        {key: "live_pnl", label: "Live P&L", money: true}
      ],
      data.pnl_summary.daily
    );

    document.getElementById("risk_exposure").innerHTML = keyValueTable([
      {label: "Open positions", value: data.risk_exposure.open_positions},
      {label: "Open market value", value: money(data.risk_exposure.market_value)},
      {label: "Portfolio exposed", value: data.risk_exposure.portfolio_exposure_pct.toFixed(2) + "%"},
      {label: "Open P&L", value: money(data.risk_exposure.open_pnl)},
      {label: "Daily loss limit", value: money(data.risk_exposure.daily_loss_limit)},
      {label: "Daily loss remaining", value: money(data.risk_exposure.daily_loss_remaining)},
      {label: "Trades today", value: data.risk_exposure.daily_trades_used + " / " + data.risk_exposure.max_daily_trades},
      {label: "Halted", value: data.risk_exposure.halted ? "YES" : "NO"}
    ]);

    document.getElementById("event_risk").innerHTML = keyValueTable([
      {label: "Enabled", value: data.event_risk.enabled ? "YES" : "NO"},
      {label: "Block new entries", value: data.event_risk.block_new_entries ? "YES" : "NO"},
      {label: "Minimum impact", value: data.event_risk.min_impact},
      {label: "Active blocks", value: (data.event_risk.active || []).map(e => e.name).join(", ") || "-"}
    ]) + table(
      [
        {key: "starts_at", label: "Event time", time: true},
        {key: "name", label: "Name"},
        {key: "impact", label: "Impact"},
        {key: "symbols", label: "Symbols"},
        {key: "window_start", label: "Block starts", time: true},
        {key: "window_end", label: "Block ends", time: true}
      ],
      (data.event_risk.upcoming || []).map(e => ({
        ...e,
        symbols: (e.symbols || []).join(", ")
      }))
    );

    const regimeSymbols = data.market_regime.symbols || {};
    document.getElementById("market_regime").innerHTML = keyValueTable([
      {label: "Enabled", value: data.market_regime.enabled ? "YES" : "NO"},
      {label: "Allowed", value: data.market_regime.allowed === false ? "NO" : "YES"},
      {label: "Passing", value: safe(data.market_regime.passing) + " / " + safe(data.market_regime.required)}
    ]) + table(
      [
        {key: "symbol", label: "Symbol"},
        {key: "pass", label: "Pass"},
        {key: "reason", label: "Reason"}
      ],
      Object.keys(regimeSymbols).map(sym => ({
        symbol: sym,
        pass: regimeSymbols[sym].pass ? "YES" : "NO",
        reason: regimeSymbols[sym].reason
      }))
    );

    document.getElementById("today_orders").innerHTML = table(
      [
        {key: "submitted_at", label: "Submitted", time: true},
        {key: "symbol", label: "Symbol"},
        {key: "side", label: "Side"},
        {key: "status", label: "Status"},
        {key: "filled_qty", label: "Filled qty"},
        {key: "filled_avg_price", label: "Fill price"}
      ],
      data.today_orders
    );

    document.getElementById("today_journal").innerHTML = table(
      [
        {key: "submitted_at", label: "Submitted", time: true},
        {key: "symbol", label: "Symbol"},
        {key: "side", label: "Side"},
        {key: "status", label: "Status"},
        {key: "filled_qty", label: "Filled qty"},
        {key: "filled_avg_price", label: "Fill price"},
        {key: "realized_pnl_est", label: "P&L est"}
      ],
      data.journal.today
    );

    document.getElementById("positions").innerHTML = table(
      [
        {key: "symbol", label: "Symbol"},
        {key: "qty", label: "Qty"},
        {key: "avg_entry_price", label: "Avg entry"},
        {key: "market_value", label: "Market value"},
        {key: "unrealized_pl", label: "Unrealized P/L"}
      ],
      data.positions
    );

    document.getElementById("paired_trades").innerHTML = datedTable(
      [
        {key: "exit_time", label: "Exit time", time: true},
        {key: "symbol", label: "Symbol"},
        {key: "qty", label: "Qty"},
        {key: "entry", label: "Entry"},
        {key: "exit", label: "Exit"},
        {key: "pnl", label: "P&L", money: true}
      ],
      data.journal.paired_trades
    );

    document.getElementById("orders").innerHTML = datedTable(
      [
        {key: "submitted_at", label: "Submitted", time: true},
        {key: "symbol", label: "Symbol"},
        {key: "side", label: "Side"},
        {key: "status", label: "Status"},
        {key: "filled_qty", label: "Filled qty"},
        {key: "filled_avg_price", label: "Fill price"}
      ],
      data.orders
    );

    document.getElementById("journal").innerHTML = datedTable(
      [
        {key: "submitted_at", label: "Submitted", time: true},
        {key: "symbol", label: "Symbol"},
        {key: "side", label: "Side"},
        {key: "status", label: "Status"},
        {key: "filled_qty", label: "Filled qty"},
        {key: "filled_avg_price", label: "Fill price"},
        {key: "realized_pnl_est", label: "P&L est"}
      ],
      data.journal.recent
    );

    document.getElementById("bot_logs").textContent = (data.runtime.logs || []).join("\\n");

  } catch (err) {
    document.getElementById("error").innerHTML =
      '<div class="card bad"><b>Dashboard error:</b> ' + err + '</div>';
  }
}

loadStatus();
setInterval(loadStatus, 10000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self.send_json({"ok": True, "time": utc_now()})
            return

        if self.path == "/api/status":
            try:
                self.send_json(collect_status())
            except Exception as e:
                self.send_json({"ok": False, "time": utc_now(), "error": str(e)}, status=500)
            return

        if self.path == "/":
            self.send_html(html_page())
            return

        self.send_json({"ok": False, "error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/api/control":
            self.send_json({"ok": False, "error": "not found"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw or "{}")
            action = str(payload.get("action", "")).strip()
            self.send_json(handle_control(action))
        except Exception as e:
            self.send_json({"ok": False, "time": utc_now(), "error": str(e)}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print("[%s] %s" % (utc_now(), fmt % args), flush=True)


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Dashboard listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
