import React from "react";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "agents", label: "Agents" },
  { id: "trades", label: "Trades" },
  { id: "access", label: "Access control" },
  { id: "memory", label: "Memory" },
  { id: "experiment", label: "Experiment" },
  { id: "backtest", label: "Backtest" },
  { id: "audit", label: "Audit" },
];

export default function TopNav({ active, onChange, onRun, running }) {
  return (
    <div className="topnav">
      <div className="topnav-inner">
        <div className="topnav-brand">
          <span className="brand-mark">SC</span>
          <div>
            <div className="brand-name">Spinup Capital</div>
            <div className="brand-sub">Autonomous trading firm</div>
          </div>
        </div>

        <div className="topnav-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`topnav-tab ${active === t.id ? "active" : ""}`}
              onClick={() => onChange(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <button className="run-btn" onClick={onRun} disabled={running}>
          {running ? "Running…" : "Run market cycle"}
        </button>
      </div>
    </div>
  );
}
