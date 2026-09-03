"""
RECONCILIATION — closes the gap that made LIVE mode's P&L loop a dead end.

Previously, a live-paper trade could only ever be recorded as "pending"
(order not yet filled / position not yet visible) or "alpaca_unrealized"
(a mark-to-market snapshot taken moments after entry, which — as
alpaca_client.get_unrealized_pnl's own docstring says — is honestly close
to zero right after entry and never represents the trade's real outcome).
Nothing in the codebase ever went back and actually CLOSED a live
position, so a live trade's true win/loss was never booked, the Autopsy
Agent never ran on it, no Lesson was ever stored from it, and Talent could
never score it. The promote/fire loop was effectively dead in LIVE mode.

This module is the missing second half of the live trade lifecycle:

  1. `reconcile_pending_trades()` — for every open live trade, re-checks
     the broker for a live P&L snapshot.
  2. `close_and_realize(trade)` — submits the REVERSE legs to actually
     close the position, then books the resulting P&L as "realized" and
     runs the exact same Autopsy -> Lesson -> Agent-stats -> Talent-review
     pipeline that the MOCK-mode path in run_demo.py already runs for
     every simulated trade — so a live trade now genuinely participates in
     organizational learning and capital reallocation, not just the demo.

This is intentionally a separate module from run_demo.py's inline flow
rather than a copy-paste of it, so both the live event loop AND an
operator-triggered "reconcile now" API call share one source of truth for
what "closing a trade" means.
"""
from __future__ import annotations
import json
import uuid
from typing import List

from backend.database.models import Agent, Trade, CapitalAllocation
from backend.database.db import adjust_treasury
from backend.schemas.models import TradeProposal, OptionLeg
from backend.trading.alpaca_client import alpaca_client
from backend.trading.execution import _net_limit_price
from backend.agents.autopsy import run_autopsy
from backend.agents.memory import store_lesson
from backend.agents.talent import decide as talent_decide
from backend.schemas.models import MarketEvent, EventType


def _proposal_from_trade(trade: Trade) -> TradeProposal:
    """Reconstructs enough of the original proposal from the stored Trade
    row to run Autopsy and store a Lesson — the DB row is the source of
    truth once the original in-memory objects are long gone."""
    legs_raw = json.loads(trade.legs_json) if trade.legs_json else []
    legs = [OptionLeg(**leg) for leg in legs_raw]
    return TradeProposal(
        agent_id=trade.agent_id, ticker=trade.ticker, strategy=trade.strategy,
        legs=legs, max_loss=trade.max_loss, max_profit=trade.max_profit,
        thesis=trade.thesis or "", confidence=0.7,
    )


def close_and_realize(db, trade: Trade) -> dict:
    """
    Closes ONE open live trade and books its real outcome. Returns a
    summary dict describing what happened — never raises for an ordinary
    broker rejection, since a failed close is itself a legitimate outcome
    to surface, not a crash.
    """
    if alpaca_client.mock:
        return {"trade_id": trade.trade_id, "status": "skipped", "reason": "mock mode has nothing to reconcile"}
    if trade.pnl_source == "closed":
        return {"trade_id": trade.trade_id, "status": "already_closed"}
    if not trade.filled:
        return {"trade_id": trade.trade_id, "status": "skipped", "reason": "trade was never filled"}

    proposal = _proposal_from_trade(trade)

    # Snapshot mark-to-market immediately before closing — this becomes the
    # realized P&L once the closing order fills at approximately the same
    # mark. In paper trading this small-slippage approximation is
    # reasonable and is clearly labeled, never presented as an exact fill.
    pre_close_pnl = alpaca_client.get_unrealized_pnl(trade.ticker)
    if pre_close_pnl is None:
        return {
            "trade_id": trade.trade_id, "status": "pending",
            "reason": "no visible position yet on the account — nothing to close",
        }

    close_client_order_id = f"SPINUP-CLOSE-{trade.trade_id}-{uuid.uuid4().hex[:6].upper()}"
    # A permissive limit price so the close is likely to fill promptly —
    # worst case, assume the round-trip costs as much as the original
    # debit/credit again. This affects only whether the close fills, not
    # the P&L recorded: that comes from pre_close_pnl (the broker's own
    # mark-to-market snapshot taken just above), not from this price.
    close_limit_price = -_net_limit_price(trade.strategy, trade.max_loss, trade.max_profit or 0)
    close_result = alpaca_client.close_mleg_position(trade.ticker, proposal.legs, close_client_order_id, close_limit_price)
    if not close_result.get("filled"):
        return {
            "trade_id": trade.trade_id, "status": "close_failed",
            "reason": close_result.get("error", "closing order did not fill"),
        }

    pnl = pre_close_pnl
    chain_for_autopsy = {"iv_percentile": trade.iv_percentile_at_entry or 50}
    autopsy = run_autopsy(proposal, pnl, chain_for_autopsy)

    event_type = trade.event_type or EventType.EARNINGS.value
    synthetic_event = MarketEvent(
        event_id=f"reconcile-{trade.trade_id}", event_type=EventType(event_type),
        ticker=trade.ticker, description="Reconciled live trade close",
    )

    agent_row = db.query(Agent).filter_by(agent_id=trade.agent_id).first()
    if agent_row:
        store_lesson(db, trade.agent_id, agent_row.specialist_type, synthetic_event,
                     chain_for_autopsy, proposal, pnl, autopsy)
        agent_row.trade_count += 1
        agent_row.total_pnl += pnl
        if pnl >= 0:
            agent_row.wins += 1
        else:
            agent_row.losses += 1
            agent_row.max_drawdown = max(agent_row.max_drawdown, abs(pnl) / max(agent_row.capital, 1))

    trade.pnl = pnl
    trade.pnl_source = "closed"
    trade.close_broker_order_id = close_result.get("broker_order_id")
    from backend.database.models import now
    trade.closed_at = now()
    db.commit()

    talent_summary = None
    if agent_row and agent_row.trade_count % 2 == 0:
        decision = talent_decide(agent_row)
        delta = decision.new_capital - decision.previous_capital
        db.add(CapitalAllocation(
            agent_id=agent_row.agent_id, previous_capital=decision.previous_capital,
            new_capital=decision.new_capital, reason=decision.reasoning, talent_score=decision.score,
        ))
        if decision.decision == "FIRE":
            agent_row.status = "FIRED"
            adjust_treasury(db, decision.previous_capital, f"Capital reclaimed from fired agent {agent_row.agent_id}")
        else:
            agent_row.status = decision.decision if decision.decision != "KEEP" else agent_row.status
            agent_row.capital = decision.new_capital
            adjust_treasury(db, -delta, f"Capital {'increase' if delta > 0 else 'decrease'} for {agent_row.agent_id}")
        talent_summary = {"decision": decision.decision, "score": decision.score, "new_capital": decision.new_capital}
    db.commit()

    return {
        "trade_id": trade.trade_id, "status": "closed", "pnl": pnl,
        "autopsy": autopsy, "talent_review": talent_summary,
    }


