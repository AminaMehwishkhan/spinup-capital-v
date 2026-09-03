"""
Thin wrapper around Alpaca's paper trading API.

Runs in one of two modes, chosen automatically from config:
  - LIVE-PAPER: real calls to Alpaca's paper endpoint (needs ALPACA_API_KEY / SECRET)
  - MOCK: fully offline, deterministic simulated fills/quotes. No network calls.

This is the ONLY module in the codebase allowed to talk to the broker.
Every other module goes through backend.trading.execution.ExecutionGateway,
never directly through here — that's the architectural guarantee that no
agent can bypass risk review.
"""
from __future__ import annotations
import random
import string
from datetime import date, timedelta
from typing import List, Optional
from backend.config import settings
from backend.schemas.models import OptionLeg


def _rand_id(prefix: str) -> str:
    return f"{prefix}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"


class AlpacaClient:
    def __init__(self):
        self.mock = settings.ALPACA_MOCK
        self._sdk = None
        if not self.mock:
            self._init_live()

    def _init_live(self):
        # Imported lazily so the package isn't required in pure-mock dev.
        from alpaca.trading.client import TradingClient
        self._sdk = TradingClient(
            settings.ALPACA_API_KEY,
            settings.ALPACA_SECRET_KEY,
            paper=True,
        )
        self._option_data_client = None
        self._stock_data_client = None

    # ---------------------------------------------------------------- account
    def get_account(self) -> dict:
        if self.mock:
            return {"cash": settings.STARTING_TREASURY, "buying_power": settings.STARTING_TREASURY, "mock": True}
        acct = self._sdk.get_account()
        return {"cash": float(acct.cash), "buying_power": float(acct.buying_power), "mock": False}

    # ------------------------------------------------------------- options chain
    def get_option_chain_snapshot(self, ticker: str) -> dict:
        """
        Returns a lightweight synthetic-but-plausible chain snapshot in mock mode.
        In LIVE mode, calls Alpaca's real option chain endpoint (alpaca-py's
        OptionHistoricalDataClient.get_option_chain).
        """
        if self.mock or self._sdk is None:
            base = 100 + (hash(ticker) % 400)
            iv_percentile = 30 + (hash(ticker + "iv") % 70)
            near_expiration = date.today() + timedelta(days=21)
            far_expiration = date.today() + timedelta(days=49)  # ~4 weeks after near — a real calendar tenor gap
            return {
                "ticker": ticker,
                "underlying_price": base,
                "iv_percentile": iv_percentile,
                "expiration": near_expiration.isoformat(),
                "far_expiration": far_expiration.isoformat(),
                "strikes": [round(base * m, 1) for m in (0.90, 0.95, 1.00, 1.05, 1.10)],
            }
        return self._get_live_option_chain(ticker)

    def _get_live_option_chain(self, ticker: str) -> dict:
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        from alpaca.data.enums import OptionsFeed

        if self._option_data_client is None:
            self._option_data_client = OptionHistoricalDataClient(
                settings.ALPACA_API_KEY, settings.ALPACA_SECRET_KEY
            )

        # Target an expiration ~2-6 weeks out. Adjust if a specialist's mandate
        # needs a different tenor (e.g. weekly earnings plays vs. monthly macro).
        exp_gte = date.today() + timedelta(days=14)
        exp_lte = date.today() + timedelta(days=45)
        feed = OptionsFeed.OPRA if settings.ALPACA_OPTIONS_FEED == "opra" else OptionsFeed.INDICATIVE

        try:
            chain = self._option_data_client.get_option_chain(
                OptionChainRequest(
                    underlying_symbol=ticker,
                    expiration_date_gte=exp_gte,
                    expiration_date_lte=exp_lte,
                    feed=feed,
                )
            )
        except Exception as e:
            raise RuntimeError(
                f"Alpaca live option chain request failed for {ticker}: {e}. Check that "
                "(1) your API keys are valid, (2) your account has an options data "
                "entitlement for the feed you configured (ALPACA_OPTIONS_FEED="
                f"'{settings.ALPACA_OPTIONS_FEED}'), and (3) {ticker} has listed options."
            ) from e

        if not chain:
            raise RuntimeError(
                f"Alpaca returned an empty option chain for {ticker} in the "
                f"{exp_gte}–{exp_lte} expiration window. Try a more liquid ticker "
                "or widen the window in _get_live_option_chain()."
            )

        parsed = self._parse_chain_symbols(chain)
        if not parsed:
            raise RuntimeError(
                f"Could not parse any contract symbols from the live chain for {ticker}. "
                "Alpaca may have changed its OCC symbol format — check "
                "_parse_chain_symbols() against a live sample."
            )

        # Pick the expiration closest to a 21-day target tenor.
        target_days = 21
        def _distance(exp_str: str) -> int:
            y, m, d = map(int, exp_str.split("-"))
            return abs((date(y, m, d) - date.today()).days - target_days)

        chosen_expiration = min({p["expiration"] for p in parsed}, key=_distance)
        same_exp = [p for p in parsed if p["expiration"] == chosen_expiration]
        strikes = sorted({p["strike"] for p in same_exp})

        # A calendar spread needs a SECOND, genuinely later expiration at the
        # same strike. Pick whichever available expiration is closest to
        # ~28 days after the near one, among dates strictly after it. If the
        # live chain only has one expiration in this window, far_expiration
        # is left None — build_calendar_spread() will refuse to build a
        # calendar rather than silently submitting a degenerate same-date
        # spread, and the Managing Partner should route calendar-preferring
        # events to a strategy that IS available instead.
        far_candidates = [e for e in {p["expiration"] for p in parsed} if e > chosen_expiration]
        far_expiration = None
        if far_candidates:
            target_far_days = 28

            def _far_distance(exp_str: str) -> int:
                y, m, d = map(int, exp_str.split("-"))
                return abs((date(y, m, d) - date.fromisoformat(chosen_expiration)).days - target_far_days)

            far_expiration = min(far_candidates, key=_far_distance)

        if len(strikes) < 5:
            raise RuntimeError(
                f"Only {len(strikes)} strikes available for {ticker} at {chosen_expiration}; "
                "need at least 5 for the strategy builders in trading/options.py. Try a more "
                "liquid ticker."
            )

        # --- Implied volatility ---
        # NOTE: this is a documented approximation, not a true percentile rank.
        # Alpaca's chain snapshot gives you CURRENT implied volatility per
        # contract, not a historical percentile. A real percentile needs a
        # time series of past IV readings for this ticker, which isn't
        # available from a single chain snapshot. Until you're storing your
        # own IV history, this scales the average current IV across the
        # chosen expiration into a 0-100 pseudo-percentile. Swap this out for
        # a real percentile-rank calculation once you have that history —
        # it directly affects Risk Governor and strategy-choice thresholds.
        ivs = [p["iv"] for p in same_exp if p["iv"] is not None]
        avg_iv = sum(ivs) / len(ivs) if ivs else 0.5
        iv_percentile_approx = max(0, min(100, round(avg_iv * 100)))

        underlying_price = self._get_underlying_price(ticker, fallback=strikes[len(strikes) // 2])

        # Pick 5 strikes centered near the underlying price, matching the
        # shape the mock chain and strategy builders expect.
        mid_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - underlying_price))
        lo = max(0, mid_idx - 2)
        hi = min(len(strikes), lo + 5)
        lo = max(0, hi - 5)
        picked_strikes = strikes[lo:hi]

        return {
            "ticker": ticker,
            "underlying_price": underlying_price,
            "iv_percentile": iv_percentile_approx,
            "expiration": chosen_expiration,
            "far_expiration": far_expiration,
            "strikes": picked_strikes,
        }

    @staticmethod
    def _parse_chain_symbols(chain: dict) -> list[dict]:
        """
        Parses OCC-format contract symbols returned as keys of the chain dict:
        ROOT(variable length) + YYMMDD(6) + C/P(1) + STRIKE*1000 zero-padded(8).
        Skips anything that doesn't match — a partial parse is fine here since
        we only need enough contracts to pick strikes/expirations from.
        """
        parsed = []
        for symbol, snapshot in chain.items():
            try:
                date_part = symbol[-15:-9]
                strike_part = symbol[-8:]
                expiration = f"20{date_part[0:2]}-{date_part[2:4]}-{date_part[4:6]}"
                strike = int(strike_part) / 1000.0
                iv = getattr(snapshot, "implied_volatility", None)
                parsed.append({"symbol": symbol, "expiration": expiration, "strike": strike, "iv": iv})
            except (ValueError, IndexError):
                continue
        return parsed

    def _get_underlying_price(self, ticker: str, fallback: float) -> float:
        """Best-effort latest trade price; falls back to a strike-derived estimate on any failure."""
        try:
            from alpaca.data.historical.stock import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest

            if self._stock_data_client is None:
                self._stock_data_client = StockHistoricalDataClient(
                    settings.ALPACA_API_KEY, settings.ALPACA_SECRET_KEY
                )
            trades = self._stock_data_client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=ticker)
            )
            return float(trades[ticker].price)
        except Exception:
            return fallback

    # ------------------------------------------------------------------ orders
    def submit_mleg_order(self, ticker: str, legs: List[OptionLeg], client_order_id: str,
                           net_limit_price: float) -> dict:
        """
        Submits a multi-leg options order. In mock mode, simulates an
        immediate fill and a randomized-but-bounded P&L outcome so the full
        Autopsy -> Talent loop can be demoed without live keys.

        Uses a LIMIT order, not a market order. Alpaca rejects options
        MARKET orders outside regular trading hours (error 42210000:
        "options market orders are only allowed during market hours") —
        which meant every trade submitted outside 9:30am-4:00pm ET was
        failing outright, regardless of how good the proposal was. A limit
        order at the strategy's own computed net price is accepted at any
        time (it simply rests until the market can fill it), and — per
        Alpaca's documented mleg convention — a positive `net_limit_price`
        means a net debit (you're paying) and a negative one means a net
        credit (you're receiving); `net_limit_price` must be passed in
        using that sign convention by the caller.
        """
        if self.mock or self._sdk is None:
            filled = True
            broker_order_id = _rand_id("MOCKORD")
            return {"filled": filled, "broker_order_id": broker_order_id, "mock": True}

        # LIVE mode: build a real Alpaca mleg order request.
        from alpaca.trading.requests import OptionLegRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce

        alpaca_legs = [
            OptionLegRequest(
                symbol=self._occ_symbol(ticker, leg),
                side=OrderSide.BUY if leg.side == "buy" else OrderSide.SELL,
                ratio_qty=leg.ratio,
            )
            for leg in legs
        ]
        order_req = LimitOrderRequest(
            qty=1,
            order_class=OrderClass.MLEG,
            time_in_force=TimeInForce.DAY,
            legs=alpaca_legs,
            limit_price=round(net_limit_price, 2),
            client_order_id=client_order_id,
        )
        try:
            result = self._sdk.submit_order(order_req)
        except Exception as e:
            # A rejected order (e.g. insufficient options level, closed
            # market, bad symbol) must surface as a failed trade, not crash
            # the whole run — the firm should record this as a real
            # execution failure, not silently pretend nothing happened.
            return {"filled": False, "broker_order_id": None, "mock": False, "error": str(e)}

        # A limit order accepted by Alpaca may fill near-instantly in paper
        # trading, or may rest until the market opens/a counterparty
        # appears — "accepted" is not "filled". Check status from the
        # response we already have rather than assuming.
        status = str(getattr(result, "status", "")).lower()
        filled = "filled" in status or status == "orderstatus.filled"
        return {"filled": filled, "broker_order_id": str(result.id), "mock": False, "status": status}

    @staticmethod
    def _occ_symbol(ticker: str, leg: OptionLeg) -> str:
        # OCC symbol construction left as an extension point for LIVE mode.
        exp = leg.expiration.replace("-", "")[2:]
        cp = "C" if leg.option_type == "call" else "P"
        strike_int = int(round(leg.strike * 1000))
        return f"{ticker}{exp}{cp}{strike_int:08d}"

    def close_mleg_position(self, ticker: str, legs: List[OptionLeg], client_order_id: str,
                             net_limit_price: float) -> dict:
        """
        Submits the REVERSE of an open multi-leg position (every leg's side
        flipped) to close it out. This is what actually turns an opened
        live-paper position into a REALIZED trade — previously the codebase
        only ever opened positions and read unrealized P&L off them, so a
        live trade's true win/loss was never booked and the Autopsy ->
        Talent loop never saw a real number for it.

        Uses a LIMIT order for the same reason as submit_mleg_order — a
        market order is rejected outside regular trading hours. Since this
        codebase doesn't track a live bid/ask to close at, the caller
        should pass a deliberately permissive `net_limit_price` (using
        Alpaca's mleg sign convention: positive=debit, negative=credit) —
        the realized P&L booked by reconciliation.py comes from the
        broker's own mark-to-market snapshot taken just before this call,
        not from this limit price, so a permissive price here only affects
        whether the close fills promptly, not the P&L recorded.

        In mock mode this mirrors submit_mleg_order's simulated-fill shape.
        """
        if self.mock or self._sdk is None:
            return {"filled": True, "broker_order_id": _rand_id("MOCKCLOSE"), "mock": True}

        from alpaca.trading.requests import OptionLegRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce

        reversed_legs = [
            OptionLegRequest(
                symbol=self._occ_symbol(ticker, leg),
                side=OrderSide.SELL if leg.side == "buy" else OrderSide.BUY,
                ratio_qty=leg.ratio,
            )
            for leg in legs
        ]
        order_req = LimitOrderRequest(
            qty=1,
            order_class=OrderClass.MLEG,
            time_in_force=TimeInForce.DAY,
            legs=reversed_legs,
            limit_price=round(net_limit_price, 2),
            client_order_id=client_order_id,
        )
        try:
            result = self._sdk.submit_order(order_req)
        except Exception as e:
            return {"filled": False, "broker_order_id": None, "mock": False, "error": str(e)}

        status = str(getattr(result, "status", "")).lower()
        filled = "filled" in status or status == "orderstatus.filled"
        return {"filled": filled, "broker_order_id": str(result.id), "mock": False, "status": status}

    # -------------------------------------------------------- real P&L / audit
    def get_order_status(self, broker_order_id: str) -> Optional[dict]:
        """
        LIVE mode only: the actual fill state of a submitted order, straight
        from Alpaca — status, filled quantity, and average fill price. This
        is what lets a trade be honestly labeled "filled" vs "pending"
        rather than assumed filled the instant it's submitted.
        """
        if self.mock or self._sdk is None or not broker_order_id:
            return None
        try:
            order = self._sdk.get_order_by_id(broker_order_id)
            return {
                "status": str(order.status),
                "filled_qty": float(order.filled_qty or 0),
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            }
        except Exception as e:
            return {"status": "unknown", "error": str(e)}

    def get_unrealized_pnl(self, ticker: str) -> Optional[float]:
        """
        LIVE mode only: sums unrealized P&L across every open OPTION
        position on this underlying, read directly from Alpaca's positions
        endpoint. Returns None (not 0.0) when no matching position is found
        yet — e.g. the fill hasn't settled — so callers can distinguish
        "genuinely flat" from "we don't know yet" instead of a fabricated
        number.

        Note on what this number actually means: right after a trade opens,
        unrealized P&L is normally close to zero (minus the bid/ask spread
        crossed on entry) — that's the honest current mark-to-market, not a
        simulated outcome. It only reflects the trade's real win/loss once
        enough time and price movement has passed, which a short demo
        session won't produce for options. This is why MOCK mode still uses
        `simulate_close()` — there is no way to fabricate realized options
        P&L within seconds without lying about the market.
        """
        if self.mock or self._sdk is None:
            return None
        try:
            positions = self._sdk.get_all_positions()
        except Exception:
            return None
        total = 0.0
        found = False
        for p in positions:
            symbol = getattr(p, "symbol", "") or ""
            if symbol.startswith(ticker):
                total += float(getattr(p, "unrealized_pl", 0) or 0)
                found = True
        return total if found else None

    def list_positions(self) -> list[dict]:
        """LIVE mode: every open position on the paper account, for the audit screen."""
        if self.mock or self._sdk is None:
            return []
        try:
            positions = self._sdk.get_all_positions()
        except Exception:
            return []
        return [
            {
                "symbol": getattr(p, "symbol", None),
                "qty": float(getattr(p, "qty", 0) or 0),
                "avg_entry_price": float(getattr(p, "avg_entry_price", 0) or 0),
                "market_value": float(getattr(p, "market_value", 0) or 0),
                "unrealized_pl": float(getattr(p, "unrealized_pl", 0) or 0),
            }
            for p in positions
        ]

    def list_recent_orders(self, limit: int = 25) -> list[dict]:
        """LIVE mode: the broker's own order ledger, for the audit screen —
        the ground truth to reconcile against the firm's internal Trade table."""
        if self.mock or self._sdk is None:
            return []
        try:
            from alpaca.trading.requests import GetOrdersRequest
            req = GetOrdersRequest(limit=limit)
            orders = self._sdk.get_orders(filter=req)
        except Exception:
            return []
        return [
            {
                "id": str(o.id),
                "client_order_id": getattr(o, "client_order_id", None),
                "symbol": getattr(o, "symbol", None),
                "status": str(o.status),
                "side": str(getattr(o, "side", "")),
                "order_class": str(getattr(o, "order_class", "")),
                "filled_qty": float(o.filled_qty or 0),
                "filled_avg_price": float(o.filled_avg_price) if getattr(o, "filled_avg_price", None) else None,
                "submitted_at": o.submitted_at.isoformat() if getattr(o, "submitted_at", None) else None,
            }
            for o in orders
        ]


alpaca_client = AlpacaClient()
