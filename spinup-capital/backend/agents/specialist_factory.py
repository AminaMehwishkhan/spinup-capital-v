from __future__ import annotations
import random
import string
from backend.schemas.models import AgentSpec, SpecialistType, AgentStatus, MarketEvent

TEMPLATES = {
    SpecialistType.EARNINGS: {
        "mandate": "Trade defined-risk post-earnings volatility structures.",
        "allowed_strategies": ["iron_condor", "calendar", "vertical_call_spread", "vertical_put_spread"],
        "permissions": ["market_data", "options_data", "trading:propose"],
    },
    SpecialistType.MACRO: {
        "mandate": "Trade defined-risk directional structures around macro releases (CPI, FOMC, NFP).",
        "allowed_strategies": ["vertical_call_spread", "vertical_put_spread"],
        "permissions": ["market_data", "options_data", "trading:propose"],
    },
    SpecialistType.VOLATILITY: {
        "mandate": "Trade IV skew and term-structure anomalies with calendars/diagonals/verticals.",
        "allowed_strategies": ["calendar", "vertical_call_spread", "vertical_put_spread"],
        "permissions": ["market_data", "options_data", "trading:propose"],
    },
    SpecialistType.HEDGING: {
        "mandate": "Protect the firm's portfolio against drawdown and concentration risk.",
        "allowed_strategies": ["vertical_put_spread"],
        "permissions": ["market_data", "options_data", "trading:propose", "account:read"],
    },
}


def _agent_id(specialist_type: SpecialistType, ticker: str) -> str:
    suffix = "".join(random.choices(string.digits, k=3))
    return f"{specialist_type.value.upper()}-{ticker}-{suffix}"


def spin_up_specialist(
    specialist_type: SpecialistType,
    event: MarketEvent,
    starting_capital: float,
    max_trade_risk_override: float | None = None,
) -> AgentSpec:
    """
    Instantiates a specialist from a capability template. The TEMPLATE is
    predefined (for reliability), but WHICH template gets activated, for
    WHICH symbol, with WHAT capital and risk budget, is decided dynamically
    by the Managing Partner at call time.
    """
    tmpl = TEMPLATES[specialist_type]
    agent_id = _agent_id(specialist_type, event.ticker)
    max_trade_risk = max_trade_risk_override or (starting_capital * 0.10)

    return AgentSpec(
        agent_id=agent_id,
        specialist_type=specialist_type,
        mandate=tmpl["mandate"],
        allowed_symbols=[event.ticker],
        allowed_strategies=tmpl["allowed_strategies"],
        capital=starting_capital,
        max_trade_risk=max_trade_risk,
        permissions=tmpl["permissions"],
        status=AgentStatus.PROBATION,
    )
