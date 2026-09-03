"""
ORGANIZATIONAL MEMORY.

This is what makes "self-evolving" literally true rather than narrated:
after every closed trade, the Autopsy Agent's structured rule gets stored
here, tagged by specialist type, ticker, and market conditions. Before a
specialist proposes its NEXT trade — even a different agent instance,
possibly for a different ticker — it retrieves relevant past lessons and
that retrieval measurably changes its strategy choice and its stated
thesis. Nothing here is per-agent; it's firm-wide knowledge, matching the
"Trading Memory" concept in the spec (store market condition, strategy,
reason, outcome, failure cause → specialists retrieve before proposing).
"""
from __future__ import annotations
from typing import List
from backend.database.models import Lesson
from backend.schemas.models import MarketEvent, TradeProposal


def store_lesson(
    db,
    agent_id: str,
    specialist_type: str,
    event: MarketEvent,
    chain: dict,
    proposal: TradeProposal,
    pnl: float,
    autopsy: dict,
) -> Lesson:
    row = Lesson(
        agent_id=agent_id,
        specialist_type=specialist_type,
        ticker=event.ticker,
        outcome="win" if pnl >= 0 else "loss",
        iv_percentile=chain.get("iv_percentile"),
        days_to_event=event.days_to_event,
        market_condition=f"{event.event_type.value} on {event.ticker}, IV pct {chain.get('iv_percentile')}, "
                          f"{event.days_to_event if event.days_to_event is not None else 'n/a'} days to event",
        failure_reason=None if pnl >= 0 else autopsy.get("narrative"),
        lesson=autopsy.get("narrative", ""),
        rule=autopsy.get("rule", ""),
        confidence=0.75 if pnl >= 0 else 0.6,
    )
    db.add(row)
    db.commit()
    return row


def retrieve_relevant_lessons(
    db,
    specialist_type: str,
    ticker: str | None = None,
    top_n: int = 3,
) -> List[Lesson]:
    """
    Firm-wide retrieval: any specialist of this type — regardless of which
    physical agent_id learned it, and regardless of ticker unless one
    matches exactly — can benefit from the lesson. Ticker-matching lessons
    are ranked first, then most-recent-first.
    """
    rows = (
        db.query(Lesson)
        .filter(Lesson.specialist_type == specialist_type)
        .order_by(Lesson.created_at.desc())
        .limit(25)
        .all()
    )
    if not rows:
        return []
    ticker_matches = [r for r in rows if ticker and r.ticker == ticker]
    others = [r for r in rows if not (ticker and r.ticker == ticker)]
    ranked = ticker_matches + others
    return ranked[:top_n]


def archive_retirement(db, agent, decision) -> Lesson:
    """
    AGENT RETIREMENT: a fired agent's career doesn't just disappear — its
    full track record is condensed into one archival lesson (tagged
    is_retirement=True) so the NEXT specialist of this type, hired for any
    ticker, inherits what got this one terminated instead of starting from
    zero. This is the "organizational memory" version of an exit
    interview, and it's retrieved through the exact same
    retrieve_relevant_lessons() path as any ordinary trade lesson.
    """
    win_rate = (agent.wins / agent.trade_count) if agent.trade_count else 0.0
    row = Lesson(
        agent_id=agent.agent_id,
        specialist_type=agent.specialist_type,
        ticker="ALL",
        outcome="retired",
        market_condition=f"Career summary over {agent.trade_count} trades",
        failure_reason=decision.reasoning,
        lesson=(
            f"{agent.agent_id} was retired after {agent.trade_count} trades "
            f"({win_rate:.0%} win rate, ${agent.total_pnl:,.0f} total P&L, "
            f"{agent.risk_violations} risk violation(s)). {decision.reasoning}"
        ),
        rule=(
            f"Future {agent.specialist_type} specialists: prior hire terminated at {win_rate:.0%} "
            f"win rate with {agent.risk_violations} risk violation(s) and "
            f"{agent.max_drawdown:.0%} max drawdown — tighten sizing and re-verify thesis quality "
            f"before repeating this specialist type's recent strategy mix."
        ),
        confidence=0.9,
        is_retirement=True,
    )
    db.add(row)
    db.commit()
    return row


def should_avoid_long_premium(lessons: List[Lesson]) -> bool:
    """Simple, explainable check the specialist can act on before proposing."""
    return any("avoid long-premium" in (l.rule or "").lower() for l in lessons)
