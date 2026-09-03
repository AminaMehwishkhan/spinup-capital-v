"""
Bull/Bear debate. Bull defends the trade proposal; Bear must identify a
SPECIFIC, falsifiable failure condition (not generic 'there is risk').
Runs on the LLM client, which falls back to a heuristic template offline.
"""
from __future__ import annotations
from backend.agents.llm_client import complete
from backend.schemas.models import TradeProposal, DebateResult, MarketEvent


def run_debate(proposal: TradeProposal, event: MarketEvent, chain: dict) -> DebateResult:
    system = (
        "You are running an internal trading-desk debate. Bull defends a proposed options "
        "trade in 2 sentences. Bear must attack it in 2 sentences and state ONE specific, "
        "measurable failure condition (e.g. 'if IV falls below X while price moves beyond Y'). "
        "Respond as JSON: {\"bull\": ..., \"bear\": ..., \"failure_condition\": ...}"
    )
    user = (
        f"Ticker: {proposal.ticker}\nStrategy: {proposal.strategy}\n"
        f"Max loss: {proposal.max_loss}\nMax profit: {proposal.max_profit}\n"
        f"Thesis: {proposal.thesis}\nIV percentile: {chain.get('iv_percentile')}\n"
        f"Days to event: {event.days_to_event}"
    )

    def heuristic():
        import json
        iv = chain.get("iv_percentile", 50)
        bull = (
            f"{proposal.strategy.replace('_', ' ').title()} on {proposal.ticker} captures the thesis "
            f"('{proposal.thesis}') with a defined max loss of ${proposal.max_loss:,.0f}."
        )
        bear = (
            f"IV percentile is {iv}, so pricing may already reflect the move; the structure's "
            f"edge shrinks if realized volatility undershoots implied volatility."
        )
        failure = (
            f"If {proposal.ticker} implied volatility falls more than 15 points while price stays "
            f"within the short strikes, theta decay will not offset the premium paid/collected as modeled."
        )
        return json.dumps({"bull": bull, "bear": bear, "failure_condition": failure})

    raw = complete(system, user, heuristic_fn=heuristic)
    import json
    try:
        data = json.loads(raw)
    except Exception:
        data = {"bull": raw, "bear": "No structured objection parsed.", "failure_condition": "N/A"}

    return DebateResult(
        bull_argument=data.get("bull", ""),
        bear_argument=data.get("bear", ""),
        bear_failure_condition=data.get("failure_condition", ""),
    )
