from __future__ import annotations
import json
from backend.agents.llm_client import complete
from backend.schemas.models import TradeProposal


def run_autopsy(proposal: TradeProposal, pnl: float, chain: dict) -> dict:
    """
    Returns {"narrative": str, "rule": str} — narrative is the human-readable
    autopsy shown in the UI; rule is a short, structured, machine-checkable
    lesson other specialists can act on (this is what gets stored in the
    Lesson table and retrieved by future proposals — see agents/memory.py).
    """
    won = pnl >= 0
    iv = chain.get("iv_percentile", 50)
    system = (
        "Write a trade autopsy as JSON: "
        '{"narrative": "2 sentences on what happened", '
        '"rule": "one short, specific, reusable trading rule, under 20 words"}'
    )
    user = (
        f"Ticker: {proposal.ticker}. Strategy: {proposal.strategy}. PnL: {pnl}. "
        f"IV percentile at entry: {iv}. Thesis: {proposal.thesis}"
    )

    def heuristic():
        long_premium = proposal.strategy in {"calendar", "long_call", "long_put"}
        if won:
            narrative = (
                f"The {proposal.strategy.replace('_',' ')} on {proposal.ticker} closed +${pnl:,.0f}, "
                f"validating the thesis at {iv}th-percentile IV."
            )
            rule = (
                f"Favor {proposal.strategy.replace('_',' ')} structures near {iv}th-percentile IV "
                f"for this ticker class."
            )
        else:
            narrative = (
                f"The {proposal.strategy.replace('_',' ')} on {proposal.ticker} closed -${abs(pnl):,.0f}; "
                f"the move exceeded the structure's break-evens faster than modeled."
            )
            if long_premium and iv >= 80:
                rule = "Avoid long-premium structures when IV percentile > 80 close to a binary event."
            else:
                rule = f"Reduce size or widen strikes on {proposal.strategy.replace('_',' ')} above {iv}th-percentile IV."
        return json.dumps({"narrative": narrative, "rule": rule})

    raw = complete(system, user, heuristic_fn=heuristic)
    try:
        data = json.loads(raw)
    except Exception:
        data = {"narrative": raw, "rule": "No structured rule parsed."}
    return data
