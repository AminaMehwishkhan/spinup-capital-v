const BASE = "http://localhost:8000";

const MOCK = {
  summary: {
    treasury: 60000,
    deployed_capital: 40000,
    total_firm_value: 100000,
    agents_hired: 5,
    agents_active: 4,
    agents_fired: 1,
    trades_executed: 6,
    trades_blocked: 2,
  },
  agents: [
    { agent_id: "EARNINGS-NVDA-329", specialist_type: "earnings", status: "PROMOTED", capital: 15000, total_pnl: 1089, trade_count: 3, wins: 3, losses: 0, max_drawdown: 0, risk_violations: 0 },
    { agent_id: "VOLATILITY-TSLA-478", specialist_type: "volatility", status: "PROBATION", capital: 10000, total_pnl: 204, trade_count: 1, wins: 1, losses: 0, max_drawdown: 0, risk_violations: 0 },
    { agent_id: "EARNINGS-AAPL-487", specialist_type: "earnings", status: "KEEP", capital: 10000, total_pnl: 358, trade_count: 1, wins: 1, losses: 0, max_drawdown: 0, risk_violations: 0 },
    { agent_id: "MACRO-SPY-341", specialist_type: "macro", status: "PROBATION", capital: 5000, total_pnl: -320, trade_count: 2, wins: 0, losses: 2, max_drawdown: 0.06, risk_violations: 1 },
    { agent_id: "MACRO-CPI-102", specialist_type: "macro", status: "FIRED", capital: 0, total_pnl: -1100, trade_count: 4, wins: 1, losses: 3, max_drawdown: 0.11, risk_violations: 2 },
  ],
  trades: [
    { trade_id: "TRD-A1B2C3", agent_id: "EARNINGS-NVDA-329", ticker: "NVDA", strategy: "vertical_call_spread", pnl: 213, filled: true, risk_approved: true, thesis: "NVDA shows elevated IV ahead of earnings; a defined-risk vertical captures the expected move." },
    { trade_id: "TRD-D4E5F6", agent_id: "MACRO-SPY-341", ticker: "SPY", strategy: "vertical_call_spread", pnl: 0, filled: false, risk_approved: false, risk_reasons: "Max loss $1,467 exceeds this agent's per-trade risk limit of $1,000.", thesis: "SPY CPI volatility play." },
  ],
  lessons: [
    { id: 1, specialist_type: "earnings", ticker: "AAPL", outcome: "loss", iv_percentile: 91, rule: "Avoid long-premium structures when IV percentile > 80 close to a binary event.", lesson: "The calendar on AAPL closed -$610; the move exceeded the structure's break-evens faster than modeled." },
    { id: 2, specialist_type: "macro", ticker: "SPY", outcome: "win", iv_percentile: 78, rule: "Favor vertical call spread structures near 78th-percentile IV for this ticker class.", lesson: "The vertical call spread on SPY closed +$340, validating the thesis at 78th-percentile IV." },
  ],
  arenaLog: [
    { id: 1, candidate_id: "EARNINGS-NVDA-322", specialist_type: "earnings", ticker: "NVDA", trials_run: 6, win_rate: 0.67, avg_pnl: 82, risk_pass_rate: 1.0, passed: true, reasoning: "6/6 trial proposals cleared the Risk Governor; win rate 67%, avg simulated PnL $82. Cleared for hire with real capital." },
    { id: 2, candidate_id: "MACRO-SPY-970", specialist_type: "macro", ticker: "SPY", trials_run: 6, win_rate: 0.2, avg_pnl: -180, risk_pass_rate: 1.0, passed: false, reasoning: "6/6 trial proposals cleared the Risk Governor; win rate 20%, avg simulated PnL -$180. Did not meet the bar — hire declined." },
  ],
};

