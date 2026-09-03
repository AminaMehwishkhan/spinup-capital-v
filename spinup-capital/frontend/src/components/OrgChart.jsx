import React from "react";
import AgentBadge from "./AgentBadge.jsx";

export default function OrgChart({ agents }) {
  const activeCount = agents.filter((a) => a.status !== "FIRED").length;

  return (
    <div className="org-chart">
      <div className="mp-node">MANAGING PARTNER</div>
      <svg className="org-lines" viewBox="0 0 720 34" preserveAspectRatio="none">
        <line x1="360" y1="0" x2="360" y2="12" stroke="var(--hairline-bright)" strokeWidth="1.5" />
        <line x1="60" y1="12" x2="660" y2="12" stroke="var(--hairline-bright)" strokeWidth="1.5" />
        {agents.slice(0, 6).map((_, i) => {
          const x = 60 + (i * 600) / Math.max(agents.length - 1, 1);
          return (
            <line
              key={i}
              x1={x}
              y1="12"
              x2={x}
              y2="30"
              stroke="var(--hairline-bright)"
              strokeWidth="1.5"
            />
          );
        })}
      </svg>
      <div className="badge-row">
        {agents.map((a) => (
          <AgentBadge agent={a} key={a.agent_id} />
        ))}
      </div>
      <div className="section-sub" style={{ marginTop: 16 }}>
        {activeCount} active specialist{activeCount === 1 ? "" : "s"} · {agents.length - activeCount} retired
      </div>
    </div>
  );
}
