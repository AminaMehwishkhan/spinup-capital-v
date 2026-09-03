"""
HISTORICAL REPLAY / BACKTESTING.

Unlike the interactive demo (`simulate_close` — a documented, intentional
coin-flip approximation for a fast, always-succeeds live demo) and the
Static-vs-Spinup control experiment (which compares organizational logic
on identical *simulated* outcomes), this module asks a different question:
"if this specialist had actually been trading this ticker over the last N
days, using its real strategy-selection and risk logic, would it have
made money?" — settled against REAL historical prices, with a genuine,
deterministic options-payoff calculation, not a random draw.

Walk-forward design: starting after enough bars for a trailing-volatility
lookback, take non-overlapping windows of `holding_period_days`. At each
step: compute a REAL trailing realized-volatility percentile from the
actual price history (not fabricated), build a real chain snapshot at
that day's actual price, run the SAME `specialist_trader.build_proposal`
logic used everywhere else in the codebase, then settle the position using
the REAL price `holding_period_days` later via intrinsic-value payoff math.

Known, documented simplification: this settles every strategy AS IF held
to the near expiration, using intrinsic value there. For calendar spreads
(whose far leg still has time value at near-expiration) it additionally
estimates the far leg's remaining time value with the same
Brenner–Subrahmanyam approximation used in trading/options.py, rather than
a full option-pricing model. This is a backtest engine for directional
strategy comparison, not a broker-grade options simulator.
"""
from __future__ import annotations
import statistics
from datetime import date, timedelta
from typing import List

from backend.config import settings
from backend.backtest.data import fetch_daily_bars, Bar
from backend.schemas.models import AgentSpec, SpecialistType, AgentStatus, MarketEvent, EventType, OptionLeg
from backend.agents.specialist_factory import TEMPLATES
from backend.agents.specialist_trader import build_proposal
from backend.trading.options import STRATEGY_BUILDERS

TRAILING_VOL_WINDOW = 20
SPECIALIST_TO_EVENT_TYPE = {
    "earnings": EventType.EARNINGS,
    "macro": EventType.MACRO,
    "volatility": EventType.VOLATILITY_ANOMALY,
    "hedging": EventType.DRAWDOWN,
}


def _intrinsic(option_type: str, strike: float, settle: float) -> float:
    return max(settle - strike, 0.0) if option_type == "call" else max(strike - settle, 0.0)


def _settle_payoff(legs: List[OptionLeg], max_loss: float, max_profit: float, strategy: str,
                    settle_price: float, underlying_at_entry: float, iv_percentile: float,
                    near_days: int, far_days_extra: int) -> float:
    """Real, deterministic P&L at settlement — no randomness."""
    is_credit_strategy = strategy == "iron_condor"

    if strategy == "calendar":
        # Near leg (short) expires worthless or intrinsic at settle_price;
        # far leg still has remaining time value, estimated the same way
        # trading/options.py prices it originally, using the ENTRY IV as a
        # forward estimate (a documented simplification — real IV would
        # have moved too).
        near_leg, far_leg = legs[0], legs[1]
        near_intrinsic = _intrinsic(near_leg.option_type, near_leg.strike, settle_price)
        iv = 0.15 + (iv_percentile / 100.0) * 0.65
        far_remaining_value = 0.4 * settle_price * iv * (far_days_extra / 365.0) ** 0.5
        # We're short the near leg (sold it) and long the far leg (bought it).
        settlement_value = (-near_intrinsic + far_remaining_value) * 100
        debit_paid = max_loss  # calendar's max_loss == the debit paid, by construction
        pnl = settlement_value - debit_paid
    else:
        settlement_value = 0.0
        for leg in legs:
            intrinsic = _intrinsic(leg.option_type, leg.strike, settle_price)
            sign = 1 if leg.side == "buy" else -1
            settlement_value += intrinsic * leg.ratio * sign
        settlement_value *= 100
        entry_flow = max_profit if is_credit_strategy else -max_loss
        pnl = entry_flow + settlement_value

    return round(max(min(pnl, max_profit), -max_loss), 2)


