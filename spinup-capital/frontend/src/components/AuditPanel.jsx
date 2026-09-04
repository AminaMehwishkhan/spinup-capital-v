import React, { useEffect, useState } from "react";
import { fetchAlpacaAccount, fetchAlpacaPositions, fetchAlpacaOrders, reconcileAlpacaTrades } from "../api.js";

export default function AuditPanel() {
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [reconcileResult, setReconcileResult] = useState(null);
  const [reconciling, setReconciling] = useState(false);

  const load = () => {
    fetchAlpacaAccount().then(setAccount);
    fetchAlpacaPositions().then(setPositions);
    fetchAlpacaOrders().then(setOrders);
  };

  useEffect(() => {
    load();
  }, []);

  const handleReconcile = async () => {
    setReconciling(true);
    const r = await reconcileAlpacaTrades();
    setReconcileResult(r);
    load();
    setReconciling(false);
  };

  return (
    <div>
      

      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(2, 1fr)", marginTop: 0, marginBottom: 32 }}>
        <div className="kpi-card">
          <div className="kpi-head"><span className="kpi-label">Account cash</span></div>
          <div className="kpi-value">${(account?.cash ?? 0).toLocaleString()}</div>
          <div className="kpi-meta">live Alpaca paper account</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-head"><span className="kpi-label">Buying power</span></div>
          <div className="kpi-value">${(account?.buying_power ?? 0).toLocaleString()}</div>
          <div className="kpi-meta">available for new positions</div>
        </div>
      </div>

      <div className="section-head" style={{ marginTop: 0 }}>
        <div className="section-title">Open positions</div>
        <div className="section-sub">straight from the broker, not the internal Trade table</div>
      </div>
      {positions.length === 0 ? (
        <div className="section-sub">No open positions.</div>
      ) : (
        <div className="log">
          {positions.map((p, i) => (
            <div className="log-row" key={i}>
              <div className="log-ticker">{p.symbol}</div>
              <div className="log-text">
                qty {p.qty} · market value ${p.market_value} ·{" "}
                <span className={p.unrealized_pl >= 0 ? "gain" : "loss"}>
                  {p.unrealized_pl >= 0 ? "+" : ""}${p.unrealized_pl}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="section-head">
        <div className="section-title">Recent broker orders</div>
        <div className="section-sub">Alpaca's own order ledger — ground truth to reconcile against</div>
      </div>
      {orders.length === 0 ? (
        <div className="section-sub">No recent orders.</div>
      ) : (
        <div className="log">
          {orders.map((o, i) => (
            <div className="log-row" key={i}>
              <div className="log-ticker">{o.symbol || "—"}</div>
              <div className="log-text">
                <b>{o.client_order_id}</b> · {o.status} · {o.side} × {o.filled_qty}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="section-head">
        <div className="section-title">Reconcile pending trades</div>
        <div className="section-sub">closes open live trades and books real realized P&amp;L into Autopsy → Talent</div>
      </div>
      <div className="perm-console">
        <div className="perm-demo" style={{ marginTop: 0, paddingTop: 0, borderTop: "none" }}>
          <div className="perm-demo-copy">
            <div className="perm-demo-sub">
              Pending live trades only get an unrealized mark-to-market snapshot at entry. This
              actually closes each one and runs Autopsy + Talent review on the real outcome.
            </div>
          </div>
          <button className="run-btn" onClick={handleReconcile} disabled={reconciling}>
            {reconciling ? "Reconciling…" : "Reconcile now"}
          </button>
        </div>
        {reconcileResult && (
          <div style={{ marginTop: 16, fontSize: 12.5, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
            {JSON.stringify(reconcileResult.results, null, 2)}
          </div>
        )}
      </div>
    </div>
  );
}
