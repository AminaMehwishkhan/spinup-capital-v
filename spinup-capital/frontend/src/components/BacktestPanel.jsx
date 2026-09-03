import React, { useMemo, useState } from "react";
import { runBacktest } from "../api.js";

function EquityLine({ curve }) {
  const width = 560;
  const height = 160;
  const pad = 8;
  const points = useMemo(() => {
    if (!curve || curve.length < 2) return "";
    const min = Math.min(...curve);
    const max = Math.max(...curve);
    const range = max - min || 1;
    return curve
      .map((v, i) => {
        const x = pad + (i / (curve.length - 1)) * (width - pad * 2);
        const y = height - pad - ((v - min) / range) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [curve]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="equity-chart" preserveAspectRatio="none">
      <line x1={pad} y1={height / 2} x2={width - pad} y2={height / 2} stroke="var(--hairline)" strokeWidth="1" strokeDasharray="3 4" />
      <polyline points={points} fill="none" stroke="var(--accent-brand)" strokeWidth="2" />
    </svg>
  );
}

const SPECIALIST_OPTIONS = ["earnings", "macro", "volatility", "hedging"];

export default function BacktestPanel() {
  const [ticker, setTicker] = useState("AAPL");
  const [specialistType, setSpecialistType] = useState("earnings");
  const [lookback, setLookback] = useState(180);
  const [holding, setHolding] = useState(21);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    const r = await runBacktest({
      ticker, specialist_type: specialistType, lookback_days: lookback,
      holding_period_days: holding, capital: 10000,
    });
    setResult(r);
    setRunning(false);
  };

  return (
    <div>
      <div className="perm-console" style={{ marginBottom: 20 }}>
        <div className="perm-demo" style={{ marginTop: 0, paddingTop: 0, borderTop: "none", flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            Ticker
            <input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())}
                   style={{ background: "var(--panel-raised)", border: "1px solid var(--hairline)", borderRadius: 6, padding: "7px 10px", color: "var(--text-primary)", width: 90, fontFamily: "var(--font-mono)" }} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            Specialist
            <select value={specialistType} onChange={(e) => setSpecialistType(e.target.value)}
                    style={{ background: "var(--panel-raised)", border: "1px solid var(--hairline)", borderRadius: 6, padding: "7px 10px", color: "var(--text-primary)" }}>
              {SPECIALIST_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            Lookback (days)
            <input type="number" value={lookback} onChange={(e) => setLookback(Number(e.target.value))}
                   style={{ background: "var(--panel-raised)", border: "1px solid var(--hairline)", borderRadius: 6, padding: "7px 10px", color: "var(--text-primary)", width: 90 }} />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            Holding period (days)
            <input type="number" value={holding} onChange={(e) => setHolding(Number(e.target.value))}
                   style={{ background: "var(--panel-raised)", border: "1px solid var(--hairline)", borderRadius: 6, padding: "7px 10px", color: "var(--text-primary)", width: 90 }} />
          </label>
          <button className="run-btn" onClick={handleRun} disabled={running}>
            {running ? "Running…" : "Run backtest"}
          </button>
        </div>
      </div>

      {!result ? (
        <div className="section-sub">No backtest run yet.</div>
      ) : result.error ? (
        <div className="trade-reason">{result.error}</div>
      ) : (
        <div className="experiment-body">
          <div className="offline-banner" style={{ marginBottom: 16 }}>{result.data_source}</div>
          <EquityLine curve={result.equity_curve} />
          <table className="experiment-table">
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>
              <tr><td>Total return</td><td className={result.total_return_pct >= 0 ? "gain" : "loss"}>{(result.total_return_pct * 100).toFixed(1)}%</td></tr>
              <tr><td>Win rate</td><td>{Math.round(result.win_rate * 100)}%</td></tr>
              <tr><td>Max drawdown</td><td>{(result.max_drawdown_pct * 100).toFixed(1)}%</td></tr>
              <tr><td>Trades</td><td>{result.trades}</td></tr>
              <tr><td>Final equity</td><td>${result.final_equity.toLocaleString()}</td></tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
