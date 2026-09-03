"""
THE CONTROL EXPERIMENT (spec Section 24): does organizational adaptation
actually improve performance, or are you just watching a normal trading
bot with an org chart drawn on top of it?

Two arms, run against the EXACT SAME event stream and the EXACT SAME
per-event simulated market outcome (same seed -> same win/loss and
magnitude for "this event"), so the only thing that differs between arms
is the organizational logic:

  STATIC DESK  — one persistent agent per specialist type, hired once at
                 the start with an equal, fixed slice of capital. No Arena
                 gate, no Talent review, never fired, capital never moves.
  SPINUP       — the real system: Arena-gated hiring per ticker, Talent
                 review every 2 trades, capital promoted/cut/reclaimed.

This is intentionally a separate, lightweight, in-memory simulation (not
the SQLite-backed `run_demo.py`) so it can run many events fast and stay
fully deterministic for a reliable, reproducible results slide.

Usage:
    python -m backend.demo.run_experiment --events 24
"""
from __future__ import annotations
import argparse
import hashlib
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.schemas.models import AgentSpec, SpecialistType, AgentStatus, MarketEvent
from backend.events.market_events import scenario_sequence
from backend.agents.managing_partner import EVENT_TO_SPECIALIST
from backend.agents.specialist_factory import TEMPLATES
from backend.agents.specialist_trader import build_proposal, repair_proposal
from backend.agents.risk_governor import evaluate as risk_evaluate
from backend.agents.arena import run_arena
from backend.agents.talent import decide as talent_decide
from backend.trading.execution import simulate_close_seeded

BAR = "=" * 70


def line(msg=""):
    print(msg)


def _synthetic_chain(ticker: str, event_seed: int) -> dict:
    """
    A deterministic, offline chain snapshot — this experiment's whole
    methodology depends on fast, reproducible, network-free runs (see the
    module docstring). It must NEVER call the real Alpaca client: doing so
    previously meant that whenever the app happened to be configured in
    LIVE mode, a single Monte Carlo batch (e.g. 25 runs x 60 events x 2
    arms) fired up to several thousand real network requests at the
    broker, turning a supposedly-instant simulation into something that
    could hang for minutes or trip a rate limit. Same shape as
    alpaca_client's mock-mode chain and arena.py's `_synthetic_scenario`.
    """
    from datetime import date, timedelta
    rnd = random.Random(event_seed)
    base = 100 + (hash(ticker) % 400)
    iv_percentile = rnd.randint(20, 95)
    near_expiration = date.today() + timedelta(days=21)
    far_expiration = date.today() + timedelta(days=49)
    return {
        "ticker": ticker,
        "underlying_price": base,
        "iv_percentile": iv_percentile,
        "expiration": near_expiration.isoformat(),
        "far_expiration": far_expiration.isoformat(),
        "strikes": [round(base * m, 1) for m in (0.90, 0.95, 1.00, 1.05, 1.10)],
    }


def header(title: str):
    line()
    line(BAR)
    line(f"  {title}")
    line(BAR)


@dataclass
class ExpAgent:
    """
    Deliberately duck-type-compatible with the SQLAlchemy `Agent` model:
    `talent.score_agent`/`talent.decide` only ever touch these attribute
    names, so this dataclass can be passed straight into them unmodified.
    """
    agent_id: str
    specialist_type: str
    ticker: Optional[str]
    capital: float
    total_pnl: float = 0.0
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    max_drawdown: float = 0.0
    risk_violations: int = 0
    status: str = "ACTIVE"
    fired: bool = False


def _event_seed(event: MarketEvent, idx: int, run_seed: int = 0) -> int:
    """Same event + same position in the sequence + same run_seed -> same
    simulated market outcome. Varying run_seed across repeated calls is
    what lets run_monte_carlo() draw independent samples while still
    keeping both arms' outcomes identical to each other within one run."""
    h = hashlib.md5(f"{event.event_id}-{idx}-{run_seed}".encode()).hexdigest()
    return int(h[:8], 16)


def _spec_from_exp(agent: ExpAgent, ticker: str) -> AgentSpec:
    tmpl = TEMPLATES[SpecialistType(agent.specialist_type)]
    return AgentSpec(
        agent_id=agent.agent_id, specialist_type=SpecialistType(agent.specialist_type),
        mandate=tmpl["mandate"], allowed_symbols=[ticker], allowed_strategies=tmpl["allowed_strategies"],
        capital=agent.capital, max_trade_risk=agent.capital * 0.10,
        permissions=tmpl["permissions"], status=AgentStatus.PROBATION,
    )


