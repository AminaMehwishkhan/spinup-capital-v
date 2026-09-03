from __future__ import annotations
from typing import List
from backend.schemas.models import AgentSpec, MarketEvent, TradeProposal
from backend.trading.options import STRATEGY_BUILDERS
from backend.agents.llm_client import complete
from backend.agents.memory import should_avoid_long_premium


def choose_strategy(spec: AgentSpec, event: MarketEvent, chain: dict, lessons: List = None) -> str:
    lessons = lessons or []
    iv = chain.get("iv_percentile", 50)

    # Organizational memory overrides the default heuristic when it applies.
    if should_avoid_long_premium(lessons) and iv >= 80 and event.days_to_event is not None and event.days_to_event <= 3:
        for candidate in ("vertical_call_spread", "vertical_put_spread", "iron_condor"):
            if candidate in spec.allowed_strategies:
                return candidate

    # Deterministic strategy selection heuristic (kept simple/explainable for the demo).
    calendar_available = "calendar" in spec.allowed_strategies and chain.get("far_expiration") not in (None, chain.get("expiration"))
    if "iron_condor" in spec.allowed_strategies and iv >= 70:
        return "iron_condor"
    if calendar_available and iv <= 40:
        return "calendar"
    if "vertical_call_spread" in spec.allowed_strategies:
        return "vertical_call_spread"
    return spec.allowed_strategies[0]


def generate_thesis(spec: AgentSpec, event: MarketEvent, strategy: str, chain: dict, lessons: List = None) -> str:
    lessons = lessons or []
    system = "Write a 1-2 sentence trading thesis for an options desk. Be concrete and specific."
    lesson_context = " ".join(l.rule for l in lessons if l.rule)
    user = (
        f"Ticker: {event.ticker}. Event: {event.description}. Strategy: {strategy}. "
        f"IV percentile: {chain.get('iv_percentile')}. Mandate: {spec.mandate}. "
        f"Relevant firm lessons: {lesson_context or 'none yet'}"
    )

    def heuristic():
        base = (
            f"{event.ticker} shows {chain.get('iv_percentile')}th-percentile IV ahead of "
            f"'{event.description.split(';')[0].strip().lower()}'; a {strategy.replace('_',' ')} "
            f"captures the expected move within a defined-risk structure."
        )
        if lessons:
            base += f" (Informed by {len(lessons)} prior firm lesson{'s' if len(lessons) != 1 else ''}: \"{lessons[0].rule}\")"
        return base

    return complete(system, user, heuristic_fn=heuristic)


def build_proposal(spec: AgentSpec, event: MarketEvent, chain: dict, lessons: List = None) -> TradeProposal:
    lessons = lessons or []
    strategy = choose_strategy(spec, event, chain, lessons)
    legs, max_loss, max_profit = STRATEGY_BUILDERS[strategy](chain)

    # Size to the agent's own risk budget up front, rather than relying on
    # a Risk Governor rejection + trade-surgery repair for every proposal
    # whose raw strike width happens not to fit (e.g. a high-priced
    # underlying producing a wide, expensive vertical spread). A small
    # safety margin + hard clamp avoids floating-point rounding pushing the
    # scaled max_loss a few cents back over budget.
    scale_note = ""
    if spec.max_trade_risk and max_loss > spec.max_trade_risk > 0:
        scale = (spec.max_trade_risk * 0.99) / max_loss
        max_loss = min(round(max_loss * scale, 2), spec.max_trade_risk)
        max_profit = round(max_profit * scale, 2)
        scale_note = f" Sized to {scale:.0%} of a full contract to fit the ${spec.max_trade_risk:,.0f} risk budget."

    thesis = generate_thesis(spec, event, strategy, chain, lessons) + scale_note

    return TradeProposal(
        agent_id=spec.agent_id,
        ticker=event.ticker,
        strategy=strategy,
        legs=legs,
        max_loss=max_loss,
        max_profit=max_profit,
        thesis=thesis,
        confidence=0.7,
    )


def repair_proposal(
    spec: AgentSpec, event: MarketEvent, chain: dict, reasons: list[str],
    max_allowed_risk: float | None = None,
) -> TradeProposal:
    """
    "Trade surgery": if Risk rejects on max-loss grounds, the specialist
    doesn't just re-propose the same structure — it (a) switches to a
    narrower strategy where possible, and (b) scales the position size
    down (fractional contracts, as a paper-trading simplification) until
    max loss fits inside the agent's per-trade risk budget.
    """
    fallback_strategy = "vertical_call_spread" if "vertical_call_spread" in spec.allowed_strategies else spec.allowed_strategies[0]
    legs, max_loss, max_profit = STRATEGY_BUILDERS[fallback_strategy](chain)

    scale_note = ""
    if max_allowed_risk and max_loss > max_allowed_risk > 0:
        scale = (max_allowed_risk * 0.99) / max_loss
        max_loss = min(round(max_loss * scale, 2), max_allowed_risk)
        max_profit = round(max_profit * scale, 2)
        scale_note = f" and sized down to {scale:.0%} of a full contract to fit the risk budget"

    thesis = (
        f"Redesigned after Risk rejection ({'; '.join(reasons)}). Switched to a narrower "
        f"{fallback_strategy.replace('_', ' ')}{scale_note}, cutting max loss to ${max_loss:,.0f}."
    )
    return TradeProposal(
        agent_id=spec.agent_id,
        ticker=event.ticker,
        strategy=fallback_strategy,
        legs=legs,
        max_loss=max_loss,
        max_profit=max_profit,
        thesis=thesis,
        confidence=0.6,
    )
