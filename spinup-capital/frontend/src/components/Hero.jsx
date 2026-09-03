import React from "react";

export default function Hero({ summary, onRun, onJump, running }) {
  return (
    <div className="hero">
      <div className="hero-badges">
        <span className="live-badge">
          <span className="live-badge-dot" /> Live firm
        </span>
        <span className="hero-date">
          {summary.agents_active} active agent{summary.agents_active === 1 ? "" : "s"} · updated just now
        </span>
      </div>

      <h1 className="hero-title">
        Every trade is proposed by an AI. <span className="grad-text">Every dollar is tracked</span> back
        to the agent that earned it.
      </h1>

      <p className="hero-sub">
        Spinup Capital hires specialist trading agents, forces every proposal through adversarial risk
        review, executes on a real Alpaca paper account, and reallocates capital based on what actually
        happened — not what an agent claims it did.
      </p>

      <div className="hero-actions">
        <button className="run-btn" onClick={onRun} disabled={running}>
          {running ? "Running cycle…" : "Run market cycle"}
        </button>
        <button className="run-btn secondary" onClick={onJump}>
          View the org chart
        </button>
      </div>
    </div>
  );
}