def _summarize(label: str, agents: Dict[str, ExpAgent], equity_curve: List[float],
               total_capital: float, trades_log: List[dict], arena_declines: int = 0) -> dict:
    final_equity = equity_curve[-1]
    total_pnl = final_equity - total_capital
    ret = total_pnl / total_capital if total_capital else 0.0

    deltas = [equity_curve[i + 1] - equity_curve[i] for i in range(len(equity_curve) - 1)]
    nonzero = [d for d in deltas if d != 0]
    if len(nonzero) >= 2:
        mean_d = statistics.mean(nonzero)
        std_d = statistics.pstdev(nonzero) or 1e-9
        sharpe_proxy = (mean_d / std_d) * (len(nonzero) ** 0.5)
    else:
        sharpe_proxy = 0.0

    peak = total_capital
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    executed = [t for t in trades_log if not t.get("blocked")]
    wins = [t for t in executed if t.get("pnl", 0) >= 0]
    win_rate = len(wins) / len(executed) if executed else 0.0
    fired = len([a for a in agents.values() if a.fired])

    return {
        "label": label,
        "final_equity": round(final_equity, 2),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round(ret, 4),
        "sharpe_proxy": round(sharpe_proxy, 2),
        "max_drawdown_pct": round(max_dd, 4),
        "capital_efficiency_pct": round(ret, 4),
        "win_rate": round(win_rate, 4),
        "trades_executed": len(executed),
        "trades_blocked": len(trades_log) - len(executed),
        "agents_used": len(agents),
        "agents_fired": fired,
        "arena_declines": arena_declines,
        "equity_curve": [round(e, 2) for e in equity_curve],
    }


def run_static_desk(events: List[MarketEvent], total_capital: float, hire_capital: float, run_seed: int = 0) -> dict:
    """
    Deploys the SAME starting capital per specialist type that Spinup gives
    each new hire, so both arms put an equal number of dollars at risk from
    the outset — the only difference is that Static's capital never moves
    afterward, however each agent performs.
    """
    types = [SpecialistType.EARNINGS, SpecialistType.MACRO, SpecialistType.VOLATILITY, SpecialistType.HEDGING]
    agents: Dict[str, ExpAgent] = {
        t.value: ExpAgent(agent_id=f"STATIC-{t.value.upper()}", specialist_type=t.value,
                           ticker=None, capital=hire_capital)
        for t in types
    }
    equity_curve = [total_capital]
    trades_log: List[dict] = []

    for idx, event in enumerate(events):
        specialist_type = EVENT_TO_SPECIALIST[event.event_type]
        agent = agents[specialist_type.value]
        spec = _spec_from_exp(agent, event.ticker)
        chain = _synthetic_chain(event.ticker, _event_seed(event, idx, run_seed))

        proposal = build_proposal(spec, event, chain)
        deployed = sum(a.capital for a in agents.values())
        risk = risk_evaluate(proposal, agent.capital, deployed, total_capital, event)
        if not risk.approved:
            agent.risk_violations += 1
            proposal = repair_proposal(spec, event, chain, risk.reasons, max_allowed_risk=agent.capital * 0.10)
            risk = risk_evaluate(proposal, agent.capital, deployed, total_capital, event)

        if not risk.approved:
            equity_curve.append(equity_curve[-1])
            trades_log.append({"event": idx, "agent": agent.agent_id, "blocked": True})
            continue

        pnl = simulate_close_seeded(proposal, _event_seed(event, idx, run_seed),
                                     specialist_type=specialist_type.value, lessons_count=0)
        equity_curve.append(equity_curve[-1] + pnl)
        trades_log.append({"event": idx, "agent": agent.agent_id, "pnl": pnl, "blocked": False})

    return _summarize("Static Desk", agents, equity_curve, total_capital, trades_log)


