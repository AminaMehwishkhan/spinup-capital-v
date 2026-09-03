import React, { useMemo, useState } from "react";
import { runExperiment, runMonteCarlo } from "../api.js";

function EdgeHistogram({ edges }) {
  const width = 560;
  const height = 120;
  const pad = 8;
  const bars = useMemo(() => {
    if (!edges || edges.length === 0) return [];
    const min = Math.min(...edges, 0);
    const max = Math.max(...edges, 0);
    const range = max - min || 1;
    const barW = (width - pad * 2) / edges.length;
    return edges.map((e, i) => {
      const x = pad + i * barW;
      const h = (Math.abs(e) / range) * (height - pad * 2);
      const zeroY = height - pad - ((0 - min) / range) * (height - pad * 2);
      const y = e >= 0 ? zeroY - h : zeroY;
      return { x, y, h: Math.max(h, 1), w: barW * 0.7, gain: e >= 0 };
    });
  }, [edges]);

  if (bars.length === 0) return null;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="equity-chart" preserveAspectRatio="none">
      {bars.map((b, i) => (
        <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h}
              fill={b.gain ? "var(--accent-gain)" : "var(--accent-loss)"} opacity="0.85" />
      ))}
    </svg>
  );
}

function MonteCarloPanel() {
  const [mc, setMc] = useState(null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    const r = await runMonteCarlo(60, 25);
    setMc(r);
    setRunning(false);
  };

  return (
    <div style={{ marginTop: 32 }}>
      <div className="experiment-head">
        <div className="section-sub">
          A single run could just be luck. This repeats the identical comparison 25 times with
          independently-seeded market outcomes and reports the distribution of Spinup's edge over
          Static — not one headline number.
        </div>
        <button className="run-btn secondary" onClick={handleRun} disabled={running}>
          {running ? "Running 25 trials…" : "Run Monte Carlo (25×)"}
        </button>
      </div>

      {!mc ? (
        <div className="section-sub" style={{ marginTop: 12 }}>No Monte Carlo run yet.</div>
      ) : (
        <div className="experiment-body">
          <EdgeHistogram edges={mc.all_edges_pct} />
          <div className="experiment-legend">
            <span><i className="dot gain" /> Spinup ahead this run</span>
            <span><i className="dot brand" style={{ background: "var(--accent-loss)" }} /> Static ahead this run</span>
          </div>

          <table className="experiment-table">
            <thead><tr><th>Metric</th><th>Value</th></tr></thead>
            <tbody>
              <tr><td>Mean edge (Spinup − Static)</td><td className={mc.mean_edge_pct >= 0 ? "gain" : "loss"}>{(mc.mean_edge_pct * 100).toFixed(2)}%</td></tr>
              <tr><td>95% CI on mean edge</td><td>[{(mc.edge_95ci_low_pct * 100).toFixed(2)}%, {(mc.edge_95ci_high_pct * 100).toFixed(2)}%]</td></tr>
              <tr><td>Spinup win rate across runs</td><td>{Math.round(mc.spinup_win_rate_across_runs * 100)}%</td></tr>
              <tr><td>Mean Sharpe — Static / Spinup</td><td>{mc.mean_static_sharpe.toFixed(2)} / {mc.mean_spinup_sharpe.toFixed(2)}</td></tr>
              <tr><td>Runs</td><td>{mc.n_runs} × {mc.n_events_per_run} events</td></tr>
            </tbody>
          </table>
          <div className="section-sub" style={{ marginTop: 12 }}>{mc.note}</div>
        </div>
      )}
    </div>
  );
}

function EquityChart({ staticCurve, spinupCurve }) {
  const width = 560;
  const height = 160;
  const pad = 8;

  const points = useMemo(() => {
    const all = [...staticCurve, ...spinupCurve];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const range = max - min || 1;
    const toPoints = (curve) =>
      curve
        .map((v, i) => {
          const x = pad + (i / (curve.length - 1)) * (width - pad * 2);
          const y = height - pad - ((v - min) / range) * (height - pad * 2);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
    return { staticPts: toPoints(staticCurve), spinupPts: toPoints(spinupCurve) };
  }, [staticCurve, spinupCurve]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="equity-chart" preserveAspectRatio="none">
      <line x1={pad} y1={height / 2} x2={width - pad} y2={height / 2} stroke="var(--hairline)" strokeWidth="1" strokeDasharray="3 4" />
      <polyline points={points.staticPts} fill="none" stroke="var(--accent-brand)" strokeWidth="2" />
      <polyline points={points.spinupPts} fill="none" stroke="var(--accent-gain)" strokeWidth="2" />
    </svg>
  );
}

export default function ExperimentPanel({ initial }) {
  const [result, setResult] = useState(initial || null);
  const [running, setRunning] = useState(false);

  const handleRun = async () => {
    setRunning(true);
    const r = await runExperiment(40);
    setResult(r);
    setRunning(false);
  };

  return (
    <div>
      <div className="experiment-head">
        <div className="section-sub">
          Same event stream, same simulated market outcomes, both arms — the only variable is
          whether capital gets reallocated by performance.
        </div>
        <button className="run-btn secondary" onClick={handleRun} disabled={running}>
          {running ? "Running 40 events…" : "Run experiment"}
        </button>
      </div>

      {!result ? (
        <div className="section-sub" style={{ marginTop: 12 }}>
          No experiment run yet.
        </div>
      ) : (
        <div className="experiment-body">
          <EquityChart
            staticCurve={result.static.equity_curve}
            spinupCurve={result.spinup.equity_curve}
          />
          <div className="experiment-legend">
            <span><i className="dot brand" /> Static Desk</span>
            <span><i className="dot gain" /> Spinup Capital</span>
          </div>

          <table className="experiment-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Static Desk</th>
                <th>Spinup Capital</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Return</td>
                <td>{(result.static.return_pct * 100).toFixed(1)}%</td>
                <td>{(result.spinup.return_pct * 100).toFixed(1)}%</td>
              </tr>
              <tr>
                <td>Sharpe (proxy)</td>
                <td>{result.static.sharpe_proxy.toFixed(2)}</td>
                <td>{result.spinup.sharpe_proxy.toFixed(2)}</td>
              </tr>
              <tr>
                <td>Max drawdown</td>
                <td>{(result.static.max_drawdown_pct * 100).toFixed(1)}%</td>
                <td>{(result.spinup.max_drawdown_pct * 100).toFixed(1)}%</td>
              </tr>
              <tr>
                <td>Win rate</td>
                <td>{Math.round(result.static.win_rate * 100)}%</td>
                <td>{Math.round(result.spinup.win_rate * 100)}%</td>
              </tr>
              <tr>
                <td>Trades executed / blocked</td>
                <td>{result.static.trades_executed} / {result.static.trades_blocked}</td>
                <td>{result.spinup.trades_executed} / {result.spinup.trades_blocked}</td>
              </tr>
              <tr>
                <td>Agents fired</td>
                <td>{result.static.agents_fired}</td>
                <td>{result.spinup.agents_fired}</td>
              </tr>
              <tr>
                <td>Final equity</td>
                <td>${result.static.final_equity.toLocaleString()}</td>
                <td>${result.spinup.final_equity.toLocaleString()}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <MonteCarloPanel />
    </div>
  );
}
