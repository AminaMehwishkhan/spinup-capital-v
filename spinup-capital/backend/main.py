from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database.db import init_db, SessionLocal, get_treasury_balance
from backend.database.models import Agent, Trade, CapitalAllocation, Debate, Lesson, ArenaReview
from backend.events.market_events import get_next_event, all_scenarios

app = FastAPI(title="Spinup Capital API")


@app.on_event("startup")
def _log_mode_on_startup():
    from backend.config import settings, _PROJECT_ROOT
    env_path = _PROJECT_ROOT / ".env"
    print("=" * 70)
    if settings.ALPACA_MOCK:
        print(f"MODE: MOCK — no Alpaca keys loaded.")
        print(f"  .env expected at: {env_path} (exists: {env_path.exists()})")
        print(f"  If that file exists and has real keys but this still says MOCK, "
              f"check for typos in the key names or extra quotes/whitespace around the values.")
    else:
        print(f"MODE: LIVE PAPER — Alpaca key loaded ({settings.ALPACA_API_KEY[:4]}…), "
              f"base URL: {settings.ALPACA_BASE_URL}")
    print("=" * 70)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db(reset=False)


@app.get("/firm/summary")
def firm_summary():
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        trades = db.query(Trade).all()
        treasury = get_treasury_balance(db)
        deployed = sum(a.capital for a in agents if a.status != "FIRED")
        return {
            "treasury": treasury,
            "deployed_capital": deployed,
            "total_firm_value": treasury + deployed,
            "agents_hired": len(agents),
            "agents_active": len([a for a in agents if a.status != "FIRED"]),
            "agents_fired": len([a for a in agents if a.status == "FIRED"]),
            "trades_executed": len([t for t in trades if t.filled]),
            # WAS `not t.filled` — that conflated three different things: a
            # risk-rejected proposal (genuinely blocked, never submitted), a
            # risk-approved order that's simply pending/not-yet-filled, and
            # an approved order whose submission actually failed. All three
            # showed up as one undifferentiated "blocked" number, which is
            # exactly what made approved-but-pending live trades look like
            # Risk Governor rejections in the dashboard.
            "trades_blocked": len([t for t in trades if not t.risk_approved]),
            "trades_pending": len([t for t in trades if t.risk_approved and not t.filled]),
        }
    finally:
        db.close()


@app.get("/agents")
def list_agents():
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        return [
            {
                "agent_id": a.agent_id, "specialist_type": a.specialist_type, "status": a.status,
                "capital": a.capital, "total_pnl": a.total_pnl, "trade_count": a.trade_count,
                "wins": a.wins, "losses": a.losses, "max_drawdown": a.max_drawdown,
                "risk_violations": a.risk_violations,
                "permissions": (a.permissions or "").split(",") if a.permissions else [],
            }
            for a in agents
        ]
    finally:
        db.close()


@app.get("/trades")
def list_trades():
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.created_at.desc()).all()
        return [
            {
                "trade_id": t.trade_id, "agent_id": t.agent_id, "ticker": t.ticker,
                "strategy": t.strategy, "pnl": t.pnl, "filled": t.filled,
                "risk_approved": t.risk_approved, "risk_reasons": t.risk_reasons,
                "thesis": t.thesis, "pnl_source": t.pnl_source,
                "lessons_used_count": t.lessons_used_count, "submission_error": t.submission_error,
                "broker_order_id": t.broker_order_id, "close_broker_order_id": t.close_broker_order_id,
            }
            for t in trades
        ]
    finally:
        db.close()


