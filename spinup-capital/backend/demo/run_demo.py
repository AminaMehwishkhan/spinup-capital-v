"""
Runs the complete Spinup Capital loop end-to-end:

  Market Event -> Managing Partner -> Specialist Factory -> Trade Proposal
  -> Bull/Bear -> Risk Governor -> (repair if rejected) -> Execution
  -> simulated close -> Autopsy -> Talent review -> capital reallocation

Works fully offline (ALPACA/LLM in mock/heuristic mode) so you can demo it
today, and switches to real paper trading the moment you add Alpaca keys
to .env — no code changes required.

Usage:
    python -m backend.demo.run_demo
    python -m backend.demo.run_demo --events 4
"""
from __future__ import annotations
import argparse
import json
import uuid

from backend.config import settings
from backend.database.db import init_db, SessionLocal, get_treasury_balance, adjust_treasury
from backend.database.models import Agent, Trade, Debate, CapitalAllocation, Lesson, ArenaReview
from backend.events.market_events import get_next_event
from backend.agents.managing_partner import route_event
from backend.agents.specialist_factory import spin_up_specialist
from backend.agents.arena import run_arena
from backend.agents.specialist_trader import build_proposal, repair_proposal
from backend.agents.bull_bear import run_debate
from backend.agents.risk_governor import evaluate as risk_evaluate
from backend.agents.autopsy import run_autopsy
from backend.agents.memory import retrieve_relevant_lessons, store_lesson, archive_retirement
from backend.agents.talent import decide as talent_decide
from backend.agents.permissions import PermissionDenied
from backend.trading.alpaca_client import alpaca_client
from backend.trading.execution import execute_trade, simulate_close, attempt_unauthorized_execution

BAR = "=" * 70


def line(msg=""):
    print(msg)


def header(title: str):
    line()
    line(BAR)
    line(f"  {title}")
    line(BAR)


