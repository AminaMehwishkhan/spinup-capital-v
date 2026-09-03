"""
EXECUTION GATEWAY — the single choke point between an approved trade
proposal and the broker. No agent, LLM, or specialist ever calls Alpaca
directly; everything routes through here, and this module refuses to
submit anything that hasn't already been approved by the Risk Governor.
"""
from __future__ import annotations
import random
from typing import Iterable, Optional
from backend.schemas.models import TradeProposal, RiskCheckResult, TradeResult
from backend.trading.alpaca_client import alpaca_client
from backend.agents.permissions import require, PermissionDenied


def _net_limit_price(strategy: str, max_loss: float, max_profit: float) -> float:
    """
    Alpaca's mleg limit_price convention: positive = net debit (you pay),
    negative = net credit (you receive). Every debit-style strategy in
    this codebase (vertical spreads, calendar) sets max_loss equal to the
    debit paid; the one credit-style strategy (iron_condor) sets
    max_profit equal to the credit received — see trading/options.py's
    builders. This derives the correctly-signed net price straight from
    those numbers instead of needing a separate live quote.
    """
    if strategy == "iron_condor":
        return round(-(max_profit / 100.0), 2)
    return round(max_loss / 100.0, 2)


def execute_trade(
    proposal: TradeProposal,
    risk_result: RiskCheckResult,
    trade_id: str,
    agent_permissions: Optional[Iterable[str]] = None,
) -> TradeResult:
    # Permission gate #1: the proposing agent must actually hold
    # trading:propose. No specialist template grants trading:execute —
    # this call would refuse it even if one somehow did, since the
    # execute permission is checked against this module's OWN scope
    # below, never against the agent's.
    require("specialist", "trading:propose", held=agent_permissions)

    # Permission gate #2: only the Execution Gateway itself ever holds
    # trading:execute. This isn't a convention — it's checked every call.
    require("execution_gateway", "trading:execute")

    if not risk_result.approved:
        raise PermissionError(
            f"Execution refused: trade {trade_id} was not approved by the Risk Governor. "
            f"Reasons: {risk_result.reasons}"
        )

    client_order_id = f"SPINUP-{proposal.agent_id}-{trade_id}"
    net_limit_price = _net_limit_price(proposal.strategy, proposal.max_loss, proposal.max_profit)
    order = alpaca_client.submit_mleg_order(proposal.ticker, proposal.legs, client_order_id, net_limit_price)

    return TradeResult(
        trade_id=trade_id,
        agent_id=proposal.agent_id,
        ticker=proposal.ticker,
        strategy=proposal.strategy,
        pnl=0.0,           # unrealized until the position is later closed/marked
        max_loss=proposal.max_loss,
        filled=order["filled"],
        broker_order_id=order.get("broker_order_id"),
        order_status=order.get("status"),
        error=order.get("error"),
    )


def attempt_unauthorized_execution(role: str, held_permissions: Iterable[str]) -> dict:
    """
    Demo/audit hook: proves, at runtime, that a non-execution role cannot
    place a trade — not because it wouldn't think to, but because the
    permission gate refuses it. Always raises PermissionDenied for any
    role other than 'execution_gateway', regardless of what's in
    held_permissions, since trading:execute is never actually granted to
    any agent template.
    """
    try:
        require(role, "trading:execute", held=held_permissions)
        return {"blocked": False, "role": role}
    except PermissionDenied as e:
        return {
            "blocked": True,
            "role": role,
            "attempted_permission": "trading:execute",
            "held_permissions": e.held,
            "reason": str(e),
        }


# Per-specialist-type baseline win probability in the simulated market.
# WHY THIS EXISTS: with every specialist type sharing one flat win_bias,
# there is no persistent, learnable skill difference for Talent to ever
# detect — reallocating capital toward an early winner is then pure
# noise-chasing, which is exactly what a Monte Carlo run of the earlier
# uniform-bias version showed (Spinup underperformed Static on average,
# with zero agents ever fired). This models each specialist type facing a
# genuinely different — but fixed and reproducible — trading environment,
# so an organization that actually measures performance and reallocates
# toward what's working has real information to exploit, not luck.
# These are modeling assumptions for demonstrating the organizational
# mechanism, not claims about real market edge by strategy type.
SPECIALIST_TRUE_EDGE = {
    "earnings": 0.60,
    "volatility": 0.58,
    "macro": 0.48,
    "hedging": 0.50,
}

# Win-probability bonus per relevant lesson available at proposal time,
# capped, modeling "a specialist that draws on a documented prior failure
# mode makes a better-calibrated trade." This is what makes Trading Memory
# a real, measurable input rather than a narrative flourish — see
# /learning-curve, which checks whether this shows up in actual trade
# outcomes.
LESSON_WIN_BONUS_PER_LESSON = 0.03
LESSON_WIN_BONUS_CAP = 0.15


def _effective_win_bias(base_win_bias: float, specialist_type: str = None, lessons_count: int = 0) -> float:
    bias = SPECIALIST_TRUE_EDGE.get(specialist_type, base_win_bias) if specialist_type else base_win_bias
    bias += min(lessons_count * LESSON_WIN_BONUS_PER_LESSON, LESSON_WIN_BONUS_CAP)
    return min(bias, 0.9)


def simulate_close(proposal: TradeProposal, win_bias: float = 0.55,
                    specialist_type: str = None, lessons_count: int = 0) -> float:
    """
    MOCK-mode only: simulates a realistic-shaped P&L outcome at close so the
    Autopsy -> Talent loop can run end-to-end without waiting on real market
    time to pass. In LIVE mode, replace this with a call that reads the
    actual realized P&L from the Alpaca positions/closed-orders endpoint.

    `specialist_type` and `lessons_count` feed into `_effective_win_bias` —
    see its docstring for why they exist.
    """
    bias = _effective_win_bias(win_bias, specialist_type, lessons_count)
    won = random.random() < bias
    if won:
        return round(random.uniform(0.15, 0.9) * proposal.max_profit, 2)
    return round(-random.uniform(0.3, 1.0) * proposal.max_loss, 2)


def simulate_close_seeded(proposal: TradeProposal, event_seed: int, win_bias: float = 0.55,
                           specialist_type: str = None, lessons_count: int = 0) -> float:
    """
    Same simulated-close model as `simulate_close`, but drawn from a local,
    explicitly-seeded RNG rather than the global `random` module. Used by
    the Static-Desk-vs-Spinup control experiment (backend/experiments/) so
    that "the same market event" produces a directly comparable outcome
    across both organizational arms, regardless of how many other random
    calls either arm happened to make before reaching this trade.
    """
    rnd = random.Random(event_seed)
    bias = _effective_win_bias(win_bias, specialist_type, lessons_count)
    won = rnd.random() < bias
    if won:
        return round(rnd.uniform(0.15, 0.9) * proposal.max_profit, 2)
    return round(-rnd.uniform(0.3, 1.0) * proposal.max_loss, 2)
