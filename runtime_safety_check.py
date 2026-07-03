from pathlib import Path
import ast
import yaml

print("=" * 80)
print("RUNTIME SAFETY CHECK")
print("=" * 80)

cfg = yaml.safe_load(open("config.yaml"))

print("\nCONFIG:")
print(f"paper mode:                 {cfg.get('alpaca', {}).get('paper')}")
print(f"symbols:                    {cfg.get('symbols')}")
print(f"max_position_pct:           {cfg.get('risk', {}).get('max_position_pct')}")
print(f"take_profit_r:              {cfg.get('risk', {}).get('take_profit_r')}")
print(f"stop_atr_mult:              {cfg.get('risk', {}).get('stop_atr_mult')}")
print(f"max_daily_loss_pct:         {cfg.get('risk', {}).get('max_daily_loss_pct')}")
print(f"max_daily_trades:           {cfg.get('risk', {}).get('max_daily_trades')}")
print(f"max_concurrent_positions:   {cfg.get('risk', {}).get('max_concurrent_positions')}")
print(f"bar_minutes:                {cfg.get('strategy', {}).get('bar_minutes')}")
print(f"warmup_bars:                {cfg.get('strategy', {}).get('warmup_bars')}")
print(f"event_risk_enabled:         {cfg.get('event_risk', {}).get('enabled', False)}")
print(f"market_regime_enabled:      {cfg.get('market_regime', {}).get('enabled', False)}")

print("\nPYTHON FILES:")
py_files = sorted(Path(".").glob("*.py"))
for p in py_files:
    print(f"{p.name:<35} OK")

print("\nIMPORT CHECK:")
available_modules = {p.stem for p in py_files}
missing_local_imports = []

for p in py_files:
    try:
        tree = ast.parse(p.read_text())
    except Exception as e:
        print(f"{p.name:<35} PARSE ERROR: {e}")
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in available_modules:
                continue
            if node.module in ["executor"]:
                missing_local_imports.append((p.name, node.module))

        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in ["executor"] and root not in available_modules:
                    missing_local_imports.append((p.name, root))

if missing_local_imports:
    print("Missing local imports found:")
    for filename, module in missing_local_imports:
        print(f"  {filename} imports missing module: {module}")
else:
    print("No missing executor.py import found.")

print("\nORDER EXECUTION KEYWORD CHECK:")
keywords = [
    "submit_order",
    "filled_avg_price",
    "TradingClient",
    "StockDataStream",
    "get_order",
    "bracket",
    "take_profit",
    "stop_loss",
]

for kw in keywords:
    hits = []
    for p in py_files:
        text = p.read_text(errors="ignore")
        if kw in text:
            hits.append(p.name)

    print(f"{kw:<25}: {', '.join(sorted(set(hits))) if hits else 'NOT FOUND'}")

print("\nSAFETY INTERPRETATION:")
if cfg.get("alpaca", {}).get("paper") is True:
    print("PASS: paper mode is enabled.")
else:
    print("DANGER: paper mode is not enabled.")

if cfg.get("risk", {}).get("max_concurrent_positions") == 1:
    print("PASS: max_concurrent_positions is 1.")
else:
    print("CHECK: max_concurrent_positions is not 1.")

if cfg.get("risk", {}).get("max_daily_loss_pct", 999) <= 5:
    print("PASS: max_daily_loss_pct is 5% or lower.")
else:
    print("CHECK: max_daily_loss_pct is above 5%.")

print("=" * 80)
