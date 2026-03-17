import React, { useState, useEffect, useCallback } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Graph3D  from "./components/Graph3D";
import Sidebar  from "./components/Sidebar";
import Login    from "./components/Login";
import Signup   from "./components/Signup";
import Chat     from "./components/Chat";

const API = "http://localhost:8000";

function MainApp({ user, setUser }) {
  const [selectedNode,  setSelectedNode]  = useState(null);
  const [brainOpen,     setBrainOpen]     = useState(true);
  const [graphData,     setGraphData]     = useState({ nodes: [], links: [] });
  const [citedNodeIds,  setCitedNodeIds]  = useState([]);
  const [stats,         setStats]         = useState({
    memories: 0, lastRetrievalMs: null, healthy: null
  });
  const navigate = useNavigate();

  // Initial graph load + health check
  useEffect(() => {
    if (!user?.username) return;

    const loadGraph = async () => {
      try {
        const r = await fetch(`${API}/graph-visuals/${user.username}`);
        if (r.ok) {
          const d = await r.json();
          setGraphData(d);
          const memCount = d.nodes?.filter(n => n.type === "Memory").length || 0;
          setStats(s => ({ ...s, memories: memCount }));
        }
      } catch (_) {}
    };

    const checkHealth = async () => {
      try {
        const r = await fetch(`${API}/health`);
        if (r.ok) {
          const d = await r.json();
          setStats(s => ({ ...s, healthy: d.status === "healthy" }));
        }
      } catch (_) { setStats(s => ({ ...s, healthy: false })); }
    };

    loadGraph();
    checkHealth();

    // Poll graph every 30s to keep it live
    const poll = setInterval(loadGraph, 30000);
    return () => clearInterval(poll);
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem("graphmind_user");
    setUser(null);
    navigate("/login");
  };

  const initials = user?.username
    ? user.username.slice(0, 2).toUpperCase()
    : "??";

  const memCount = graphData.nodes?.filter(n => n.type === "Memory").length || 0;
  const conCount = graphData.nodes?.filter(n => n.type === "Concept").length || 0;

  return (
    <div className="dashboard">
      {/* ── Topbar ── */}
      <div className="topbar">
        <div className="topbar-logo">
          <div className="logo-orb">🧠</div>
          GraphMind
        </div>
        <div className="topbar-divider" />

        <div className="topbar-stats">
          <div className="stat-chip">
            <div className={`ind ${stats.healthy === true ? "green" : stats.healthy === false ? "red" : "gold"}`} />
            <span className="val">
              {stats.healthy === true ? "Online" : stats.healthy === false ? "Degraded" : "Checking"}
            </span>
          </div>
          <div className="stat-chip">
            <div className="ind purple" />
            <span className="val">{memCount}</span>
            <span>memories</span>
          </div>
          <div className="stat-chip">
            <div className="ind cyan" />
            <span className="val">{conCount}</span>
            <span>concepts</span>
          </div>
          {stats.lastRetrievalMs != null && (
            <div className="stat-chip">
              <div className="ind gold" />
              <span className="val">{stats.lastRetrievalMs}ms</span>
              <span>last retrieval</span>
            </div>
          )}
        </div>

        <div className="topbar-right">
          <div className="user-pill">
            <div className="user-avatar">{initials}</div>
            {user?.username}
          </div>
          <button className="topbar-btn" onClick={handleLogout}>Sign out</button>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="dashboard-body">
        <div className="chat-section">
          <Chat
            user={user}
            setGraphData={(d) => {
              setGraphData(d);
              const mc = d.nodes?.filter(n => n.type === "Memory").length || 0;
              setStats(s => ({ ...s, memories: mc }));
            }}
            setCitedNodeIds={setCitedNodeIds}
            setStats={setStats}
          />
        </div>

        <div className={`brain-section ${brainOpen ? "open" : "collapsed"}`}>
          <button
            className={`toggle-btn ${brainOpen ? "open" : "collapsed"}`}
            onClick={() => setBrainOpen(v => !v)}
          >
            <span className="chev">{brainOpen ? "›" : "‹"}</span>
          </button>

          {brainOpen && (
            <>
              <div className="brain-top">
                <div className="brain-label">3D Knowledge Graph</div>
                <Graph3D
                  graphData={graphData}
                  onSelectNode={setSelectedNode}
                  citedNodeIds={citedNodeIds}
                />
              </div>
              <div className="brain-bottom">
                <Sidebar skill={selectedNode} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(() => {
    const s = localStorage.getItem("graphmind_user");
    return s ? JSON.parse(s) : null;
  });

  return (
    <Routes>
      <Route path="/login"  element={user ? <Navigate to="/app" /> : <Login  onLogin={setUser}  />} />
      <Route path="/signup" element={user ? <Navigate to="/app" /> : <Signup onSignup={setUser} />} />
      <Route path="/app"    element={user ? <MainApp user={user} setUser={setUser} /> : <Navigate to="/login" />} />
      <Route path="*"       element={<Navigate to="/login" />} />
    </Routes>
  );
}
