"""
AGENT ARENA — before a newly spun-up specialist ever touches real firm
capital, it has to prove itself against a batch of synthetic scenarios.

This mirrors how a real trading firm treats a new hire: paper-trade
probation before a live book, not "here's $10,000, good luck." It also
gives the Managing Partner an honest answer to "how do you know this new
agent won't blow up the account on trade #1?" — because trade #1 was
never on real capital.

Nothing here touches the broker, the treasury, or the agents table. It's
a pure simulation using the same deterministic Risk Governor and the same
strategy-building logic the agent would use for real, so a pass here means
something concrete: this mandate, against this scenario distribution,
clears the firm's own risk bar most of the time.
"""
from __future__ import annotations
import random
from datetime import date, timedelta
from typing import List

from backend.config import settings
from backend.schemas.models import AgentSpec, MarketEvent, ArenaTrialResult, ArenaResult
from backend.agents.specialist_trader import build_proposal
from backend.agents.risk_governor import evaluate as risk_evaluate
from backend.trading.execution import simulate_close


def _synthetic_scenario(ticker: str, seed: int) -> dict:
    """A deterministic-but-varied synthetic chain snapshot for one trial."""
    rnd = random.Random(seed)
    base = 100 + (hash(ticker) % 400)
    iv = rnd.randint(20, 95)
    near_expiration = date.today() + timedelta(days=21)
    far_expiration = date.today() + timedelta(days=49)  # real ~4-week tenor gap, so calendar candidates
    return {                                             # actually get exercised in the Arena, not skipped
        "ticker": ticker,
        "underlying_price": base,
        "iv_percentile": iv,
        "expiration": near_expiration.isoformat(),
        "far_expiration": far_expiration.isoformat(),
        "strikes": [round(base * m, 1) for m in (0.90, 0.95, 1.00, 1.05, 1.10)],
    }


def run_arena(spec: AgentSpec, event: MarketEvent, n_trials: int | None = None) -> ArenaResult:
    n_trials = n_trials or settings.ARENA_TRIALS
    trials: List[ArenaTrialResult] = []

    for i in range(n_trials):
        chain = _synthetic_scenario(event.ticker, seed=(hash(spec.agent_id) + i) & 0xFFFFFFFF)
        scenario_event = event.model_copy(update={"iv_percentile": chain["iv_percentile"]})

        proposal = build_proposal(spec, scenario_event, chain)
        # Arena trials never touch real firm exposure — evaluated against the
        # candidate's own proposed capital only.
        risk = risk_evaluate(proposal, spec.capital, 0.0, spec.capital, scenario_event)
        pnl = simulate_close(proposal, win_bias=0.5) if risk.approved else 0.0

        trials.append(ArenaTrialResult(
            scenario_iv=chain["iv_percentile"], strategy=proposal.strategy,
            risk_approved=risk.approved, pnl=pnl,
        ))

    approved = [t for t in trials if t.risk_approved]
    win_rate = (sum(1 for t in approved if t.pnl >= 0) / len(approved)) if approved else 0.0
    avg_pnl = (sum(t.pnl for t in approved) / len(approved)) if approved else 0.0
    risk_pass_rate = len(approved) / len(trials) if trials else 0.0

    passed = (
        win_rate >= settings.ARENA_MIN_WIN_RATE
        and risk_pass_rate >= settings.ARENA_MIN_RISK_PASS_RATE
    )

    reasoning = (
        f"{len(approved)}/{len(trials)} trial proposals cleared the Risk Governor "
        f"(risk pass rate {risk_pass_rate:.0%}, bar {settings.ARENA_MIN_RISK_PASS_RATE:.0%}); "
        f"of those, win rate {win_rate:.0%} (bar {settings.ARENA_MIN_WIN_RATE:.0%}), "
        f"avg simulated PnL ${avg_pnl:,.0f}. "
        + ("Cleared for hire with real capital." if passed else "Did not meet the bar — hire declined.")
    )

    return ArenaResult(
        trials=trials, win_rate=win_rate, avg_pnl=avg_pnl,
        risk_pass_rate=risk_pass_rate, passed=passed, reasoning=reasoning,
    )
