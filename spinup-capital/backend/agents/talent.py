"""
HEAD OF TALENT — deterministic scoring, no LLM. This is the capital-
allocation engine: the thing that makes Spinup an "organization" rather
than a bag of independent bots.
"""
from __future__ import annotations
from backend.schemas.models import TalentDecision
from backend.database.models import Agent

# Weights sum to 1.0 — shown transparently, never hidden behind "the LLM decided".
W_ROI = 0.35
W_WIN_RATE = 0.20
W_DRAWDOWN = 0.20
W_VIOLATIONS = 0.15
W_CONSISTENCY = 0.10


def score_agent(agent: Agent) -> float:
    roi = (agent.total_pnl / agent.capital) if agent.capital else 0.0
    win_rate = (agent.wins / agent.trade_count) if agent.trade_count else 0.0
    drawdown_penalty = min(agent.max_drawdown, 1.0)          # 0 (none) .. 1 (100% dd)
    violation_penalty = min(agent.risk_violations * 0.15, 1.0)
    consistency = 1.0 if agent.trade_count >= 3 else agent.trade_count / 3

    roi_score = max(min(roi * 4, 1.0), -1.0)   # roughly maps +/-25% roi to +/-1.0
    score = (
        W_ROI * roi_score
        + W_WIN_RATE * win_rate
        - W_DRAWDOWN * drawdown_penalty
        - W_VIOLATIONS * violation_penalty
        + W_CONSISTENCY * consistency
    )
    # Normalize to a 0-100 scale for readability
    return round(max(min((score + 1) * 50, 100), 0), 1)


def decide(agent: Agent) -> TalentDecision:
    if agent.trade_count < 2:
        return TalentDecision(
            agent_id=agent.agent_id,
            decision="PROBATION",
            score=0.0,
            previous_capital=agent.capital,
            new_capital=agent.capital,
            reasoning="Not enough closed trades yet for a performance review (minimum 2).",
        )

    score = score_agent(agent)
    prev_capital = agent.capital

    if score >= 75:
        new_capital = round(prev_capital * 1.5, 2)
        decision = "PROMOTE"
        reasoning = (
            f"Score {score}/100: strong risk-adjusted return with {agent.wins}/{agent.trade_count} "
            f"wins and {agent.risk_violations} risk violations. Capital increased."
        )
    elif score >= 50:
        new_capital = prev_capital
        decision = "KEEP"
        reasoning = f"Score {score}/100: acceptable performance. Capital unchanged, remains on watch."
    elif score >= 30:
        new_capital = round(prev_capital * 0.5, 2)
        decision = "PROBATION"
        reasoning = f"Score {score}/100: underperforming. Capital cut by half pending improvement."
    else:
        new_capital = 0.0
        decision = "FIRE"
        reasoning = (
            f"Score {score}/100: poor risk-adjusted performance "
            f"(drawdown {agent.max_drawdown:.1%}, {agent.risk_violations} violations). Terminated."
        )

    return TalentDecision(
        agent_id=agent.agent_id,
        decision=decision,
        score=score,
        previous_capital=prev_capital,
        new_capital=new_capital,
        reasoning=reasoning,
    )
