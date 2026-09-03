"""
For the hackathon MVP, market events are drawn from a small deterministic
scenario set so the demo is reliable. Swap `get_next_event` for a real feed
(Alpaca news stream + an earnings calendar API) when you have time.
"""
from __future__ import annotations
import itertools
from backend.schemas.models import MarketEvent, EventType

_SCENARIOS = [
    MarketEvent(
        event_id="evt-001", event_type=EventType.EARNINGS, ticker="NVDA",
        description="NVDA reports earnings in 6 days; elevated options volume detected.",
        days_to_event=6, iv_percentile=78,
    ),
    MarketEvent(
        event_id="evt-002", event_type=EventType.MACRO, ticker="SPY",
        description="CPI print in 2 days; macro desk flags elevated cross-asset volatility.",
        days_to_event=2, iv_percentile=61,
    ),
    MarketEvent(
        event_id="evt-003", event_type=EventType.VOLATILITY_ANOMALY, ticker="TSLA",
        description="TSLA IV term structure inverted — front-month richer than back-month.",
        days_to_event=None, iv_percentile=88,
    ),
    MarketEvent(
        event_id="evt-004", event_type=EventType.EARNINGS, ticker="AAPL",
        description="AAPL earnings in 1 day — very short IV-crush window.",
        days_to_event=1, iv_percentile=91,
    ),
]

_cycle = itertools.cycle(_SCENARIOS)


def get_next_event() -> MarketEvent:
    return next(_cycle)


def all_scenarios():
    return list(_SCENARIOS)


def scenario_sequence(n: int):
    """
    A fresh, independent cyclic sequence of n events — used by the
    static-desk-vs-Spinup control experiment so that both arms see the
    EXACT same event stream regardless of how many times the shared
    `get_next_event()` cycle (used by the interactive demo) has already
    been advanced elsewhere in the process.
    """
    cyc = itertools.cycle(_SCENARIOS)
    return [next(cyc) for _ in range(n)]
