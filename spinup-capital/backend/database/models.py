from __future__ import annotations
import datetime as dt
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def now():
    return dt.datetime.utcnow()


class Agent(Base):
    __tablename__ = "agents"
    agent_id = Column(String, primary_key=True)
    specialist_type = Column(String, nullable=False)
    mandate = Column(Text)
    status = Column(String, default="PROBATION")
    capital = Column(Float, default=0)
    total_pnl = Column(Float, default=0)
    trade_count = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    max_drawdown = Column(Float, default=0)
    risk_violations = Column(Integer, default=0)
    permissions = Column(Text, default="market_data,options_data,trading:propose")
    created_at = Column(DateTime, default=now)
    fired_at = Column(DateTime, nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    trade_id = Column(String, primary_key=True)
    agent_id = Column(String, ForeignKey("agents.agent_id"))
    ticker = Column(String)
    strategy = Column(String)
    legs_json = Column(Text)
    max_loss = Column(Float)
    max_profit = Column(Float)
    thesis = Column(Text)
    pnl = Column(Float, default=0)
    pnl_source = Column(String, default="simulated")  # "simulated" | "alpaca_unrealized" | "pending"
    filled = Column(Boolean, default=False)
    broker_order_id = Column(String, nullable=True)
    close_broker_order_id = Column(String, nullable=True)
    risk_approved = Column(Boolean, default=False)
    risk_reasons = Column(Text)
    submission_error = Column(Text, nullable=True)
    lessons_used_count = Column(Integer, default=0)
    iv_percentile_at_entry = Column(Float, nullable=True)
    event_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)
    closed_at = Column(DateTime, nullable=True)


class Debate(Base):
    __tablename__ = "debates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(String, ForeignKey("trades.trade_id"))
    bull_argument = Column(Text)
    bear_argument = Column(Text)
    bear_failure_condition = Column(Text)
    created_at = Column(DateTime, default=now)


class CapitalAllocation(Base):
    __tablename__ = "capital_allocations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, ForeignKey("agents.agent_id"))
    previous_capital = Column(Float)
    new_capital = Column(Float)
    reason = Column(Text)
    talent_score = Column(Float)
    timestamp = Column(DateTime, default=now)


class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, ForeignKey("agents.agent_id"))
    specialist_type = Column(String, index=True)
    ticker = Column(String, index=True)
    outcome = Column(String)              # "win" | "loss"
    iv_percentile = Column(Float, nullable=True)
    days_to_event = Column(Integer, nullable=True)
    market_condition = Column(Text)
    failure_reason = Column(Text, nullable=True)
    lesson = Column(Text)                 # human-readable narrative
    rule = Column(Text)                   # short, structured, machine-checkable rule
    confidence = Column(Float, default=0.5)
    is_retirement = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class ArenaReview(Base):
    __tablename__ = "arena_reviews"
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(String)          # the agent_id that would have been used, whether hired or not
    specialist_type = Column(String)
    ticker = Column(String)
    trials_run = Column(Integer)
    win_rate = Column(Float)
    avg_pnl = Column(Float)
    risk_pass_rate = Column(Float)
    passed = Column(Boolean)
    reasoning = Column(Text)
    created_at = Column(DateTime, default=now)


class Treasury(Base):
    __tablename__ = "treasury"
    id = Column(Integer, primary_key=True, autoincrement=True)
    balance = Column(Float)
    timestamp = Column(DateTime, default=now)
    note = Column(Text)
