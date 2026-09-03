import React, { useMemo } from "react";

function buildEntries(trades, agents) {
  const entries = [];
  trades.forEach((t) => {
    if (t.risk_approved === false) {
      entries.push({
        cls: "loss",
        ticker: t.ticker,
        text: (
          <>
            <b>{t.agent_id}</b> trade blocked by Risk Governor — {t.risk_reasons || "risk check failed"}
          </>
        ),
      });
    } else if (t.filled === false) {
      entries.push({
        cls: "warn",
        ticker: t.ticker,
        text: (
          <>
            <b>{t.agent_id}</b> {t.strategy?.replaceAll("_", " ")} on {t.ticker} approved by Risk Governor
            but not yet filled{t.submission_error ? ` — ${t.submission_error}` : " — pending"}
          </>
        ),
      });
    } else {
      entries.push({
        cls: t.pnl >= 0 ? "gain" : "warn",
        ticker: t.ticker,
        text: (
          <>
            <b>{t.agent_id}</b> closed {t.strategy?.replaceAll("_", " ")} on {t.ticker}:{" "}
            {t.pnl >= 0 ? "+" : ""}
            {t.pnl}
          </>
        ),
      });
    }
  });
  agents.forEach((a) => {
    if (a.status === "FIRED") {
      entries.push({
        cls: "loss",
        ticker: "HR",
        text: (
          <>
            <b>{a.agent_id}</b> terminated — capital reclaimed to treasury
          </>
        ),
      });
    } else if (a.status === "PROMOTED") {
      entries.push({
        cls: "gain",
        ticker: "HR",
        text: (
          <>
            <b>{a.agent_id}</b> promoted — capital increased to ${a.capital.toLocaleString()}
          </>
        ),
      });
    }
  });
  return entries;
}

export default function ActivityLog({ trades, agents }) {
  const entries = useMemo(() => buildEntries(trades, agents), [trades, agents]);

  return (
    <div className="log">
      {entries.length === 0 && (
        <div className="log-row">
          <span className="log-text">No activity yet — run the demo loop to populate this feed.</span>
        </div>
      )}
      {entries.map((e, i) => (
        <div className={`log-row ${e.cls}`} key={i}>
          <span className="log-ticker">{e.ticker}</span>
          <span className="log-text">{e.text}</span>
        </div>
      ))}
    </div>
  );
}
