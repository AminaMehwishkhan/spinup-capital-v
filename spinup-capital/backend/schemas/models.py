from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    PROBATION = "PROBATION"
    ACTIVE = "ACTIVE"
    PROMOTED = "PROMOTED"
    FIRED = "FIRED"


class SpecialistType(str, Enum):
    EARNINGS = "earnings"
    MACRO = "macro"
    VOLATILITY = "volatility"
    HEDGING = "hedging"


class EventType(str, Enum):
    EARNINGS = "earnings"
    MACRO = "macro"
    VOLATILITY_ANOMALY = "volatility_anomaly"
    DRAWDOWN = "drawdown"


class MarketEvent(BaseModel):
    event_id: str
    event_type: EventType
    ticker: str
    description: str
    days_to_event: Optional[int] = None   # e.g. days to earnings
    iv_percentile: Optional[float] = None


class AgentSpec(BaseModel):
    """Output of the Agent Factory — the 'employment contract'."""
    agent_id: str
    specialist_type: SpecialistType
    mandate: str
    allowed_symbols: List[str]
    allowed_strategies: List[str]
    capital: float
    max_trade_risk: float
    permissions: List[str]
    status: AgentStatus = AgentStatus.PROBATION


class OptionLeg(BaseModel):
    side: str          # "buy" | "sell"
    option_type: str   # "call" | "put"
    strike: float
    expiration: str    # ISO date
    ratio: int = 1


class TradeProposal(BaseModel):
    agent_id: str
    ticker: str
    strategy: str
    legs: List[OptionLeg]
    max_loss: float
    max_profit: float
    thesis: str
    confidence: float = Field(ge=0, le=1)


class RiskCheckResult(BaseModel):
    approved: bool
    reasons: List[str]
    checked_rules: List[str]


class DebateResult(BaseModel):
    bull_argument: str
    bear_argument: str
    bear_failure_condition: str


class TradeResult(BaseModel):
    trade_id: str
    agent_id: str
    ticker: str
    strategy: str
    pnl: float
    max_loss: float
    filled: bool
    broker_order_id: Optional[str] = None
    pnl_source: str = "simulated"   # "simulated" | "alpaca_unrealized" | "pending"
    order_status: Optional[str] = None
    error: Optional[str] = None


class TalentDecision(BaseModel):
    agent_id: str
    decision: str  # PROMOTE | KEEP | PROBATION | FIRE
    score: float
    previous_capital: float
    new_capital: float
    reasoning: str


class ArenaTrialResult(BaseModel):
    scenario_iv: float
    strategy: str
    risk_approved: bool
    pnl: float


class ArenaResult(BaseModel):
    trials: List[ArenaTrialResult]
    win_rate: float
    avg_pnl: float
    risk_pass_rate: float
    passed: bool
    reasoning: str
