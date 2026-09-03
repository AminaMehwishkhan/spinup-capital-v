"""
RISK GOVERNOR — deterministic, rule-based, no LLM in the loop.

Design rule from the spec: "The LLM proposes. Deterministic policy decides.
Alpaca executes." This module is that policy decider. Nothing here is
probabilistic or model-generated; every rule is plain Python so it's fully
auditable and impossible for a prompt-injected or hallucinating agent to
talk its way around.
"""
from __future__ import annotations
from typing import List
from backend.config import settings
from backend.schemas.models import TradeProposal, RiskCheckResult, MarketEvent


UNDEFINED_RISK_STRATEGIES = {"naked_call", "naked_put", "short_straddle_naked"}


def evaluate(
    proposal: TradeProposal,
    agent_capital: float,
    deployed_capital_across_firm: float,
    treasury_balance: float,
    event: MarketEvent | None = None,
) -> RiskCheckResult:
    reasons: List[str] = []
    checked: List[str] = []

    # 1. Defined risk only
    checked.append("defined_risk_structure")
    if settings.REQUIRE_DEFINED_RISK and proposal.strategy in UNDEFINED_RISK_STRATEGIES:
        reasons.append(f"Strategy '{proposal.strategy}' is undefined-risk; only defined-risk structures are permitted.")

    # 2. Max loss vs agent's own risk budget
    checked.append("max_trade_risk_vs_agent_capital")
    trade_risk_limit = agent_capital * settings.MAX_TRADE_RISK_PCT_OF_AGENT_CAPITAL
    if proposal.max_loss > trade_risk_limit:
        reasons.append(
            f"Max loss ${proposal.max_loss:,.0f} exceeds this agent's per-trade risk limit "
            f"of ${trade_risk_limit:,.0f} ({settings.MAX_TRADE_RISK_PCT_OF_AGENT_CAPITAL:.0%} of ${agent_capital:,.0f} capital)."
        )

    # 3. Firm-wide exposure ceiling
    checked.append("portfolio_exposure_ceiling")
    projected_exposure = deployed_capital_across_firm + proposal.max_loss
    exposure_ceiling = treasury_balance * settings.MAX_PORTFOLIO_EXPOSURE_PCT
    if projected_exposure > exposure_ceiling:
        reasons.append(
            f"Projected firm-wide exposure ${projected_exposure:,.0f} would exceed the "
            f"{settings.MAX_PORTFOLIO_EXPOSURE_PCT:.0%} exposure ceiling (${exposure_ceiling:,.0f})."
        )

    # 4. Earnings-window guard for long-premium trades
    checked.append("earnings_window_long_premium_guard")
    if event is not None and event.days_to_event is not None:
        is_long_premium = proposal.strategy in {"calendar", "long_call", "long_put"}
        if is_long_premium and event.days_to_event <= settings.MIN_DAYS_TO_EARNINGS_FOR_LONG_PREMIUM:
            reasons.append(
                f"Long-premium strategy proposed only {event.days_to_event} day(s) before earnings "
                f"(minimum safe window is {settings.MIN_DAYS_TO_EARNINGS_FOR_LONG_PREMIUM} days) — high IV-crush risk."
            )

    # 5. Sanity: profit/loss numbers must be internally consistent
    checked.append("pnl_sanity_check")
    if proposal.max_loss <= 0:
        reasons.append("Max loss must be a positive, defined number.")
    if proposal.max_profit <= 0:
        reasons.append("Max profit must be a positive, defined number.")

    return RiskCheckResult(approved=(len(reasons) == 0), reasons=reasons, checked_rules=checked)
