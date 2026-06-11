import itertools, json
from experiment import load_events, split, base_cfg, run
events = load_events(); is_ev, _ = split(events)
results = []
for dev, rsi_min, tp_r, stop_m in itertools.product(
        (1.0, 1.5), (25, 30), (1.0, 1.5, 2.0), (1.0, 2.5)):
    cfg = base_cfg(**{"strategy.mode": "reversion", "strategy.vwap_dev_atr": dev,
                      "strategy.rsi_min_entry": rsi_min,
                      "risk.take_profit_r": tp_r, "risk.stop_atr_mult": stop_m})
    s = run(cfg, is_ev)
    results.append([round(s["net"],2), s["n"], round(s["win_rate"],1),
                    round(s["profit_factor"],2), round(s["max_drawdown"],2),
                    dev, rsi_min, tp_r, stop_m])
    print("done", dev, rsi_min, tp_r, stop_m, flush=True)
results.sort(reverse=True)
json.dump(results, open("sweep_rev.json","w"), indent=0)
