from experiment import load_events, split, base_cfg, run, summary
events = load_events(); is_ev, oos_ev = split(events)
tuned = {"risk.take_profit_r": 3.0, "risk.stop_atr_mult": 2.5,
         "strategy.volume_surge_mult": 2.5, "strategy.rsi_max_entry": 70,
         "strategy.cross_confirm_bars": 3}
cfg = base_cfg(**tuned)
print("TUNED MOMENTUM (picked on IS only):")
summary("  IS  (Dec-Apr)", run(cfg, is_ev))
summary("  OOS (Apr-Jun)", run(cfg, oos_ev))
print("\nTUNED + SPY/QQQ only (tightest spreads, a-priori choice):")
summary("  IS  (Dec-Apr)", run(cfg, is_ev, symbols=["SPY","QQQ"]))
summary("  OOS (Apr-Jun)", run(cfg, oos_ev, symbols=["SPY","QQQ"]))
print("\nBASELINE for reference:")
summary("  IS  (Dec-Apr)", run(base_cfg(), is_ev))
summary("  OOS (Apr-Jun)", run(base_cfg(), oos_ev))
