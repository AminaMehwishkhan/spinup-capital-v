import React from "react";

const ROLE_LABELS = {
  earnings: "Earnings Specialist",
  macro: "Macro Specialist",
  volatility: "Volatility Specialist",
  hedging: "Hedging Specialist",
};

export default function AgentBadge({ agent }) {
  const winRate = agent.trade_count > 0 ? Math.round((agent.wins / agent.trade_count) * 100) : null;
  const pnlClass = agent.total_pnl >= 0 ? "gain" : "loss";

  return (
    <div className={`badge ${agent.status}`}>
      <div className="badge-top">
        <div>
          <div className="badge-id">{agent.agent_id}</div>
          <div className="badge-role">{ROLE_LABELS[agent.specialist_type] || agent.specialist_type}</div>
        </div>
        <span className={`status-pill ${agent.status}`}>{agent.status.toLowerCase()}</span>
      </div>

      <div className="badge-stats">
        <div>
          <div className="badge-stat-label">Capital</div>
          <div className="badge-stat-value">${agent.capital.toLocaleString()}</div>
        </div>
        <div>
          <div className="badge-stat-label">P&amp;L</div>
          <div className={`badge-stat-value ${pnlClass}`}>
            {agent.total_pnl >= 0 ? "+" : ""}
            {agent.total_pnl.toLocaleString()}
          </div>
        </div>
        <div>
          <div className="badge-stat-label">Trades</div>
          <div className="badge-stat-value">{agent.trade_count}</div>
        </div>
        <div>
          <div className="badge-stat-label">Win rate</div>
          <div className="badge-stat-value">{winRate === null ? "—" : `${winRate}%`}</div>
        </div>
      </div>

      {agent.permissions && agent.permissions.length > 0 && (
        <div className="badge-permissions">
          {agent.permissions.map((p) => (
            <span className="badge-perm-tag" key={p}>{p}</span>
          ))}
        </div>
      )}
    </div>
  );
}
