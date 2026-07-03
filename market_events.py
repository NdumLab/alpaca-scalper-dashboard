"""Planned market-event risk controls.

The first version is intentionally local and deterministic: events are loaded
from config.yaml, then used to block new entries around known high-impact
windows. External calendar/news ingestion can feed the same schema later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
IMPACT_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class PlannedEvent:
    name: str
    starts_at: datetime
    impact: str
    symbols: tuple[str, ...]
    pre_minutes: int
    post_minutes: int
    action: str
    source: str = "config"

    def applies_to(self, symbol: str) -> bool:
        return "*" in self.symbols or symbol in self.symbols

    def window(self) -> tuple[datetime, datetime]:
        return (
            self.starts_at - timedelta(minutes=self.pre_minutes),
            self.starts_at + timedelta(minutes=self.post_minutes),
        )

    def is_active_for(self, ts: datetime, symbol: str) -> bool:
        if not self.applies_to(symbol):
            return False
        start, end = self.window()
        ts_et = ts.astimezone(ET)
        return start <= ts_et <= end

    def as_dict(self, now: datetime | None = None) -> dict:
        start, end = self.window()
        now_et = (now or datetime.now(ET)).astimezone(ET)
        return {
            "name": self.name,
            "starts_at": self.starts_at.isoformat(),
            "impact": self.impact,
            "symbols": list(self.symbols),
            "pre_minutes": self.pre_minutes,
            "post_minutes": self.post_minutes,
            "action": self.action,
            "source": self.source,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "active": start <= now_et <= end,
        }


class EventRisk:
    def __init__(self, cfg: dict):
        self.cfg = cfg.get("event_risk", {}) or {}
        self.enabled = bool(self.cfg.get("enabled", False))
        self.block_new_entries = bool(self.cfg.get("block_new_entries", True))
        self.min_impact = str(self.cfg.get("min_impact", "high")).lower()
        self.events = self._load_events()

    def _load_events(self) -> list[PlannedEvent]:
        events = []
        default_pre = int(self.cfg.get("default_pre_minutes", 30))
        default_post = int(self.cfg.get("default_post_minutes", 15))
        default_action = str(self.cfg.get("default_action", "block_entries"))

        for raw in self.cfg.get("planned_events", []) or []:
            starts_at = self._parse_time(raw.get("time") or raw.get("starts_at"))
            if starts_at is None:
                continue

            impact = str(raw.get("impact", "high")).lower()
            symbols = raw.get("symbols", ["*"]) or ["*"]
            if isinstance(symbols, str):
                symbols = [symbols]
            events.append(PlannedEvent(
                name=str(raw.get("name") or raw.get("event") or "planned event"),
                starts_at=starts_at,
                impact=impact,
                symbols=tuple(str(s).upper() if s != "*" else "*" for s in symbols),
                pre_minutes=int(raw.get("pre_minutes", default_pre)),
                post_minutes=int(raw.get("post_minutes", default_post)),
                action=str(raw.get("action", default_action)),
                source=str(raw.get("source", "config")),
            ))
        return sorted(events, key=lambda item: item.starts_at)

    @staticmethod
    def _parse_time(value) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ET)
        return parsed.astimezone(ET)

    def blocks_entry(self, ts: datetime, symbol: str) -> bool:
        if not self.enabled or not self.block_new_entries:
            return False
        return bool(self.active_blocks(ts, symbol))

    def active_blocks(self, ts: datetime, symbol: str) -> list[PlannedEvent]:
        if not self.enabled:
            return []
        threshold = IMPACT_RANK.get(self.min_impact, IMPACT_RANK["high"])
        symbol = symbol.upper()
        return [
            event for event in self.events
            if event.action == "block_entries"
            and IMPACT_RANK.get(event.impact, 0) >= threshold
            and event.is_active_for(ts, symbol)
        ]

    def upcoming(self, now: datetime | None = None, limit: int = 8) -> list[dict]:
        now_et = (now or datetime.now(ET)).astimezone(ET)
        return [
            event.as_dict(now_et)
            for event in self.events
            if event.window()[1] >= now_et
        ][:limit]

    def status(self, now: datetime | None = None) -> dict:
        now_et = (now or datetime.now(ET)).astimezone(ET)
        active = [
            event.as_dict(now_et)
            for event in self.events
            if event.window()[0] <= now_et <= event.window()[1]
        ]
        return {
            "enabled": self.enabled,
            "block_new_entries": self.block_new_entries,
            "min_impact": self.min_impact,
            "active": active,
            "upcoming": self.upcoming(now_et),
        }