def run_spinup_desk(events: List[MarketEvent], total_capital: float, hire_capital: float, run_seed: int = 0) -> dict:
    agents: Dict[str, ExpAgent] = {}
    treasury = total_capital
    equity_curve = [total_capital]
    trades_log: List[dict] = []
    arena_declines = 0
    # Organizational memory, modeled at the level this experiment actually
    # tests: every LOSS teaches this specialist type something for next
    # time. This is what run_spinup_desk has that run_static_desk
    # deliberately never gets — the Static arm always passes
    # lessons_count=0 regardless of outcomes, however many trades it runs.
    type_lesson_counts: Dict[str, int] = {}

    for idx, event in enumerate(events):
        specialist_type = EVENT_TO_SPECIALIST[event.event_type]
        key = f"{specialist_type.value}:{event.ticker}"
        agent = agents.get(key)

        if agent is None or agent.fired:
            candidate_capital = min(hire_capital, treasury * 0.2)
            if candidate_capital <= 0:
                equity_curve.append(equity_curve[-1])
                trades_log.append({"event": idx, "blocked": True, "reason": "treasury exhausted"})
                continue

            trial_spec = AgentSpec(
                agent_id=f"{specialist_type.value.upper()}-{event.ticker}-{idx}",
                specialist_type=specialist_type, mandate=TEMPLATES[specialist_type]["mandate"],
                allowed_symbols=[event.ticker], allowed_strategies=TEMPLATES[specialist_type]["allowed_strategies"],
                capital=candidate_capital, max_trade_risk=candidate_capital * 0.10,
                permissions=TEMPLATES[specialist_type]["permissions"], status=AgentStatus.PROBATION,
            )
            arena_result = run_arena(trial_spec, event)
            if not arena_result.passed:
                arena_declines += 1
                equity_curve.append(equity_curve[-1])
                trades_log.append({"event": idx, "blocked": True, "reason": "arena declined"})
                continue

            agent = ExpAgent(agent_id=trial_spec.agent_id, specialist_type=specialist_type.value,
                              ticker=event.ticker, capital=candidate_capital)
            agents[key] = agent
            treasury -= candidate_capital

        spec = _spec_from_exp(agent, event.ticker)
        chain = _synthetic_chain(event.ticker, _event_seed(event, idx, run_seed))
        proposal = build_proposal(spec, event, chain)
        deployed = sum(a.capital for a in agents.values() if not a.fired)
        risk = risk_evaluate(proposal, agent.capital, deployed, treasury + deployed, event)
        if not risk.approved:
            agent.risk_violations += 1
            proposal = repair_proposal(spec, event, chain, risk.reasons, max_allowed_risk=agent.capital * 0.10)
            risk = risk_evaluate(proposal, agent.capital, deployed, treasury + deployed, event)

        if not risk.approved:
            equity_curve.append(equity_curve[-1])
            trades_log.append({"event": idx, "agent": agent.agent_id, "blocked": True})
            continue

        lessons_count = type_lesson_counts.get(specialist_type.value, 0)
        pnl = simulate_close_seeded(proposal, _event_seed(event, idx, run_seed),
                                     specialist_type=specialist_type.value, lessons_count=lessons_count)
        agent.trade_count += 1
        agent.total_pnl += pnl
        if pnl >= 0:
            agent.wins += 1
        else:
            agent.losses += 1
            agent.max_drawdown = max(agent.max_drawdown, abs(pnl) / agent.capital)
            type_lesson_counts[specialist_type.value] = type_lesson_counts.get(specialist_type.value, 0) + 1
        equity_curve.append(equity_curve[-1] + pnl)
        trades_log.append({"event": idx, "agent": agent.agent_id, "pnl": pnl, "blocked": False})

        if agent.trade_count % 2 == 0:
            decision = talent_decide(agent)
            delta = decision.new_capital - decision.previous_capital
            if decision.decision == "FIRE":
                agent.fired = True
                agent.status = "FIRED"
                treasury += decision.previous_capital
            else:
                agent.capital = decision.new_capital
                agent.status = decision.decision
                treasury -= delta

    return _summarize("Spinup Capital", agents, equity_curve, total_capital, trades_log,
                       arena_declines=arena_declines)


def print_comparison(static: dict, spinup: dict):
    header("STATIC DESK vs. SPINUP CAPITAL — CONTROL EXPERIMENT")
    line(f"{'Metric':<26}{'Static Desk':>18}{'Spinup Capital':>18}")
    line("-" * 62)
    rows = [
        ("Return", f"{static['return_pct']:+.1%}", f"{spinup['return_pct']:+.1%}"),
        ("Sharpe (proxy)", f"{static['sharpe_proxy']:.2f}", f"{spinup['sharpe_proxy']:.2f}"),
        ("Max drawdown", f"{static['max_drawdown_pct']:.1%}", f"{spinup['max_drawdown_pct']:.1%}"),
        ("Capital efficiency", f"{static['capital_efficiency_pct']:+.1%}", f"{spinup['capital_efficiency_pct']:+.1%}"),
        ("Win rate", f"{static['win_rate']:.0%}", f"{spinup['win_rate']:.0%}"),
        ("Trades executed", str(static["trades_executed"]), str(spinup["trades_executed"])),
        ("Trades blocked", str(static["trades_blocked"]), str(spinup["trades_blocked"])),
        ("Agents used", str(static["agents_used"]), str(spinup["agents_used"])),
        ("Agents fired", str(static["agents_fired"]), str(spinup["agents_fired"])),
        ("Arena declines", "n/a", str(spinup["arena_declines"])),
        ("Final equity", f"${static['final_equity']:,.0f}", f"${spinup['final_equity']:,.0f}"),
    ]
    for label, a, b in rows:
        line(f"{label:<26}{a:>18}{b:>18}")

    line()
    edge = spinup["return_pct"] - static["return_pct"]
    verdict = (
        f"Spinup's dynamic capital allocation produced {edge:+.1%} return vs. the static desk "
        f"on the identical event stream and identical simulated market outcomes — "
        "the only variable that differed was organizational adaptation."
        if edge > 0 else
        f"On this run, the static desk outperformed Spinup by {-edge:.1%}. Re-run with more "
        "events or a different --hire-capital to see how sensitive this is."
    )
    line(verdict)


