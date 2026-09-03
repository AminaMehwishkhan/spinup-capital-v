import React, { useEffect, useState } from "react";
import { fetchLearningCurve } from "../api.js";

export default function LearningCurvePanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchLearningCurve().then(setData);
  }, []);

  if (!data) return null;
  const entries = Object.entries(data.by_specialist_type || {});

  if (entries.length === 0) {
    return <div className="section-sub">Not enough closed trades yet — run a few market cycles.</div>;
  }

  return (
    <div>
      <table className="experiment-table">
        <thead>
          <tr>
            <th>Specialist type</th>
            <th>No memory available</th>
            <th>With memory available</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([stype, buckets]) => (
            <tr key={stype}>
              <td style={{ textTransform: "capitalize" }}>{stype}</td>
              <td>
                {buckets.no_memory.trades === 0
                  ? "no trades"
                  : `${Math.round(buckets.no_memory.win_rate * 100)}% win · $${buckets.no_memory.avg_pnl} avg (${buckets.no_memory.trades})`}
              </td>
              <td>
                {buckets.with_memory.trades === 0
                  ? "no trades"
                  : `${Math.round(buckets.with_memory.win_rate * 100)}% win · $${buckets.with_memory.avg_pnl} avg (${buckets.with_memory.trades})`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="section-sub" style={{ marginTop: 12 }}>{data.note}</div>
    </div>
  );
}
