import React from "react";

export default function MemoryPanel({ lessons }) {
  if (!lessons || lessons.length === 0) {
    return <div className="section-sub">No lessons recorded yet — close a trade to populate firm memory.</div>;
  }
  return (
    <div className="memory-grid">
      {lessons.map((l) => (
        <div className={`memory-card ${l.outcome}`} key={l.id}>
          <div className="memory-head">
            <span className="memory-tag">{l.specialist_type} · {l.ticker}</span>
            <span className={`memory-outcome ${l.outcome}`}>{l.outcome}</span>
          </div>
          <div className="memory-rule">{l.rule}</div>
          <div className="memory-context">IV at entry: {l.iv_percentile}th pct</div>
        </div>
      ))}
    </div>
  );
}
