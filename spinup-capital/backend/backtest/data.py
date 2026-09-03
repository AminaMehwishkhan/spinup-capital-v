"""
Historical daily-bar data for the backtest engine.

LIVE mode: real daily bars from Alpaca's StockHistoricalDataClient.
MOCK mode: a deterministic (seeded), clearly-labeled synthetic price series
— never random per-call, so a backtest is reproducible — built as a simple
geometric random walk. This is NOT real market data and the engine's
response says so explicitly; it exists purely so the backtest module is
exercisable and demoable without live keys.
"""
from __future__ import annotations
import random
from datetime import date, timedelta
from typing import List, TypedDict
from backend.config import settings


class Bar(TypedDict):
    date: str
    close: float


def fetch_daily_bars(ticker: str, lookback_days: int) -> List[Bar]:
    if settings.ALPACA_MOCK:
        return _synthetic_bars(ticker, lookback_days)
    return _live_bars(ticker, lookback_days)


def _synthetic_bars(ticker: str, lookback_days: int) -> List[Bar]:
    """Deterministic seeded geometric random walk — same ticker + same
    lookback always reproduces the same series, so backtest results are
    stable and comparable run-to-run in MOCK mode."""
    rnd = random.Random(hash(ticker) & 0xFFFFFFFF)
    price = 100.0 + (hash(ticker) % 400)
    daily_vol = 0.018  # ~28% annualized, a plausible single-name vol
    drift = 0.0002
    bars: List[Bar] = []
    start = date.today() - timedelta(days=lookback_days)
    for i in range(lookback_days):
        price *= (1 + drift + rnd.gauss(0, daily_vol))
        price = max(price, 1.0)
        bars.append({"date": (start + timedelta(days=i)).isoformat(), "close": round(price, 2)})
    return bars


def _live_bars(ticker: str, lookback_days: int) -> List[Bar]:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(settings.ALPACA_API_KEY, settings.ALPACA_SECRET_KEY)
    start = date.today() - timedelta(days=lookback_days)
    try:
        resp = client.get_stock_bars(
            StockBarsRequest(symbol_or_symbols=ticker, timeframe=TimeFrame.Day, start=start)
        )
    except Exception as e:
        raise RuntimeError(
            f"Alpaca historical bars request failed for {ticker}: {e}. Check API keys and that "
            f"{ticker} is a valid, actively-traded symbol."
        ) from e

    bars_for_ticker = resp[ticker] if hasattr(resp, "__getitem__") else resp.data.get(ticker, [])
    if not bars_for_ticker:
        raise RuntimeError(f"Alpaca returned no historical bars for {ticker} over the last {lookback_days} days.")

    return [
        {"date": b.timestamp.date().isoformat() if hasattr(b.timestamp, "date") else str(b.timestamp)[:10],
         "close": float(b.close)}
        for b in bars_for_ticker
    ]
