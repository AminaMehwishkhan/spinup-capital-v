import React, { useState } from "react";
import { attemptUnauthorizedTrade } from "../api.js";

const ROLE_LABELS = {
  managing_partner: "Managing Partner",
  specialist: "Specialist (any type)",
  bull_bear: "Bull / Bear Desk",
  risk_governor: "Risk Governor",
  execution_gateway: "Execution Gateway",
  talent_agent: "Head of Talent",
};

const PERM_LABELS = {
  market_data: "Market data",
  options_data: "Options data",
  "trading:propose": "Propose trades",
  "trading:execute": "Execute trades",
  "account:read": "Read account",
  "account:write": "Write account",
};

export default function PermissionConsole({ matrix }) {
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const handleAttempt = async () => {
    setRunning(true);
    setResult(null);
    const r = await attemptUnauthorizedTrade();
    // small delay so the "attempting..." state is perceptible, not instant
    await new Promise((res) => setTimeout(res, 500));
    setResult(r);
    setRunning(false);
  };

  if (!matrix || !matrix.roles) return null;

  return (
    <div className="perm-console">
      <div className="perm-matrix-wrap">
        <table className="perm-matrix">
          <thead>
            <tr>
              <th className="perm-role-head">Role</th>
              {matrix.permissions.map((p) => (
                <th key={p} className="perm-col-head" title={PERM_LABELS[p] || p}>
                  {PERM_LABELS[p] || p}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.roles.map((r) => (
              <tr key={r.role} className={r.role === "execution_gateway" ? "perm-row-highlight" : ""}>
                <td className="perm-role-name">{ROLE_LABELS[r.role] || r.role}</td>
                {matrix.permissions.map((p) => (
                  <td key={p} className="perm-cell">
                    {r.granted.includes(p) ? (
                      <span className="perm-yes" aria-label="granted">✓</span>
                    ) : (
                      <span className="perm-no" aria-label="denied">·</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="perm-demo">
        <div className="perm-demo-copy">
          <div className="perm-demo-title">Prove it, live</div>
          <div className="perm-demo-sub">
            Try to route a trade through the Bull/Bear desk — a role that only ever holds{" "}
            <code>market_data</code> and <code>options_data</code>. The Execution Gateway checks
            this scope on every call, not just at hire time.
          </div>
        </div>
        <button className="perm-attempt-btn" onClick={handleAttempt} disabled={running}>
          {running ? "Attempting…" : "Attempt unauthorized trade"}
        </button>
      </div>

      {result && (
        <div className={`perm-result ${result.blocked ? "blocked" : "allowed"}`}>
          <span className="perm-result-badge">{result.blocked ? "BLOCKED" : "ALLOWED"}</span>
          <div className="perm-result-body">
            <div>
              <b>{ROLE_LABELS[result.role] || result.role}</b> attempted{" "}
              <code>{result.attempted_permission}</code>
            </div>
            <div className="perm-result-detail">
              Held permissions: {(result.held_permissions || []).join(", ") || "none"}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
