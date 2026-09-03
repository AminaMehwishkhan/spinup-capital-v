"""
Central configuration. Everything is env-driven so the same codebase runs in:
  - MOCK mode (no Alpaca keys, no LLM keys)  -> fully offline demo
  - LIVE-PAPER mode (real Alpaca paper keys) -> real paper P&L
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env by its ABSOLUTE path (project root, two levels up from this
# file), not by relying on the process's current working directory.
# `load_dotenv()` with no argument only searches upward from wherever the
# process happened to be launched — if uvicorn is started from any
# directory other than the exact project root, this silently finds
# nothing, ALPACA_API_KEY/SECRET_KEY come back empty, and the app falls
# back to MOCK mode with no error at all. That's exactly what happened
# here: LIVE mode worked from one terminal/cwd and silently reverted to
# MOCK from another.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings:
    # Alpaca
    ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "").strip()
    ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "").strip()
    ALPACA_BASE_URL: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    # 'indicative' is free and available on every account. 'opra' requires an
    # OPRA options data subscription on your Alpaca account — set this to
    # 'opra' only if you actually have that entitlement, or get_option_chain
    # calls will fail.
    ALPACA_OPTIONS_FEED: str = os.getenv("ALPACA_OPTIONS_FEED", "indicative").strip().lower()

    @property
    def ALPACA_MOCK(self) -> bool:
        return not (self.ALPACA_API_KEY and self.ALPACA_SECRET_KEY)

    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "heuristic").lower()
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()

    # Firm
    STARTING_TREASURY: float = float(os.getenv("STARTING_TREASURY", "100000"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./spinup.db")

    # Risk defaults (hard, deterministic — never overridden by an LLM)
    MAX_TRADE_RISK_PCT_OF_AGENT_CAPITAL: float = 0.10   # a single trade can risk at most 10% of the agent's capital
    MAX_PORTFOLIO_EXPOSURE_PCT: float = 0.60            # agents' combined deployed capital vs treasury
    MIN_DAYS_TO_EARNINGS_FOR_LONG_PREMIUM: int = 2      # block long-premium trades inside earnings window
    REQUIRE_DEFINED_RISK: bool = True                   # no naked options, ever

    # Agent Arena — every new specialist must clear this gauntlet of synthetic
    # scenarios BEFORE it receives real capital. See agents/arena.py.
    ARENA_TRIALS: int = int(os.getenv("ARENA_TRIALS", "6"))
    ARENA_MIN_WIN_RATE: float = float(os.getenv("ARENA_MIN_WIN_RATE", "0.50"))
    ARENA_MIN_RISK_PASS_RATE: float = float(os.getenv("ARENA_MIN_RISK_PASS_RATE", "0.60"))


settings = Settings()
