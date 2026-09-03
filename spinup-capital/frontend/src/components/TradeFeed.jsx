import React from "react";

export default function TradeFeed({ trades }) {
  if (trades.length === 0) {
    return <div className="section-sub">No trades proposed yet.</div>;
  }
  return (
    <div>
      {trades.map((t) => (
        <div className="trade-card" key={t.trade_id}>
          <div className="trade-head">
            <span>
              {t.ticker} · {t.strategy?.replaceAll("_", " ")}
            </span>
            <span className={`trade-pill ${t.risk_approved ? "approved" : "blocked"}`}>
              {t.risk_approved ? "risk approved" : "blocked"}
            </span>
          </div>
          <div className="trade-thesis">{t.thesis}</div>
          {!t.risk_approved && t.risk_reasons && (
            <div className="trade-reason">{t.risk_reasons}</div>
          )}
          {t.risk_approved && t.filled === false && (
            <div className="trade-reason">
              {t.submission_error ? `Not filled — ${t.submission_error}` : "Approved and submitted — not yet filled."}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
