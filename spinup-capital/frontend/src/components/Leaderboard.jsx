import React from "react";

const TYPE_INITIALS = {
  earnings: "ER",
  macro: "MC",
  volatility: "VL",
  hedging: "HG",
};

const TYPE_COLOR_CLASS = {
  earnings: "avatar-amber",
  macro: "avatar-blue",
  volatility: "avatar-purple",
  hedging: "avatar-teal",
};

function Row({ rank, agent }) {
  const pnlPct = agent.capital > 0 ? (agent.total_pnl / Math.max(agent.capital - agent.total_pnl, 1)) * 100 : 0;
  const isGain = agent.total_pnl >= 0;
  return (
    <div className="lb-row">
      <div className="lb-rank">{rank}</div>
      <div className={`lb-avatar ${TYPE_COLOR_CLASS[agent.specialist_type] || "avatar-slate"}`}>
        {TYPE_INITIALS[agent.specialist_type] || "??"}
      </div>
      <div className="lb-body">
        <div className="lb-name">{agent.agent_id}</div>
        <div className="lb-meta">
          {agent.specialist_type} · {agent.trade_count} trade{agent.trade_count === 1 ? "" : "s"} ·{" "}
          {agent.status.toLowerCase()}
        </div>
      </div>
      <div className="lb-figures">
        <div className="lb-value">${agent.capital.toLocaleString()}</div>
        <div className={`lb-change ${isGain ? "gain" : "loss"}`}>
          {isGain ? "+" : ""}
          {pnlPct.toFixed(1)}%
        </div>
      </div>
    </div>
  );
}

export default function Leaderboard({ agents, limit = 6 }) {
  const ranked = [...agents]
    .filter((a) => a.status !== "FIRED")
    .sort((a, b) => b.total_pnl - a.total_pnl)
    .slice(0, limit);

  if (ranked.length === 0) {
    return <div className="section-sub">No active agents yet — run a market cycle to hire the first specialist.</div>;
  }

  return (
    <div className="lb-list">
      {ranked.map((a, i) => (
        <Row key={a.agent_id} rank={i + 1} agent={a} />
      ))}
    </div>
  );
}
