import React, { useState, useEffect, useCallback } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Graph3D           from "./components/Graph3D";
import Sidebar           from "./components/Sidebar";
import IntelligencePanel from "./components/IntelligencePanel";
import Login             from "./components/Login";
import Signup            from "./components/Signup";
import Chat              from "./components/Chat";

const API = "http://localhost:8000";

/* ── localStorage helpers (mirrors IntelligencePanel) ───────────────────── */
const lsGet = (k, fb) => {
  try { const v = localStorage.getItem(k); return v !== null ? JSON.parse(v) : fb; }
  catch { return fb; }
};
const K = (u) => ({
  idate:  `gm_idate_${u}`,
  plan:   `gm_plan_${u}`,
  done:   `gm_plandone_${u}`,
  target: `gm_target_${u}`,
});
const todayStr  = () => new Date().toISOString().slice(0, 10);
const daysLeft  = (ds) => { if (!ds) return null; return Math.ceil((new Date(ds) - new Date()) / 86400000); };
const greetWord = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

const QUOTES = [
  "The expert in anything was once a beginner.",
  "Consistency beats intensity. Every single time.",
  "One problem a day keeps the rejection away.",
  "You don't rise to your goals. You fall to your systems.",
  "Progress is invisible until it isn't.",
  "Hard problems today, easy interviews tomorrow.",
  "Your future self is watching. Make them proud.",
  "Show up today. That's the whole job.",
  "It compounds. Keep going.",
  "The grind is the shortcut.",
  "One hour daily beats ten hours on Sunday.",
  "Doubt kills more dreams than failure ever will.",
  "Every weak topic is just an unopened door.",
  "The interview rewards those who put in the hours.",
  "Build the habit. The skill follows.",
  "Solve one more problem. Just one.",
  "Clarity comes from action, not thought.",
  "The best revenge is getting the offer.",
  "You've solved hard problems before. This is another.",
  "Trust the process. The process doesn't lie.",
];
const dailyQuote = () => {
  const doy = Math.floor((new Date() - new Date(new Date().getFullYear(), 0, 0)) / 86400000);
  return QUOTES[doy % QUOTES.length];
};

/* ── Stable star field — computed once, never re-rendered ───────────────── */
const STAR_DATA = Array.from({ length: 55 }, () => ({
  left:    `${Math.random() * 100}%`,
  top:     `${Math.random() * 100}%`,
  size:    Math.random() > 0.85 ? 2 : 1,
  opacity: Math.random() * 0.32 + 0.05,
  dur:     `${(2 + Math.random() * 4).toFixed(1)}s`,
  delay:   `${(Math.random() * 3).toFixed(1)}s`,
}));

