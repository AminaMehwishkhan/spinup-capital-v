import React, { useEffect, useState, useCallback, useRef } from "react";
import TopNav from "./components/TopNav.jsx";
import Hero from "./components/Hero.jsx";
import KpiGrid from "./components/KpiGrid.jsx";
import Leaderboard from "./components/Leaderboard.jsx";
import OrgChart from "./components/OrgChart.jsx";
import ActivityLog from "./components/ActivityLog.jsx";
import TradeFeed from "./components/TradeFeed.jsx";
import MemoryPanel from "./components/MemoryPanel.jsx";
import ArenaPanel from "./components/ArenaPanel.jsx";
import ExperimentPanel from "./components/ExperimentPanel.jsx";
import PermissionConsole from "./components/PermissionConsole.jsx";
import RetirementArchive from "./components/RetirementArchive.jsx";
import LearningCurvePanel from "./components/LearningCurvePanel.jsx";
import BacktestPanel from "./components/BacktestPanel.jsx";
import AuditPanel from "./components/AuditPanel.jsx";
import {
  fetchSummary, fetchAgents, fetchTrades, fetchLessons, fetchArenaLog, runDemo,
  fetchPermissionMatrix, fetchRetirements,
} from "./api.js";

const POLL_INTERVAL_MS = 5000;

export default function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [summary, setSummary] = useState(null);
  const [agents, setAgents] = useState([]);
  const [trades, setTrades] = useState([]);
  const [lessons, setLessons] = useState([]);
  const [arenaLog, setArenaLog] = useState([]);
  const [permMatrix, setPermMatrix] = useState(null);
  const [retirements, setRetirements] = useState([]);
  const [running, setRunning] = useState(false);
  const [offlineNote, setOfflineNote] = useState(false);
  const inFlight = useRef(false);

  const loadAll = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const [s, a, t, l, ar, pm, ret] = await Promise.all([
        fetchSummary(), fetchAgents(), fetchTrades(), fetchLessons(), fetchArenaLog(),
        fetchPermissionMatrix(), fetchRetirements(),
      ]);
      setSummary(s);
      setAgents(a);
      setTrades(t);
      setLessons(l);
      setArenaLog(ar);
      setPermMatrix(pm);
      setRetirements(ret);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible" && !running) loadAll();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [running, loadAll]);

  const handleRun = async () => {
    setRunning(true);
    const result = await runDemo(4);
    if (result.status === "offline") setOfflineNote(true);
    await loadAll();
    setRunning(false);
  };

  if (!summary) return null;

  return (
    <div className="app-root">
      <TopNav active={activeTab} onChange={setActiveTab} onRun={handleRun} running={running} />

      <div className="shell">
        {offlineNote && (
          <div className="offline-banner">
            Backend not reachable at localhost:8000 — showing static demo data. Start it with{" "}
            <code>uvicorn backend.main:app --reload</code>.
          </div>
        )}

        {activeTab === "overview" && (
          <>
            <Hero summary={summary} onRun={handleRun} running={running} onJump={() => setActiveTab("agents")} />
            <KpiGrid summary={summary} />

            <div className="two-col">
              <div>
                <div className="section-head">
                  <div className="section-title">Top agents by performance</div>
                  <div className="section-sub">ranked by realized P&amp;L</div>
                </div>
                <Leaderboard agents={agents} />
              </div>
              <div>
                <div className="section-head">
                  <div className="section-title">Live activity</div>
                  <div className="section-sub">audit trail</div>
                </div>
                <ActivityLog trades={trades} agents={agents} />
              </div>
            </div>

            <div className="section-head">
              <div className="section-title">Access control</div>
              <div className="section-sub">every role's real permission scope — enforced at runtime, not just documented</div>
            </div>
            <PermissionConsole matrix={permMatrix} />
          </>
        )}

        {activeTab === "agents" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Firm org chart</div>
              <div className="section-sub">
                {summary.agents_hired} hired · {summary.agents_active} active · {summary.agents_fired} fired
              </div>
            </div>
            <OrgChart agents={agents} />

            <div className="section-head">
              <div className="section-title">Hiring pipeline</div>
              <div className="section-sub">Agent Arena — candidates trial before real capital</div>
            </div>
            <ArenaPanel reviews={arenaLog} />

            <div className="section-head">
              <div className="section-title">Retirement archive</div>
              <div className="section-sub">fired agents' careers, condensed into a lesson the next hire inherits</div>
            </div>
            <RetirementArchive retirements={retirements} />
          </>
        )}

        {activeTab === "trades" && (
          <div className="two-col" style={{ marginTop: 28 }}>
            <div>
              <div className="section-head" style={{ marginTop: 0 }}>
                <div className="section-title">Trade proposals &amp; risk decisions</div>
                <div className="section-sub">most recent first</div>
              </div>
              <TradeFeed trades={trades} />
            </div>
            <div>
              <div className="section-head" style={{ marginTop: 0 }}>
                <div className="section-title">Live activity</div>
                <div className="section-sub">audit trail</div>
              </div>
              <ActivityLog trades={trades} agents={agents} />
            </div>
          </div>
        )}

        {activeTab === "access" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Access control</div>
              <div className="section-sub">every role's real permission scope — enforced at runtime, not just documented</div>
            </div>
            <PermissionConsole matrix={permMatrix} />
          </>
        )}

        {activeTab === "memory" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Trading memory</div>
              <div className="section-sub">lessons the firm has learned, reused across agents</div>
            </div>
            <MemoryPanel lessons={lessons} />

            <div className="section-head">
              <div className="section-title">Does memory actually change outcomes?</div>
              <div className="section-sub">win rate / avg P&amp;L for trades proposed with vs. without a relevant lesson available</div>
            </div>
            <LearningCurvePanel />

            <div className="section-head">
              <div className="section-title">Retirement archive</div>
              <div className="section-sub">fired agents' careers, condensed into a lesson the next hire inherits</div>
            </div>
            <RetirementArchive retirements={retirements} />
          </>
        )}

        {activeTab === "experiment" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Does the organization actually help?</div>
              <div className="section-sub">static desk vs. Spinup control experiment</div>
            </div>
            <ExperimentPanel />
          </>
        )}

        {activeTab === "backtest" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Historical replay</div>
              <div className="section-sub">real price history, real settlement math at expiration — not a coin flip</div>
            </div>
            <BacktestPanel />
          </>
        )}

        {activeTab === "audit" && (
          <>
            <div className="section-head" style={{ marginTop: 28 }}>
              <div className="section-title">Alpaca execution &amp; audit</div>
              <div className="section-sub">the broker's own ledger, reconciled against the firm's internal records</div>
            </div>
            <AuditPanel />
          </>
        )}

        <div className="footer-note">
          Every trade proposed by an LLM. Every risk decision made by deterministic code.
          Every dollar tracked back to the agent that earned or lost it.
        </div>
      </div>
    </div>
  );
}