def run_backtest(ticker: str, specialist_type: str, lookback_days: int = 180,
                  holding_period_days: int = 21, capital: float = 10000) -> dict:
    try:
        stype = SpecialistType(specialist_type)
    except ValueError:
        return {"error": f"Unknown specialist_type '{specialist_type}'. Use one of: "
                          f"{[t.value for t in SpecialistType]}"}

    tmpl = TEMPLATES[stype]
    bars = fetch_daily_bars(ticker, lookback_days)
    min_needed = TRAILING_VOL_WINDOW + holding_period_days + 1
    if len(bars) < min_needed:
        return {"error": f"Not enough price history ({len(bars)} bars) for a {holding_period_days}-day "
                          f"holding period with a {TRAILING_VOL_WINDOW}-day vol lookback — need at least {min_needed}."}

    closes = [b["close"] for b in bars]
    dates = [b["date"] for b in bars]

    log_returns = [
        (closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))
    ]
    trailing_vol = [None] * len(closes)
    for i in range(TRAILING_VOL_WINDOW, len(closes)):
        window = log_returns[i - TRAILING_VOL_WINDOW:i]
        trailing_vol[i] = statistics.pstdev(window) * (252 ** 0.5)  # annualized realized vol

    valid_vols = sorted(v for v in trailing_vol if v is not None)

    def _percentile_rank(v: float) -> float:
        if not valid_vols:
            return 50.0
        below = sum(1 for x in valid_vols if x <= v)
        return round(100 * below / len(valid_vols), 1)

    equity = capital
    equity_curve = [equity]
    trades_log = []

    t = TRAILING_VOL_WINDOW
    while t + holding_period_days < len(closes):
        vol = trailing_vol[t]
        if vol is None:
            t += holding_period_days
            continue

        entry_price = closes[t]
        entry_date_str = dates[t]
        iv_percentile = _percentile_rank(vol)
        entry_date = date.fromisoformat(entry_date_str[:10]) if len(entry_date_str) >= 10 else date.today()
        near_exp = entry_date + timedelta(days=holding_period_days)
        far_exp = near_exp + timedelta(days=28)

        chain = {
            "ticker": ticker,
            "underlying_price": entry_price,
            "iv_percentile": iv_percentile,
            "expiration": near_exp.isoformat(),
            "far_expiration": far_exp.isoformat(),
            "strikes": [round(entry_price * m, 2) for m in (0.90, 0.95, 1.00, 1.05, 1.10)],
        }

        spec = AgentSpec(
            agent_id=f"BACKTEST-{stype.value.upper()}-{ticker}", specialist_type=stype,
            mandate=tmpl["mandate"], allowed_symbols=[ticker], allowed_strategies=tmpl["allowed_strategies"],
            capital=capital, max_trade_risk=capital * 0.10, permissions=tmpl["permissions"],
            status=AgentStatus.PROBATION,
        )
        synthetic_event = MarketEvent(
            event_id=f"backtest-{entry_date_str}", event_type=SPECIALIST_TO_EVENT_TYPE[stype.value],
            ticker=ticker, description="Historical replay window", days_to_event=None,
        )

        proposal = build_proposal(spec, synthetic_event, chain, lessons=[])
        settle_price = closes[t + holding_period_days]

        pnl = _settle_payoff(
            proposal.legs, proposal.max_loss, proposal.max_profit, proposal.strategy,
            settle_price, entry_price, iv_percentile, holding_period_days, 28,
        )

        equity += pnl
        equity_curve.append(round(equity, 2))
        trades_log.append({
            "entry_date": entry_date_str, "strategy": proposal.strategy,
            "entry_price": entry_price, "settle_price": settle_price,
            "iv_percentile": iv_percentile, "pnl": pnl,
        })
        t += holding_period_days

    if not trades_log:
        return {"error": "No trade windows produced — try a longer lookback_days."}

    wins = [tr for tr in trades_log if tr["pnl"] >= 0]
    peak = capital
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    return {
        "ticker": ticker, "specialist_type": stype.value,
        "data_source": "synthetic (MOCK mode — not real market data; add Alpaca keys for a real backtest)"
                        if settings.ALPACA_MOCK else "alpaca_historical",
        "lookback_days": lookback_days, "holding_period_days": holding_period_days,
        "starting_capital": capital, "final_equity": round(equity, 2),
        "total_return_pct": round((equity - capital) / capital, 4),
        "win_rate": round(len(wins) / len(trades_log), 3),
        "max_drawdown_pct": round(max_dd, 4),
        "trades": len(trades_log),
        "equity_curve": equity_curve,
        "trade_log": trades_log,
    }