function StableStars() {
  return (
    <div style={{ position:"absolute", inset:0, overflow:"hidden", pointerEvents:"none" }}>
      <style>{`
        @keyframes gmSkeletonPulse { 0%,100%{ opacity:1; } 50%{ opacity:0.4; } }
      `}</style>
      {STAR_DATA.map((s, i) => (
        <div key={i} style={{
          position: "absolute",
          left: s.left, top: s.top,
          width: s.size, height: s.size,
          borderRadius: "50%",
          background: "white",
          opacity: s.opacity,
          animation: `gmStarFade ${s.dur} ease ${s.delay} infinite`,
        }}/>
      ))}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   GREETING SCREEN
   First thing the user sees every session. Personalised, countdown-driven,
   tells them exactly what to do today. Judges see this in the first 5 seconds.
═══════════════════════════════════════════════════════════════════════════ */
function GreetingScreen({ user, onEnter }) {
  const username = user?.username || "";
  const keys     = K(username);

  const [readiness, setReadiness] = useState(null);
  const [weakArea,  setWeakArea]  = useState(null);
  const [fading,    setFading]    = useState(null);
  const [memTotal,  setMemTotal]  = useState(null);
  const [entering,  setEntering]  = useState(false);

  const interviewDate = lsGet(keys.idate, "");
  const target        = lsGet(keys.target, {});
  const plan          = lsGet(keys.plan, null);
  const planDone      = lsGet(keys.done, {});
  const days          = daysLeft(interviewDate);

  /* Today's topic from battle plan, else from weak areas */
  const todayEntry   = plan?.find(d => d.date === todayStr());
  const pendingToday = todayEntry?.tasks?.filter(t => !planDone[`${todayStr()}||${t.topic}`]) || [];
  const focusTopic   = pendingToday[0]?.topic || weakArea;

  useEffect(() => {
    if (!username) return;
    const token = localStorage.getItem("graphmind_token") || "";
    const hdr   = token ? { Authorization: `Bearer ${token}` } : {};

    fetch(`${API}/readiness/${username}`, { headers: hdr })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setReadiness(d); })
      .catch(() => {});

    fetch(`${API}/weak-areas/${username}`, { headers: hdr })
      .then(r => r.ok ? r.json() : null)
      .then(d => { const w = d?.weak_areas?.[0]; if (w) setWeakArea(w.topic); })
      .catch(() => {});

    fetch(`${API}/review/${username}`, { headers: hdr })
      .then(r => r.ok ? r.json() : null)
      .then(d => { const f = d?.review_topics?.[0]; if (f) setFading(f.content); })
      .catch(() => {});

    fetch(`${API}/graph-visuals/${username}`, { headers: hdr })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.nodes) {
          setMemTotal(d.nodes.filter(n => n.type === "Memory").length);
        }
      })
      .catch(() => {});
  }, [username]);

  const handleEnter = () => {
    setEntering(true);
    setTimeout(onEnter, 380);
  };

  const pct        = readiness?.readiness_pct ?? null;
  const topGap     = readiness?.gaps?.[0];
  const countColor = days === null ? "#4f8ef7"
    : days <= 3 ? "#f87171"
    : days <= 7 ? "#fbbf24"
    : "#34d399";

  /* Extract first name from email */
  const firstName   = username.split("@")[0].split(".")[0].replace(/[^a-zA-Z]/g, "");
  const displayName = firstName.charAt(0).toUpperCase() + firstName.slice(1);

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#07070e",
      display: "flex", alignItems: "center", justifyContent: "center",
      opacity: entering ? 0 : 1,
      transition: "opacity 0.38s ease",
      zIndex: 999,
      fontFamily: "inherit",
    }}>
      <style>{`
        @keyframes gmGreetIn  { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
        @keyframes gmStarFade { 0%,100%{ opacity:0.15; } 50%{ opacity:0.4; } }
      `}</style>

      {/* Stars — computed once in ref so they never flicker on re-render */}
      <StableStars />

      {/* Card */}
      <div style={{
        position: "relative", zIndex: 1,
        width: "100%", maxWidth: 440,
        padding: "0 28px",
        animation: "gmGreetIn 0.5s ease",
      }}>

        {/* Quote */}
        <div style={{
          fontSize: 11, color: "rgba(255,255,255,0.22)",
          fontStyle: "italic", textAlign: "center",
          marginBottom: 32, lineHeight: 1.7,
          letterSpacing: "0.01em",
        }}>
          "{dailyQuote()}"
        </div>

        {/* Greeting */}
        <div style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", marginBottom: 4, letterSpacing: "0.06em" }}>
          {greetWord()},
        </div>
        <div style={{
          fontSize: 36, fontWeight: 800, lineHeight: 1.05, marginBottom: 28,
          background: "linear-gradient(130deg, #ebebf5 30%, #4f8ef7)",
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
        }}>
          {displayName}.
        </div>

        {/* Countdown block */}
        {interviewDate ? (
          <div style={{
            padding: "16px 18px", borderRadius: 14, marginBottom: 12,
            background: `${countColor}0d`,
            border: `1px solid ${countColor}30`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div>
              <div style={{
                fontSize: 9, color: "rgba(255,255,255,0.3)",
                textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 5,
              }}>
                {target.company ? `${target.company} interview in` : "Interview in"}
              </div>
              <div style={{
                fontSize: 44, fontWeight: 900, fontFamily: "monospace",
                color: countColor, lineHeight: 1,
              }}>
                {days !== null && days <= 0 ? "Today" : days !== null ? `${days}d` : "—"}
              </div>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginTop: 5 }}>
                {days === null ? ""
                  : days <= 0 ? "Go get it 🔥"
                  : days <= 3 ? "Final sprint — every hour counts 🔥"
                  : days <= 7 ? "One week left — stay sharp"
                  : "Stay consistent, trust the process"}
              </div>
            </div>

            {/* Readiness ring */}
            {pct !== null && (
              <div style={{ textAlign: "center", flexShrink: 0 }}>
                <svg width="60" height="60" viewBox="0 0 60 60">
                  <circle cx="30" cy="30" r="24" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="5"/>
                  <circle cx="30" cy="30" r="24" fill="none"
                    stroke={pct >= 75 ? "#34d399" : pct >= 50 ? "#fbbf24" : "#f87171"}
                    strokeWidth="5"
                    strokeDasharray={`${(pct / 100) * 150.8} 150.8`}
                    strokeLinecap="round"
                    transform="rotate(-90 30 30)"
                    style={{ transition: "stroke-dasharray 1.2s ease" }}
                  />
                  <text x="30" y="35" textAnchor="middle" fontSize="14" fontWeight="800"
                    fontFamily="monospace"
                    fill={pct >= 75 ? "#34d399" : pct >= 50 ? "#fbbf24" : "#f87171"}>
                    {pct}
                  </text>
                </svg>
                <div style={{ fontSize: 8, color: "rgba(255,255,255,0.25)", marginTop: 3 }}>% ready</div>
              </div>
            )}
          </div>
        ) : (
          <div style={{
            padding: "12px 16px", borderRadius: 12, marginBottom: 12,
            background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.18)",
            fontSize: 11, color: "rgba(255,255,255,0.35)", lineHeight: 1.6,
          }}>
            📅 Set your interview date in the 🗓 Plan tab to activate the countdown.
          </div>
        )}

        {/* Today's focus */}
        <div style={{
          padding: "14px 16px", borderRadius: 14, marginBottom: 20,
          background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
        }}>
          <div style={{
            fontSize: 9, color: "rgba(255,255,255,0.25)",
            textTransform: "uppercase", letterSpacing: "0.12em", marginBottom: 10,
          }}>
            Today's focus
          </div>

          {focusTopic ? (
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                background: "rgba(79,142,247,0.12)", border: "1px solid rgba(79,142,247,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
              }}>🎯</div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#ebebf5", lineHeight: 1.3 }}>
                  {focusTopic}
                </div>
                <div style={{ fontSize: 10, color: "rgba(255,255,255,0.3)", marginTop: 3 }}>
                  {pendingToday.length > 1
                    ? `+${pendingToday.length - 1} more tasks in your battle plan today`
                    : pendingToday.length === 1
                    ? "From your battle plan"
                    : "Your top weak area right now"}
                </div>
              </div>
            </div>
          ) : fading ? (
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
              }}>⏱</div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#ebebf5", lineHeight: 1.3 }}>
                  {fading.length > 52 ? fading.slice(0, 52) + "…" : fading}
                </div>
                <div style={{ fontSize: 10, color: "#fbbf24", marginTop: 3 }}>
                  Fading from memory — review before it goes cold
                </div>
              </div>
            </div>
          ) : topGap ? (
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                background: "rgba(248,113,113,0.12)", border: "1px solid rgba(248,113,113,0.3)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
              }}>○</div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#ebebf5", lineHeight: 1.3 }}>
                  {topGap}
                </div>
                <div style={{ fontSize: 10, color: "#f87171", marginTop: 3 }}>
                  Top gap in your knowledge graph
                </div>
              </div>
            </div>
          ) : (
            /* Loading skeleton — pulses while API fetches */
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)",
                animation: "gmSkeletonPulse 1.4s ease infinite",
              }}/>
              <div style={{ flex: 1 }}>
                <div style={{
                  height: 14, borderRadius: 4, marginBottom: 6,
                  background: "rgba(255,255,255,0.06)",
                  animation: "gmSkeletonPulse 1.4s ease 0.1s infinite",
                  width: "70%",
                }}/>
                <div style={{
                  height: 10, borderRadius: 4,
                  background: "rgba(255,255,255,0.04)",
                  animation: "gmSkeletonPulse 1.4s ease 0.2s infinite",
                  width: "45%",
                }}/>
              </div>
            </div>
          )}
        </div>

        {/* Memory count pill */}
        {memTotal !== null && memTotal > 0 && (
          <div style={{
            display: "flex", gap: 8, justifyContent: "center",
            marginBottom: 16, flexWrap: "wrap",
          }}>
            <span style={{
              padding: "3px 10px", borderRadius: 20, fontSize: 10,
              background: "rgba(168,85,247,0.1)", border: "1px solid rgba(168,85,247,0.25)",
              color: "#a855f7",
            }}>🧠 {memTotal} memories</span>
            {pct !== null && (
              <span style={{
                padding: "3px 10px", borderRadius: 20, fontSize: 10,
                background: "rgba(79,142,247,0.1)", border: "1px solid rgba(79,142,247,0.25)",
                color: "#4f8ef7",
              }}>⚡ Hybrid RAG active</span>
            )}
            {readiness?.strengths?.length > 0 && (
              <span style={{
                padding: "3px 10px", borderRadius: 20, fontSize: 10,
                background: "rgba(52,211,153,0.1)", border: "1px solid rgba(52,211,153,0.25)",
                color: "#34d399",
              }}>✓ {readiness.strengths[0]} strong</span>
            )}
          </div>
        )}

        {/* CTA */}
        <button
          onClick={handleEnter}
          style={{
            width: "100%", padding: "15px",
            background: "linear-gradient(135deg, rgba(79,142,247,0.18), rgba(168,85,247,0.18))",
            border: "1px solid rgba(79,142,247,0.35)",
            borderRadius: 12, cursor: "pointer",
            color: "#ebebf5", fontSize: 15, fontWeight: 700,
            fontFamily: "inherit", letterSpacing: "0.02em",
            transition: "all 0.15s",
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = "linear-gradient(135deg, rgba(79,142,247,0.28), rgba(168,85,247,0.28))";
            e.currentTarget.style.borderColor = "rgba(79,142,247,0.6)";
            e.currentTarget.style.transform = "translateY(-1px)";
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = "linear-gradient(135deg, rgba(79,142,247,0.18), rgba(168,85,247,0.18))";
            e.currentTarget.style.borderColor = "rgba(79,142,247,0.35)";
            e.currentTarget.style.transform = "translateY(0)";
          }}
        >
          {focusTopic ? `Start with ${focusTopic} →` : "Start today's session →"}
        </button>

        <div style={{
          textAlign: "center", marginTop: 14,
          fontSize: 10, color: "rgba(255,255,255,0.1)",
          letterSpacing: "0.06em",
        }}>
          GRAPHMIND · HYBRID RAG · LONG-TERM MEMORY
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN APP
═══════════════════════════════════════════════════════════════════════════ */
function MainApp({ user, setUser }) {
  const [selectedNode,  setSelectedNode]  = useState(null);
  const [brainOpen,     setBrainOpen]     = useState(true);
  const [graphData,     setGraphData]     = useState({ nodes: [], links: [] });
  const [citedNodeIds,  setCitedNodeIds]  = useState([]);
  const [showGreeting,  setShowGreeting]  = useState(true);   // ← greeting screen
  const [stats,         setStats]         = useState({
    memories: 0, lastRetrievalMs: null, healthy: null, readinessPct: null
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

    const loadReadiness = async () => {
      try {
        const r = await fetch(`${API}/readiness/${user.username}`);
        if (r.ok) {
          const d = await r.json();
          setStats(s => ({ ...s, readinessPct: d.readiness_pct }));
        }
      } catch (_) {}
    };

    loadGraph();
    checkHealth();
    loadReadiness();

    // Poll graph every 30s to keep it live
    const poll = setInterval(loadGraph, 30000);
    return () => clearInterval(poll);
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem("graphmind_user");
    localStorage.removeItem("graphmind_token");
    setUser(null);
    navigate("/login");
  };

  const initials = user?.username
    ? user.username.slice(0, 2).toUpperCase()
    : "??";

  const memCount = graphData.nodes?.filter(n => n.type === "Memory").length || 0;
  const conCount = graphData.nodes?.filter(n => n.type === "Concept").length || 0;

  return (
    <>
      {/* Greeting screen — dismisses on CTA click */}
      {showGreeting && (
        <GreetingScreen
          user={user}
          onEnter={() => setShowGreeting(false)}
        />
      )}

      <div className="dashboard" style={{ opacity: showGreeting ? 0 : 1, transition: "opacity 0.3s ease 0.1s" }}>
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
            {stats.readinessPct != null && (
              <div style={{
                display: "flex", alignItems: "center", gap: 7,
                padding: "3px 10px", borderRadius: 20,
                background: stats.readinessPct >= 75
                  ? "rgba(52,211,153,0.12)" : stats.readinessPct >= 50
                  ? "rgba(251,191,36,0.12)" : "rgba(248,113,113,0.10)",
                border: `1px solid ${stats.readinessPct >= 75
                  ? "rgba(52,211,153,0.3)" : stats.readinessPct >= 50
                  ? "rgba(251,191,36,0.3)" : "rgba(248,113,113,0.3)"}`,
                fontSize: 11, fontFamily: "var(--mono)",
              }}>
                <svg width="22" height="22" viewBox="0 0 22 22">
                  <circle cx="11" cy="11" r="8" fill="none"
                    stroke="rgba(255,255,255,0.08)" strokeWidth="2.5"/>
                  <circle cx="11" cy="11" r="8" fill="none"
                    stroke={stats.readinessPct >= 75 ? "#34d399"
                      : stats.readinessPct >= 50 ? "#fbbf24" : "#f87171"}
                    strokeWidth="2.5"
                    strokeDasharray={`${(stats.readinessPct / 100) * 50.3} 50.3`}
                    strokeLinecap="round"
                    transform="rotate(-90 11 11)"
                    style={{ transition: "stroke-dasharray 0.8s ease" }}
                  />
                  <text x="11" y="14.5" textAnchor="middle"
                    fontSize="6" fontWeight="600" fontFamily="monospace"
                    fill={stats.readinessPct >= 75 ? "#34d399"
                      : stats.readinessPct >= 50 ? "#fbbf24" : "#f87171"}>
                    {stats.readinessPct}
                  </text>
                </svg>
                <span style={{ color: "var(--text-muted, #8888a4)" }}>interview ready</span>
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
                  <IntelligencePanel
                    skill={selectedNode}
                    username={user?.username}
                    onStartInterview={() => {
                      window.dispatchEvent(new CustomEvent("startInterview"));
                    }}
                  />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export default function App() {
  const [user, setUser] = useState(() => {
    const s = localStorage.getItem("graphmind_user");
    const t = localStorage.getItem("graphmind_token");
    if (s) {
      const u = JSON.parse(s);
      return { ...u, token: t || "" };
    }
    return null;
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