def recheck_unfilled_orders(db) -> List[dict]:
    """
    Re-polls the broker for every trade that was submitted but never
    confirmed filled (filled=False, risk_approved=True, has a
    broker_order_id). A resting limit order commonly fills *after* the
    initial submit_mleg_order() call returns "accepted, not filled" — but
    until now nothing ever went back and checked, so a trade could sit as
    filled=False forever even after it actually filled on Alpaca's side.
    That's why the activity log kept repeating the same "approved but not
    yet filled — pending" line indefinitely instead of ever showing a
    filled/closed outcome.

    For each such trade, calls alpaca_client.get_order_status() and, if
    the broker now reports it filled, flips trade.filled=True so it
    becomes eligible for close_and_realize() on the next sweep (or in the
    same call, via reconcile_pending_trades()).
    """
    if alpaca_client.mock:
        return []

    unfilled = (
        db.query(Trade)
        .filter(Trade.filled == False, Trade.risk_approved == True,  # noqa: E712
                Trade.broker_order_id.isnot(None))
        .all()
    )
    results = []
    for t in unfilled:
        status = alpaca_client.get_order_status(t.broker_order_id)
        if not status:
            results.append({"trade_id": t.trade_id, "status": "unknown", "reason": "no status returned"})
            continue
        broker_status = (status.get("status") or "").lower()
        # qty=1 mleg orders don't meaningfully partial-fill, but guard
        # against it anyway rather than treating it as fully filled.
        if "filled" in broker_status and "partial" not in broker_status and "unfilled" not in broker_status:
            t.filled = True
            t.pnl_source = "alpaca_unrealized"
            t.submission_error = None
            db.commit()
            results.append({"trade_id": t.trade_id, "status": "now_filled", "broker_status": broker_status})
        elif broker_status in ("canceled", "expired", "rejected"):
            # The order will never fill — stop showing it as "pending" and
            # record why, instead of polling it forever.
            t.submission_error = f"order {broker_status} at broker"
            db.commit()
            results.append({"trade_id": t.trade_id, "status": "dead", "broker_status": broker_status})
        else:
            results.append({"trade_id": t.trade_id, "status": "still_pending", "broker_status": broker_status})
    return results


def reconcile_pending_trades(db) -> List[dict]:
    """
    Full reconciliation sweep, safe to call repeatedly:
      1. recheck_unfilled_orders() — picks up any resting order that has
         since filled at the broker (see its docstring for why this step
         was missing before and caused trades to look permanently stuck).
      2. For every trade now filled (pnl_source in "pending"/
         "alpaca_unrealized"), attempts to close and realize it via
         close_and_realize().
    """
    if alpaca_client.mock:
        return [{"status": "skipped", "reason": "running in MOCK mode — nothing to reconcile against a real broker"}]

    fill_check_results = recheck_unfilled_orders(db)

    open_trades = (
        db.query(Trade)
        .filter(Trade.filled == True, Trade.pnl_source.in_(["pending", "alpaca_unrealized"]))  # noqa: E712
        .all()
    )
    close_results = [close_and_realize(db, t) for t in open_trades]
    return fill_check_results + close_results