async function safeGet(path, fallback) {
  try {
    const res = await fetch(`${BASE}${path}`, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return fallback;
  }
}

export async function fetchSummary() {
  return safeGet("/firm/summary", MOCK.summary);
}

export async function fetchAgents() {
  return safeGet("/agents", MOCK.agents);
}

export async function fetchTrades() {
  return safeGet("/trades", MOCK.trades);
}

export async function fetchLessons() {
  return safeGet("/lessons", MOCK.lessons);
}

export async function fetchArenaLog() {
  return safeGet("/arena-log", MOCK.arenaLog);
}

const MOCK_PERMISSIONS = {
  permissions: ["market_data", "options_data", "trading:propose", "trading:execute", "account:read", "account:write"],
  roles: [
    { role: "managing_partner", granted: ["market_data", "options_data", "account:read"] },
    { role: "specialist", granted: ["market_data", "options_data", "trading:propose"] },
    { role: "bull_bear", granted: ["market_data", "options_data"] },
    { role: "risk_governor", granted: ["market_data", "options_data", "account:read"] },
    { role: "execution_gateway", granted: ["market_data", "options_data", "trading:execute", "account:read", "account:write"] },
    { role: "talent_agent", granted: ["account:read"] },
  ],
};

export async function fetchPermissionMatrix() {
  return safeGet("/permissions/matrix", MOCK_PERMISSIONS);
}

const MOCK_RETIREMENTS = [
  {
    id: 1, agent_id: "MACRO-CPI-102", specialist_type: "macro",
    lesson: "MACRO-CPI-102 was retired after 4 trades (25% win rate, $-1,100 total P&L, 2 risk violation(s)).",
    rule: "Future macro specialists: prior hire terminated at 25% win rate with 2 risk violation(s) and 11% max drawdown — tighten sizing and re-verify thesis quality before repeating this specialist type's recent strategy mix.",
    created_at: new Date().toISOString(),
  },
];

export async function fetchRetirements() {
  return safeGet("/retirements", MOCK_RETIREMENTS);
}

export async function attemptUnauthorizedTrade() {
  try {
    const res = await fetch(`${BASE}/demo/unauthorized-trade`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return {
      blocked: true, role: "bull_bear", attempted_permission: "trading:execute",
      held_permissions: ["market_data", "options_data"],
      reason: "'bull_bear' does not hold the 'trading:execute' permission — request refused. Held permissions: ['market_data', 'options_data']",
    };
  }
}

const MOCK_EXPERIMENT = {
  static: {
    label: "Static Desk", return_pct: 0.024, sharpe_proxy: 0.73, max_drawdown_pct: 0.016,
    win_rate: 0.55, trades_executed: 38, trades_blocked: 2, agents_used: 4, agents_fired: 0,
    final_equity: 102378, equity_curve: [100000, 100400, 101100, 100800, 101600, 102378],
  },
  spinup: {
    label: "Spinup Capital", return_pct: 0.036, sharpe_proxy: 0.65, max_drawdown_pct: 0.032,
    win_rate: 0.55, trades_executed: 35, trades_blocked: 5, agents_used: 6, agents_fired: 1,
    arena_declines: 3, final_equity: 103596, equity_curve: [100000, 99800, 100600, 101900, 102700, 103596],
  },
};

export async function runExperiment(events = 40) {
  try {
    const res = await fetch(`${BASE}/experiment/run?events=${events}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return MOCK_EXPERIMENT;
  }
}

export async function runDemo(numEvents = 4) {
  try {
    const res = await fetch(`${BASE}/demo/run?num_events=${numEvents}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return { status: "offline", note: "Backend not reachable — showing static demo data." };
  }
}

const MOCK_MONTE_CARLO = {
  n_runs: 25, n_events_per_run: 60, mean_edge_pct: 0.0506, std_edge_pct: 0.0285,
  edge_95ci_low_pct: 0.0395, edge_95ci_high_pct: 0.0618, spinup_win_rate_across_runs: 0.96,
  mean_static_return_pct: -0.0302, mean_spinup_return_pct: 0.0205,
  mean_static_sharpe: -0.788, mean_spinup_sharpe: 0.516, mean_agents_fired_per_run: 0,
  all_edges_pct: [0.04, 0.06, 0.05, 0.03, 0.07, 0.045, 0.02, 0.08, 0.055, 0.06],
  note: "Normal-approximation 95% CI on the mean edge across Monte Carlo runs — a directional confidence estimate, not a formally validated hypothesis test.",
};

export async function runMonteCarlo(nEvents = 60, nRuns = 25) {
  try {
    const res = await fetch(`${BASE}/experiment/monte-carlo?n_events=${nEvents}&n_runs=${nRuns}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return MOCK_MONTE_CARLO;
  }
}

const MOCK_BACKTEST = {
  ticker: "AAPL", specialist_type: "earnings", data_source: "synthetic (MOCK mode — not real market data; add Alpaca keys for a real backtest)",
  lookback_days: 180, holding_period_days: 21, starting_capital: 10000, final_equity: 11340,
  total_return_pct: 0.134, win_rate: 0.625, max_drawdown_pct: 0.081, trades: 8,
  equity_curve: [10000, 9800, 10200, 10650, 10400, 10900, 11100, 10950, 11340],
  trade_log: [],
};

export async function runBacktest(params) {
  const q = new URLSearchParams(params).toString();
  try {
    const res = await fetch(`${BASE}/backtest/run?${q}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return MOCK_BACKTEST;
  }
}

const MOCK_LEARNING_CURVE = {
  by_specialist_type: {
    earnings: { no_memory: { trades: 5, win_rate: 0.4, avg_pnl: -85 }, with_memory: { trades: 9, win_rate: 0.67, avg_pnl: 245 } },
    macro: { no_memory: { trades: 4, win_rate: 0.5, avg_pnl: 30 }, with_memory: { trades: 6, win_rate: 0.6, avg_pnl: 120 } },
  },
  note: "Directional only on small sample sizes — run more market cycles for a sturdier signal.",
};

export async function fetchLearningCurve() {
  return safeGet("/learning-curve", MOCK_LEARNING_CURVE);
}

const MOCK_ALPACA_ACCOUNT = { cash: 100000, buying_power: 100000, mock: true };

export async function fetchAlpacaAccount() {
  return safeGet("/alpaca/account", MOCK_ALPACA_ACCOUNT);
}

export async function fetchAlpacaPositions() {
  return safeGet("/alpaca/positions", []);
}

export async function fetchAlpacaOrders() {
  return safeGet("/alpaca/orders", []);
}

export async function reconcileAlpacaTrades() {
  try {
    const res = await fetch(`${BASE}/alpaca/reconcile`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    return { results: [{ status: "skipped", reason: "backend not reachable" }] };
  }
}

export const IS_MOCK_CAPABLE = true;
