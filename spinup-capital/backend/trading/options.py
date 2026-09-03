"""
Deterministic strategy builders. The LLM decides *which* strategy and *why*
(thesis); this module turns that decision into concrete, defined-risk legs
and computes max loss / max profit with plain arithmetic — never guessed
by an LLM, per the "deterministic code for numbers" design rule.
"""
from __future__ import annotations
from typing import Tuple, List
from backend.schemas.models import OptionLeg


def build_iron_condor(chain: dict, width: float = None) -> Tuple[List[OptionLeg], float, float]:
    strikes = sorted(chain["strikes"])
    exp = chain["expiration"]
    underlying_price = chain.get("underlying_price", strikes[len(strikes) // 2])

    # The protective (long) wings are always the outermost available
    # strikes — this guarantees a real, non-zero wing width exists as long
    # as there are at least 3 strikes, regardless of how far the target
    # percentage would otherwise land. Short strikes are percentage-target
    # selected, but constrained to the INTERIOR strikes (excluding the two
    # outermost) so they can never collide with or cross the long wings —
    # an earlier version of this fix could pick a short strike AT the
    # chain's edge, leaving no room for a long wing and producing a
    # degenerate $0/$0 structure that the Risk Governor then rejected
    # outright for every real chain narrower than the target width.
    put_long, call_long = strikes[0], strikes[-1]
    inner_strikes = strikes[1:-1]

    if not inner_strikes:
        # Only 2 strikes total in this window — there's no room for a real
        # iron condor here. Return a deliberately invalid (zero-width)
        # result so the Risk Governor's pnl-sanity check explicitly
        # rejects it with a clear reason, rather than guessing a size.
        put_short, call_short = put_long, call_long
    else:
        put_short = _nearest_strike(inner_strikes, underlying_price * 0.95)
        call_short = _nearest_strike(inner_strikes, underlying_price * 1.05)
        if put_short >= call_short:
            # Target percentages collapsed onto the same or crossed strike
            # (a very narrow interior) — fall back to the two interior
            # strikes nearest ATM instead of an arbitrary pick.
            put_short = min(inner_strikes, key=lambda s: abs(s - underlying_price))
            remaining = [s for s in inner_strikes if s != put_short]
            call_short = min(remaining, key=lambda s: abs(s - underlying_price)) if remaining else put_short

    legs = [
        OptionLeg(side="sell", option_type="put", strike=put_short, expiration=exp),
        OptionLeg(side="buy", option_type="put", strike=put_long, expiration=exp),
        OptionLeg(side="sell", option_type="call", strike=call_short, expiration=exp),
        OptionLeg(side="buy", option_type="call", strike=call_long, expiration=exp),
    ]
    wing_width = min(put_short - put_long, call_long - call_short)
    credit_estimate = round(wing_width * 0.28, 2)   # synthetic-but-plausible credit
    max_loss = round((wing_width - credit_estimate) * 100, 2)   # per 1 contract, x100 multiplier
    max_profit = round(credit_estimate * 100, 2)
    return legs, max_loss, max_profit


def _nearest_strike(strikes: List[float], target: float) -> float:
    return min(strikes, key=lambda s: abs(s - target))


def build_vertical_spread(chain: dict, bullish: bool = True) -> Tuple[List[OptionLeg], float, float]:
    strikes = sorted(chain["strikes"])
    exp = chain["expiration"]
    underlying_price = chain.get("underlying_price", strikes[len(strikes) // 2])

    # Target the spread's width as a PERCENTAGE of the underlying price
    # (~5%), then snap each leg to the nearest actually-available strike —
    # rather than always using fixed index offsets (strikes[1]/strikes[3]).
    # The mock chain's synthetic strikes are evenly spaced at exactly ±10%
    # of price, so an index offset happens to give a small, predictable
    # dollar width there. Real option chains have arbitrary fixed-dollar
    # strike spacing that varies by ticker and price tier — the same index
    # offset against a real chain can produce a MUCH wider dollar spread
    # than intended, which is what was blowing every live trade's max_loss
    # past the Risk Governor's per-trade risk limit. Targeting a percentage
    # width keeps position sizing consistent regardless of the real
    # chain's actual strike granularity.
    atm_strike = _nearest_strike(strikes, underlying_price)
    if bullish:
        long_strike = atm_strike
        short_strike = _nearest_strike(strikes, underlying_price * 1.05)
        if short_strike <= long_strike:
            short_strike = min([s for s in strikes if s > long_strike], default=strikes[-1])
        legs = [
            OptionLeg(side="buy", option_type="call", strike=long_strike, expiration=exp),
            OptionLeg(side="sell", option_type="call", strike=short_strike, expiration=exp),
        ]
    else:
        long_strike = atm_strike
        short_strike = _nearest_strike(strikes, underlying_price * 0.95)
        if short_strike >= long_strike:
            short_strike = max([s for s in strikes if s < long_strike], default=strikes[0])
        legs = [
            OptionLeg(side="buy", option_type="put", strike=long_strike, expiration=exp),
            OptionLeg(side="sell", option_type="put", strike=short_strike, expiration=exp),
        ]
    width = abs(short_strike - long_strike)
    debit_estimate = round(width * 0.45, 2)
    max_loss = round(debit_estimate * 100, 2)
    max_profit = round((width - debit_estimate) * 100, 2)
    return legs, max_loss, max_profit


def build_calendar_spread(chain: dict) -> Tuple[List[OptionLeg], float, float]:
    strikes = sorted(chain["strikes"])
    atm = strikes[2]
    near_exp = chain["expiration"]
    far_exp = chain.get("far_expiration")
    if not far_exp or far_exp == near_exp:
        raise ValueError(
            "build_calendar_spread requires chain['far_expiration'] to be a real date "
            "later than chain['expiration'] — a calendar spread sells a near-dated "
            "contract and buys a longer-dated one at the SAME strike. Without a "
            "distinct far expiration this degenerates into two offsetting legs on "
            "the identical contract, which is not a calendar spread and cannot be "
            "submitted as a meaningful multi-leg order."
        )
    legs = [
        OptionLeg(side="sell", option_type="call", strike=atm, expiration=near_exp),
        OptionLeg(side="buy", option_type="call", strike=atm, expiration=far_exp),
    ]

    # --- Debit pricing: was a hardcoded $150 regardless of underlying price,
    # IV, or tenor — wrong by construction (a $50 stock and a $500 stock do
    # not cost the same $150 calendar debit). This uses a standard
    # Brenner–Subrahmanyam napkin approximation for an ATM option's time
    # value: price ≈ 0.4 * S * sigma * sqrt(T). It's a coarse estimate, not
    # a real pricer — swap for a live premium from the chain (or a proper
    # Black-Scholes calc) before sizing real capital — but it correctly
    # scales with price, volatility, and the actual day-count gap between
    # the two legs, which the previous constant did not.
    underlying_price = chain.get("underlying_price", atm)
    iv_percentile = chain.get("iv_percentile", 50)
    iv = 0.15 + (iv_percentile / 100.0) * 0.65  # percentile (0-100) -> rough annualized vol (15%-80%)

    from datetime import date as _date

    def _days_out(exp_str: str) -> int:
        y, m, d = map(int, exp_str.split("-"))
        return max((_date(y, m, d) - _date.today()).days, 1)

    near_days, far_days = _days_out(near_exp), _days_out(far_exp)
    near_value = 0.4 * underlying_price * iv * (near_days / 365.0) ** 0.5
    far_value = 0.4 * underlying_price * iv * (far_days / 365.0) ** 0.5
    # The near-dated short leg is worth less than the far-dated long leg
    # (less time value) — the spread between them is the net debit paid.
    # Floor at $0.50/contract so a near-zero-vol edge case doesn't produce
    # a degenerate $0 position.
    debit_estimate = round(max(far_value - near_value, 0.5) * 100, 2)  # x100 contract multiplier

    max_loss = debit_estimate
    # A long calendar's max profit is capped and only realized if the
    # underlying pins near the short strike into near-dated expiration —
    # unlike a vertical spread, it is NOT a simple multiple of the debit.
    # ~60% of debit is a conservative, documented napkin ceiling for an ATM
    # calendar (replacing the previous unconditional 1.8x, which overstated
    # the payoff for every underlying/vol combination).
    max_profit = round(debit_estimate * 0.6, 2)
    return legs, max_loss, max_profit


STRATEGY_BUILDERS = {
    "iron_condor": build_iron_condor,
    "vertical_call_spread": lambda chain: build_vertical_spread(chain, bullish=True),
    "vertical_put_spread": lambda chain: build_vertical_spread(chain, bullish=False),
    "calendar": build_calendar_spread,
}
