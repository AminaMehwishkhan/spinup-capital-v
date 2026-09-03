import React from "react";

function Icon({ name }) {
  const common = { width: 15, height: 15, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "vault":
      return (
        <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="12" cy="12" r="3" /><path d="M12 9v0" /></svg>
      );
    case "deployed":
      return (
        <svg {...common}><path d="M3 17l6-6 4 4 8-8" /><path d="M17 7h4v4" /></svg>
      );
    case "value":
      return (
        <svg {...common}><path d="M4 20V10M12 20V4M20 20v-7" /></svg>
      );
    case "bolt":
      return (
        <svg {...common}><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" /></svg>
      );
    default:
      return null;
  }
}

export default function KpiGrid({ summary }) {
  const items = [
    { icon: "vault", label: "Treasury", value: `$${summary.treasury.toLocaleString()}`, meta: "uncommitted capital" },
    { icon: "deployed", label: "Deployed to agents", value: `$${summary.deployed_capital.toLocaleString()}`, meta: `${summary.agents_active} active` },
    { icon: "value", label: "Total firm value", value: `$${summary.total_firm_value.toLocaleString()}`, meta: "treasury + deployed" },
    {
      icon: "bolt",
      label: "Trades executed / blocked",
      value: (
        <>
          <span className="gain">{summary.trades_executed}</span>
          <span className="kpi-sep"> / </span>
          <span className="loss">{summary.trades_blocked}</span>
        </>
      ),
      meta: "by the Risk Governor",
    },
  ];

  return (
    <div className="kpi-grid">
      {items.map((it) => (
        <div className="kpi-card" key={it.label}>
          <div className="kpi-head">
            <span className="kpi-label">{it.label}</span>
            <span className="kpi-icon"><Icon name={it.icon} /></span>
          </div>
          <div className="kpi-value">{it.value}</div>
          <div className="kpi-meta">{it.meta}</div>
        </div>
      ))}
    </div>
  );
}