def run(n_events: int = 24, total_capital: float = 100000, hire_capital: float = 10000, run_seed: int = 0):
    events = scenario_sequence(n_events)
    static_result = run_static_desk(events, total_capital, hire_capital, run_seed)
    spinup_result = run_spinup_desk(events, total_capital, hire_capital, run_seed)
    print_comparison(static_result, spinup_result)
    return static_result, spinup_result


def run_monte_carlo(n_events: int = 24, total_capital: float = 100000,
                     hire_capital: float = 10000, n_runs: int = 30) -> dict:
    """
    THE QUANTITATIVE CENTERPIECE: a single head-to-head run answers "did
    Spinup beat Static this time" — which could just be luck in either
    direction. This runs the SAME identical-event-stream comparison
    `n_runs` times, each with an independently-seeded outcome draw (see
    `_event_seed`), and reports the *distribution* of Spinup's edge over
    Static: mean, standard deviation, a 95% confidence interval (normal
    approximation — noted as such, not oversold as a rigorous hypothesis
    test), and the fraction of runs where Spinup actually won. That
    fraction — not any single run's headline number — is the honest answer
    to "does the organizational structure help, reliably, or did it just
    get lucky once."
    """
    edges: List[float] = []
    static_returns: List[float] = []
    spinup_returns: List[float] = []
    static_sharpes: List[float] = []
    spinup_sharpes: List[float] = []
    spinup_fired_counts: List[int] = []

    for seed in range(n_runs):
        events = scenario_sequence(n_events)
        static_result = run_static_desk(events, total_capital, hire_capital, run_seed=seed)
        spinup_result = run_spinup_desk(events, total_capital, hire_capital, run_seed=seed)
        edges.append(spinup_result["return_pct"] - static_result["return_pct"])
        static_returns.append(static_result["return_pct"])
        spinup_returns.append(spinup_result["return_pct"])
        static_sharpes.append(static_result["sharpe_proxy"])
        spinup_sharpes.append(spinup_result["sharpe_proxy"])
        spinup_fired_counts.append(spinup_result["agents_fired"])

    mean_edge = statistics.mean(edges)
    std_edge = statistics.pstdev(edges) if len(edges) > 1 else 0.0
    # Normal approximation for a 95% CI on the mean edge across runs — a
    # simple, honest estimate given a modest number of Monte Carlo runs,
    # not a claim of formal statistical significance.
    se = (std_edge / (len(edges) ** 0.5)) if len(edges) > 1 else 0.0
    ci_low, ci_high = mean_edge - 1.96 * se, mean_edge + 1.96 * se
    win_rate = sum(1 for e in edges if e > 0) / len(edges)

    return {
        "n_runs": n_runs,
        "n_events_per_run": n_events,
        "mean_edge_pct": round(mean_edge, 4),
        "std_edge_pct": round(std_edge, 4),
        "edge_95ci_low_pct": round(ci_low, 4),
        "edge_95ci_high_pct": round(ci_high, 4),
        "spinup_win_rate_across_runs": round(win_rate, 3),
        "mean_static_return_pct": round(statistics.mean(static_returns), 4),
        "mean_spinup_return_pct": round(statistics.mean(spinup_returns), 4),
        "mean_static_sharpe": round(statistics.mean(static_sharpes), 3),
        "mean_spinup_sharpe": round(statistics.mean(spinup_sharpes), 3),
        "mean_agents_fired_per_run": round(statistics.mean(spinup_fired_counts), 2),
        "all_edges_pct": [round(e, 4) for e in edges],
        "note": (
            "Normal-approximation 95% CI on the mean edge across Monte Carlo runs — "
            "a directional confidence estimate, not a formally validated hypothesis test."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=24)
    parser.add_argument("--capital", type=float, default=100000)
    parser.add_argument("--hire-capital", type=float, default=10000)
    parser.add_argument("--monte-carlo", type=int, default=0, help="Run N Monte Carlo repetitions instead of one head-to-head run")
    args = parser.parse_args()
    if args.monte_carlo:
        result = run_monte_carlo(args.events, args.capital, args.hire_capital, args.monte_carlo)
        header("MONTE CARLO — STATIC DESK vs. SPINUP CAPITAL")
        for k, v in result.items():
            if k != "all_edges_pct":
                line(f"{k:<32}{v}")
    else:
        run(args.events, args.capital, args.hire_capital)
