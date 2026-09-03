import React from "react";

export default function RetirementArchive({ retirements }) {
  if (!retirements || retirements.length === 0) {
    return (
      <div className="section-sub">
        No agent has been retired yet — a terminated agent's career gets archived here for future hires
        of the same specialist type to inherit.
      </div>
    );
  }
  return (
    <div className="retirement-grid">
      {retirements.map((r) => (
        <div className="retirement-card" key={r.id}>
          <div className="retirement-head">
            <span className="retirement-tag">{r.specialist_type}</span>
            <span className="retirement-id">{r.agent_id}</span>
          </div>
          <div className="retirement-lesson">{r.lesson}</div>
          <div className="retirement-rule">
            <span className="retirement-rule-label">Inherited rule</span>
            {r.rule}
          </div>
        </div>
      ))}
    </div>
  );
}
