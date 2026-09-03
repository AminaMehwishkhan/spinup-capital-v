"""
MANAGING PARTNER — answers exactly three questions and nothing else:
  1. What is happening? (event classification — already done upstream)
  2. Which specialist type is capable of handling it?
  3. Should we reuse an existing specialist, or spin up a new one?

It never trades and never touches risk/execution.
"""
from __future__ import annotations
from typing import List, Optional
from backend.schemas.models import MarketEvent, EventType, SpecialistType
from backend.database.models import Agent

EVENT_TO_SPECIALIST = {
    EventType.EARNINGS: SpecialistType.EARNINGS,
    EventType.MACRO: SpecialistType.MACRO,
    EventType.VOLATILITY_ANOMALY: SpecialistType.VOLATILITY,
    EventType.DRAWDOWN: SpecialistType.HEDGING,
}


def route_event(event: MarketEvent, existing_agents: List[Agent]) -> dict:
    specialist_type = EVENT_TO_SPECIALIST[event.event_type]

    # Reuse an existing, non-fired agent of the right type already covering this ticker.
    reusable: Optional[Agent] = next(
        (
            a for a in existing_agents
            if a.specialist_type == specialist_type.value
            and a.status != "FIRED"
            and event.ticker in (a.mandate or "")
        ),
        None,
    )

    if reusable:
        return {
            "action": "USE_EXISTING",
            "specialist_type": specialist_type,
            "agent_id": reusable.agent_id,
            "rationale": (
                f"An existing {specialist_type.value} specialist ({reusable.agent_id}) already "
                f"covers {event.ticker} and is in good standing — reuse rather than duplicate headcount."
            ),
        }

    return {
        "action": "SPIN_UP",
        "specialist_type": specialist_type,
        "agent_id": None,
        "rationale": (
            f"No suitable active specialist exists for a {event.event_type.value} event on "
            f"{event.ticker}. Recommending a new {specialist_type.value} specialist be hired."
        ),
    }