def run(num_events: int, starting_capital_per_hire: float, reset_db: bool):
    init_db(reset=reset_db)
    db = SessionLocal()

    header("SPINUP CAPITAL — AUTONOMOUS AI TRADING FIRM")
    line(f"Mode: {'MOCK (offline)' if settings.ALPACA_MOCK else 'LIVE PAPER (Alpaca)'} trading, "
         f"LLM provider: {settings.LLM_PROVIDER}")
    treasury = get_treasury_balance(db)
    line(f"Treasury: ${treasury:,.0f}")

    header("PERMISSION GATE CHECK")
    line("Before trading a single dollar, confirm the Bull/Bear desk cannot execute trades —")
    line("not by convention, but because the Execution Gateway checks a real permission scope.")
    check = attempt_unauthorized_execution("bull_bear", ["market_data", "options_data"])
    line(f"   Attempted permission: trading:execute")
    line(f"   Held permissions:     {check['held_permissions']}")
    line(f"   Result: {'BLOCKED' if check['blocked'] else 'ALLOWED (unexpected!)'}")

    for i in range(num_events):
        event = get_next_event()
        header(f"MARKET EVENT #{i+1}: {event.event_type.value.upper()} — {event.ticker}")
        line(event.description)

        existing_agents = db.query(Agent).all()
        routing = route_event(event, existing_agents)
        line(f"\nManaging Partner: {routing['rationale']}")

        if routing["action"] == "SPIN_UP":
            treasury = get_treasury_balance(db)
            hire_capital = min(starting_capital_per_hire, treasury * 0.2)
            spec = spin_up_specialist(routing["specialist_type"], event, hire_capital)

            header(f"AGENT ARENA — {spec.agent_id} (trial, before real capital)")
            line(f"Running {settings.ARENA_TRIALS} synthetic scenario trials against this candidate's mandate...")
            arena_result = run_arena(spec, event)
            for t in arena_result.trials:
                verdict = "approved" if t.risk_approved else "blocked"
                pnl_str = f"pnl={t.pnl:+.0f}" if t.risk_approved else "pnl=n/a"
                line(f"   trial: IV={t.scenario_iv:.0f}  strategy={t.strategy:<20} risk={verdict:<8} {pnl_str}")
            line(f"\n{arena_result.reasoning}")

            db.add(ArenaReview(
                candidate_id=spec.agent_id, specialist_type=spec.specialist_type.value,
                ticker=event.ticker, trials_run=len(arena_result.trials),
                win_rate=arena_result.win_rate, avg_pnl=arena_result.avg_pnl,
                risk_pass_rate=arena_result.risk_pass_rate, passed=arena_result.passed,
                reasoning=arena_result.reasoning,
            ))
            db.commit()

            if not arena_result.passed:
                line(f"\n>>> HIRE DECLINED. {spec.agent_id} did not clear the Arena — no capital allocated.")
                continue

            line(f"\n>>> HIRING {spec.agent_id}")
            line(f"    Mandate: {spec.mandate}")
            line(f"    Capital: ${spec.capital:,.0f}  |  Max trade risk: ${spec.max_trade_risk:,.0f}")
            line(f"    Permissions: {spec.permissions}")
            line(f"    Status: {spec.status.value}")

            db.add(Agent(
                agent_id=spec.agent_id, specialist_type=spec.specialist_type.value,
                mandate=f"{spec.mandate} [{event.ticker}]", status=spec.status.value,
                capital=spec.capital, permissions=",".join(spec.permissions),
            ))
            adjust_treasury(db, -spec.capital, f"Allocated capital to new hire {spec.agent_id}")
            db.commit()
            agent_id = spec.agent_id
        else:
            agent_id = routing["agent_id"]
            line(f"\n>>> REUSING existing specialist {agent_id}")

        agent_row = db.query(Agent).filter_by(agent_id=agent_id).first()

        # --- Trade proposal ---
        try:
            chain = alpaca_client.get_option_chain_snapshot(event.ticker)
        except Exception as e:
            line(f"\n>>> SKIPPING this event — live market data request failed: {e}")
            continue
        # rebuild a lightweight AgentSpec-like object for the trader logic
        from backend.schemas.models import AgentSpec, SpecialistType, AgentStatus
        spec_for_trade = AgentSpec(
            agent_id=agent_row.agent_id,
            specialist_type=SpecialistType(agent_row.specialist_type),
            mandate=agent_row.mandate,
            allowed_symbols=[event.ticker],
            allowed_strategies=list({
                "earnings": ["iron_condor", "calendar", "vertical_call_spread", "vertical_put_spread"],
                "macro": ["vertical_call_spread", "vertical_put_spread"],
                "volatility": ["calendar", "vertical_call_spread", "vertical_put_spread"],
                "hedging": ["vertical_put_spread"],
            }[agent_row.specialist_type]),
            capital=agent_row.capital,
            max_trade_risk=agent_row.capital * 0.10,
            permissions=["market_data", "options_data", "trading:propose"],
            status=AgentStatus(agent_row.status) if agent_row.status in AgentStatus.__members__.values() else AgentStatus.PROBATION,
        )

        # --- Organizational memory: retrieve relevant lessons before proposing ---
        lessons = retrieve_relevant_lessons(db, agent_row.specialist_type, ticker=event.ticker)
        if lessons:
            line(f"\nTRADING MEMORY: retrieved {len(lessons)} relevant lesson(s):")
            for l in lessons:
                line(f"   - [{l.ticker}, {l.outcome}] {l.rule}")
        proposal = build_proposal(spec_for_trade, event, chain, lessons=lessons)
        header(f"TRADE PROPOSAL — {agent_id}")
        line(f"Strategy: {proposal.strategy}")
        line(f"Thesis: {proposal.thesis}")
        line(f"Max loss: ${proposal.max_loss:,.0f}  |  Max profit: ${proposal.max_profit:,.0f}")

        debate = run_debate(proposal, event, chain)
        line(f"\nBULL: {debate.bull_argument}")
        line(f"BEAR: {debate.bear_argument}")
        line(f"BEAR failure condition: {debate.bear_failure_condition}")

        deployed = sum(a.capital for a in db.query(Agent).filter(Agent.status != "FIRED").all())
        treasury_balance = get_treasury_balance(db)
        risk = risk_evaluate(proposal, agent_row.capital, deployed, treasury_balance + deployed, event)

        line(f"\nRISK GOVERNOR: {'APPROVED' if risk.approved else 'REJECTED'}")
        for r in risk.reasons:
            line(f"   - {r}")

        if not risk.approved:
            agent_row.risk_violations += 1
            db.commit()
            line("\n>>> TRADE SURGERY: specialist redesigning with tighter structure...")
            proposal = repair_proposal(spec_for_trade, event, chain, risk.reasons, max_allowed_risk=agent_row.capital * 0.10)
            line(f"    New strategy: {proposal.strategy}  |  New max loss: ${proposal.max_loss:,.0f}")
            risk = risk_evaluate(proposal, agent_row.capital, deployed, treasury_balance + deployed, event)
            line(f"    RISK GOVERNOR (re-check): {'APPROVED' if risk.approved else 'REJECTED'}")
            for r in risk.reasons:
                line(f"       - {r}")

        trade_id = f"TRD-{uuid.uuid4().hex[:8].upper()}"
        db.add(Debate(
            trade_id=trade_id, bull_argument=debate.bull_argument,
            bear_argument=debate.bear_argument, bear_failure_condition=debate.bear_failure_condition,
        ))

        if not risk.approved:
            line("\n>>> TRADE BLOCKED. No order submitted.")
            db.add(Trade(
                trade_id=trade_id, agent_id=agent_id, ticker=proposal.ticker,
                strategy=proposal.strategy, legs_json=json.dumps([l.model_dump() for l in proposal.legs]),
                max_loss=proposal.max_loss, max_profit=proposal.max_profit, thesis=proposal.thesis,
                pnl=0, filled=False, risk_approved=False, risk_reasons="; ".join(risk.reasons),
                lessons_used_count=len(lessons), iv_percentile_at_entry=chain.get("iv_percentile"),
                event_type=event.event_type.value,
            ))
            db.commit()
            continue

        held_permissions = (agent_row.permissions or "").split(",")
        result = execute_trade(proposal, risk, trade_id, agent_permissions=held_permissions)
        line(f"\n>>> EXECUTED via {'MOCK' if alpaca_client.mock else 'ALPACA PAPER'}: "
             f"order {result.broker_order_id}, filled={result.filled}")

        # --- Determine P&L honestly: never fabricate a result for a live trade ---
        if alpaca_client.mock:
            pnl = simulate_close(proposal, specialist_type=agent_row.specialist_type, lessons_count=len(lessons))
            pnl_source = "simulated"
        elif not result.filled:
            # A live order that wasn't actually filled (rejected, or still
            # working) has no P&L to report — recording a random number here
            # would be worse than admitting we don't know yet.
            line("LIVE ORDER NOT FILLED — recording as pending, no P&L or lesson generated.")
            if result.error:
                line(f"   Reason: {result.error}")
            elif result.order_status:
                line(f"   Broker order status: {result.order_status} (accepted but not yet filled — "
                     f"this can be normal for a moment after submission; use Reconcile in the Audit "
                     f"tab to check again once it settles).")
            pnl = 0.0
            pnl_source = "pending"
        else:
            live_pnl = alpaca_client.get_unrealized_pnl(proposal.ticker)
            if live_pnl is None:
                line("LIVE order filled, but the position isn't visible on the account yet "
                     "(settlement lag) — recording as pending rather than guessing a P&L.")
                pnl = 0.0
                pnl_source = "pending"
            else:
                pnl = live_pnl
                pnl_source = "alpaca_unrealized"
                line(f"LIVE UNREALIZED P&L (from Alpaca positions): {'+' if pnl >= 0 else ''}{pnl:,.2f}")
                line("Note: this is the real mark-to-market moments after entry, not a simulated "
                     "outcome — it will typically be small/near-zero until the position has had "
                     "time to move, unlike the synthetic MOCK-mode close.")

        if pnl_source == "pending":
            db.add(Trade(
                trade_id=trade_id, agent_id=agent_id, ticker=proposal.ticker, strategy=proposal.strategy,
                legs_json=json.dumps([l.model_dump() for l in proposal.legs]), max_loss=proposal.max_loss,
                max_profit=proposal.max_profit, thesis=proposal.thesis, pnl=0.0, pnl_source=pnl_source,
                filled=result.filled, broker_order_id=result.broker_order_id, risk_approved=True,
                submission_error=result.error,
                lessons_used_count=len(lessons), iv_percentile_at_entry=chain.get("iv_percentile"),
                event_type=event.event_type.value,
            ))
            db.commit()
            continue

        autopsy = run_autopsy(proposal, pnl, chain)
        line(f"\nTRADE CLOSED. PnL: {'+' if pnl >= 0 else ''}{pnl:,.0f}")
        line(f"AUTOPSY: {autopsy['narrative']}")
        line(f"NEW RULE STORED TO TRADING MEMORY: {autopsy['rule']}")
        store_lesson(db, agent_id, agent_row.specialist_type, event, chain, proposal, pnl, autopsy)

        db.add(Trade(
            trade_id=trade_id, agent_id=agent_id, ticker=proposal.ticker, strategy=proposal.strategy,
            legs_json=json.dumps([l.model_dump() for l in proposal.legs]), max_loss=proposal.max_loss,
            max_profit=proposal.max_profit, thesis=proposal.thesis, pnl=pnl, pnl_source=pnl_source, filled=True,
            broker_order_id=result.broker_order_id, risk_approved=True,
            lessons_used_count=len(lessons), iv_percentile_at_entry=chain.get("iv_percentile"),
            event_type=event.event_type.value,
        ))
        agent_row.trade_count += 1
        agent_row.total_pnl += pnl
        if pnl >= 0:
            agent_row.wins += 1
        else:
            agent_row.losses += 1
            agent_row.max_drawdown = max(agent_row.max_drawdown, abs(pnl) / agent_row.capital)
        db.commit()

        # --- Talent review every couple of trades ---
        if agent_row.trade_count % 2 == 0:
            decision = talent_decide(agent_row)
            header(f"HEAD OF TALENT REVIEW — {agent_id}")
            line(f"Score: {decision.score}/100  |  Decision: {decision.decision}")
            line(decision.reasoning)

            delta = decision.new_capital - decision.previous_capital
            db.add(CapitalAllocation(
                agent_id=agent_id, previous_capital=decision.previous_capital,
                new_capital=decision.new_capital, reason=decision.reasoning, talent_score=decision.score,
            ))
            if decision.decision == "FIRE":
                agent_row.status = "FIRED"
                adjust_treasury(db, decision.previous_capital, f"Capital reclaimed from fired agent {agent_id}")
                archive_retirement(db, agent_row, decision)
                line(f"AGENT RETIREMENT: career archived to Trading Memory as a reusable lesson "
                     f"for future {agent_row.specialist_type} hires.")
            else:
                agent_row.status = decision.decision if decision.decision != "KEEP" else agent_row.status
                agent_row.capital = decision.new_capital
                adjust_treasury(db, -delta, f"Capital {'increase' if delta>0 else 'decrease'} for {agent_id}")
            db.commit()
            line(f"Capital: ${decision.previous_capital:,.0f} -> ${decision.new_capital:,.0f}")

    # --- Final summary ---
    header("FIRM SUMMARY")
    agents = db.query(Agent).all()
    trades = db.query(Trade).all()
    arena_reviews = db.query(ArenaReview).all()
    treasury_final = get_treasury_balance(db)
    total_agent_capital = sum(a.capital for a in agents if a.status != "FIRED")
    line(f"Treasury:              ${treasury_final:,.0f}")
    line(f"Deployed to agents:    ${total_agent_capital:,.0f}")
    line(f"Total firm value:      ${treasury_final + total_agent_capital:,.0f}")
    line(f"Candidates arena'd:    {len(arena_reviews)} "
         f"({len([r for r in arena_reviews if r.passed])} passed, "
         f"{len([r for r in arena_reviews if not r.passed])} declined pre-capital)")
    line(f"Agents hired:          {len(agents)}")
    line(f"Agents active:         {len([a for a in agents if a.status != 'FIRED'])}")
    line(f"Agents fired:          {len([a for a in agents if a.status == 'FIRED'])}")
    line(f"Trades executed:       {len([t for t in trades if t.filled])}")
    line(f"Trades blocked:        {len([t for t in trades if not t.risk_approved])}")
    pending_count = len([t for t in trades if t.risk_approved and not t.filled])
    if pending_count:
        line(f"Trades pending:        {pending_count} (risk-approved, submitted, not yet filled — "
             f"see Audit tab / /alpaca/reconcile)")
    if trades:
        wins = len([t for t in trades if t.filled and t.pnl > 0])
        filled = [t for t in trades if t.filled]
        if filled:
            line(f"Win rate:              {wins/len(filled):.0%}")
            line(f"Total realized PnL:    ${sum(t.pnl for t in filled):,.0f}")

    line("\nAgent leaderboard:")
    for a in sorted(agents, key=lambda x: x.total_pnl, reverse=True):
        line(f"  {a.agent_id:<20} status={a.status:<10} capital=${a.capital:>9,.0f} "
             f"pnl=${a.total_pnl:>8,.0f} trades={a.trade_count} win/loss={a.wins}/{a.losses}")

    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=4, help="Number of market events to simulate")
    parser.add_argument("--hire-capital", type=float, default=10000, help="Starting capital per new hire")
    parser.add_argument("--reset", action="store_true", help="Reset the database before running")
    args = parser.parse_args()
    run(args.events, args.hire_capital, args.reset)