@app.get("/capital-allocations")
def list_allocations():
    db = SessionLocal()
    try:
        rows = db.query(CapitalAllocation).order_by(CapitalAllocation.timestamp.desc()).all()
        return [
            {
                "agent_id": r.agent_id, "previous_capital": r.previous_capital,
                "new_capital": r.new_capital, "reason": r.reason, "talent_score": r.talent_score,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/events/scenarios")
def scenarios():
    return [e.dict() for e in all_scenarios()]


@app.get("/lessons")
def list_lessons():
    db = SessionLocal()
    try:
        rows = (
            db.query(Lesson)
            .filter(Lesson.is_retirement == False)  # noqa: E712
            .order_by(Lesson.created_at.desc())
            .limit(30)
            .all()
        )
        return [
            {
                "id": r.id, "agent_id": r.agent_id, "specialist_type": r.specialist_type,
                "ticker": r.ticker, "outcome": r.outcome, "iv_percentile": r.iv_percentile,
                "market_condition": r.market_condition, "lesson": r.lesson, "rule": r.rule,
                "confidence": r.confidence,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/retirements")
def list_retirements():
    """Fired agents' archived career summaries — the organizational-memory
    exit interview future hires of the same specialist type inherit."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Lesson)
            .filter(Lesson.is_retirement == True)  # noqa: E712
            .order_by(Lesson.created_at.desc())
            .limit(30)
            .all()
        )
        return [
            {
                "id": r.id, "agent_id": r.agent_id, "specialist_type": r.specialist_type,
                "lesson": r.lesson, "rule": r.rule, "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/permissions/matrix")
def permissions_matrix():
    """The firm's real access-control matrix — every role's actual
    permission scope, enforced at runtime by backend.agents.permissions."""
    from backend.agents.permissions import matrix
    return matrix()


@app.post("/demo/unauthorized-trade")
def demo_unauthorized_trade():
    """
    Proves, live, that a non-execution role (the Bull/Bear desk) cannot
    place a trade. Always returns blocked=True — this endpoint exists to
    make the permission gate visible in the UI, not to attempt a real
    trade under any circumstance.
    """
    from backend.trading.execution import attempt_unauthorized_execution
    return attempt_unauthorized_execution("bull_bear", ["market_data", "options_data"])


@app.get("/arena-log")
def list_arena_reviews():
    db = SessionLocal()
    try:
        rows = db.query(ArenaReview).order_by(ArenaReview.created_at.desc()).limit(30).all()
        return [
            {
                "id": r.id, "candidate_id": r.candidate_id, "specialist_type": r.specialist_type,
                "ticker": r.ticker, "trials_run": r.trials_run, "win_rate": r.win_rate,
                "avg_pnl": r.avg_pnl, "risk_pass_rate": r.risk_pass_rate, "passed": r.passed,
                "reasoning": r.reasoning,
            }
            for r in rows
        ]
    finally:
        db.close()


@app.post("/experiment/run")
def run_experiment_endpoint(events: int = 40, hire_capital: float = 10000, total_capital: float = 100000):
    from backend.demo.run_experiment import run as run_experiment
    static_result, spinup_result = run_experiment(events, total_capital, hire_capital)
    return {"static": static_result, "spinup": spinup_result}


@app.post("/demo/run")
def run_demo_endpoint(num_events: int = 4, hire_capital: float = 10000, reset: bool = False):
    from backend.demo.run_demo import run
    run(num_events, hire_capital, reset)

    # Piggyback a reconciliation sweep on every run cycle. Without this,
    # a trade that was "approved but not yet filled" on a previous cycle
    # could sit at filled=False forever even after it actually filled at
    # the broker — nothing ever re-checked it, so the activity log just
    # kept repeating the same pending line and a genuine fill/close never
    # showed up. This makes "Run market cycle" pick up any resting orders
    # that have since filled, in addition to whatever the new events do.
    from backend.trading.alpaca_client import alpaca_client
    reconcile_summary = None
    if not alpaca_client.mock:
        from backend.trading.reconciliation import reconcile_pending_trades
        db = SessionLocal()
        try:
            reconcile_summary = reconcile_pending_trades(db)
        finally:
            db.close()

    return {"status": "completed", "events_run": num_events, "reconciled": reconcile_summary}


# ------------------------------------------------------------- Alpaca audit
@app.get("/alpaca/account")
def alpaca_account():
    """LIVE mode: the real paper account's cash/buying power, straight from Alpaca."""
    from backend.trading.alpaca_client import alpaca_client
    return alpaca_client.get_account()


@app.get("/alpaca/positions")
def alpaca_positions():
    """LIVE mode: every open position on the paper account. Empty list in MOCK mode."""
    from backend.trading.alpaca_client import alpaca_client
    return alpaca_client.list_positions()


@app.get("/alpaca/orders")
def alpaca_orders(limit: int = 25):
    """LIVE mode: the broker's own order ledger — ground truth to reconcile
    against the firm's internal Trade table. Empty list in MOCK mode."""
    from backend.trading.alpaca_client import alpaca_client
    return alpaca_client.list_recent_orders(limit)


@app.post("/alpaca/reconcile")
def alpaca_reconcile():
    """
    Closes every open LIVE trade (pending / unrealized) and books its real
    realized P&L, running Autopsy -> Lesson -> Talent review on each —
    completing the live-mode P&L loop that otherwise stalls at 'pending'.
    No-ops safely in MOCK mode.
    """
    from backend.trading.reconciliation import reconcile_pending_trades
    db = SessionLocal()
    try:
        return {"results": reconcile_pending_trades(db)}
    finally:
        db.close()


# ------------------------------------------------------------ learning curve
@app.get("/learning-curve")
def learning_curve():
    """
    Does organizational memory actually change outcomes? Splits every
    closed, filled trade into two buckets — proposed with zero relevant
    lessons available vs. proposed with at least one — and compares win
    rate / average P&L per specialist type. This is a real, computed
    correlation from the firm's own trade history, not a narrative claim.
    Small-sample honestly: with only a handful of trades per bucket this
    is directional, not statistically definitive — the response says so.
    """
    db = SessionLocal()
    try:
        trades = (
            db.query(Trade)
            .filter(Trade.filled == True, Trade.pnl_source != "pending")  # noqa: E712
            .all()
        )
        by_type: dict[str, dict] = {}
        for t in trades:
            agent = db.query(Agent).filter_by(agent_id=t.agent_id).first()
            stype = agent.specialist_type if agent else "unknown"
            bucket = "with_memory" if (t.lessons_used_count or 0) > 0 else "no_memory"
            by_type.setdefault(stype, {"with_memory": [], "no_memory": []})
            by_type[stype][bucket].append(t.pnl)

        def _stats(pnls):
            if not pnls:
                return {"trades": 0, "win_rate": None, "avg_pnl": None}
            wins = sum(1 for p in pnls if p >= 0)
            return {
                "trades": len(pnls),
                "win_rate": round(wins / len(pnls), 3),
                "avg_pnl": round(sum(pnls) / len(pnls), 2),
            }

        result = {}
        for stype, buckets in by_type.items():
            result[stype] = {
                "no_memory": _stats(buckets["no_memory"]),
                "with_memory": _stats(buckets["with_memory"]),
            }
        return {
            "by_specialist_type": result,
            "note": "Directional only on small sample sizes — run more market cycles for a sturdier signal.",
        }
    finally:
        db.close()


# --------------------------------------------------------------- backtest
@app.post("/backtest/run")
def backtest_run(ticker: str = "AAPL", specialist_type: str = "earnings",
                  lookback_days: int = 180, holding_period_days: int = 21, capital: float = 10000):
    from backend.backtest.engine import run_backtest
    return run_backtest(ticker, specialist_type, lookback_days, holding_period_days, capital)


@app.post("/experiment/monte-carlo")
def experiment_monte_carlo(n_events: int = 60, total_capital: float = 100000,
                            hire_capital: float = 10000, n_runs: int = 25):
    from backend.demo.run_experiment import run_monte_carlo
    return run_monte_carlo(n_events, total_capital, hire_capital, n_runs)
