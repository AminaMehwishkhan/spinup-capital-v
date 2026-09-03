import React from "react";

export default function ArenaPanel({ reviews }) {
  if (!reviews || reviews.length === 0) {
    return <div className="section-sub">No candidates run through the Arena yet.</div>;
  }
  return (
    <div className="arena-list">
      {reviews.map((r) => (
        <div className={`arena-row ${r.passed ? "passed" : "declined"}`} key={r.id}>
          <div className="arena-verdict">
            <span className={`arena-pill ${r.passed ? "passed" : "declined"}`}>
              {r.passed ? "hired" : "declined"}
            </span>
          </div>
          <div className="arena-body">
            <div className="arena-id">{r.candidate_id}</div>
            <div className="arena-stats">
              {r.trials_run} trials · {Math.round(r.win_rate * 100)}% win rate ·{" "}
              {r.avg_pnl >= 0 ? "+" : ""}
              {Math.round(r.avg_pnl)} avg P&amp;L · {Math.round(r.risk_pass_rate * 100)}% cleared risk
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
