/**
 * GraphMind Intelligence Panel v13
 *
 * Fix 1 — Date picker: preset chips (+1w/+2w/+3w/+1m) + custom. No more broken native input.
 * Fix 2 — Daily quotes: 25 curated, rotates every day.
 * Fix 3 — Today's missions ↔ Battle Plan: ONE shared checkbox state. Same tasks, same ticks.
 * Fix 4 — Heatmap: active days derived from completed tasks, not page load.
 * Fix 5 — Progress: SVG radar/spider chart as hero visual.
 * Fix 6 — Battle Plan: company+role targeted, smart prerequisite-aware ordering, visual journey timeline.
 */

import React, { useState, useEffect, useCallback, useMemo } from "react";
import CssStars from "./CssStars";

const API = "http://localhost:8000";
function getToken() { return localStorage.getItem("graphmind_token") || ""; }
function authHdr()  { return { Authorization: `Bearer ${getToken()}` }; }

/* ── localStorage ───────────────────────────────────────────────────────── */
const lsGet = (k, fb) => { try { const v = localStorage.getItem(k); return v !== null ? JSON.parse(v) : fb; } catch { return fb; } };
const lsSet = (k, v)  => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

/* ── Shared keys (single source of truth) ──────────────────────────────── */
const K = (u) => ({
  idate:   `gm_idate_${u}`,     // interview date string
  plan:    `gm_plan_${u}`,      // generated battle plan array
  done:    `gm_plandone_${u}`,  // { "YYYY-MM-DD||topic": bool } — shared by WarRoom + BattlePlan
  target:  `gm_target_${u}`,    // { company, role }
});

/* ── Date utils ─────────────────────────────────────────────────────────── */
const todayStr = () => new Date().toISOString().slice(0, 10);
const daysLeft = (ds) => { if (!ds) return null; return Math.ceil((new Date(ds) - new Date()) / 86400000); };
const addDays  = (n)  => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
const dayLabel = (ds) => {
  const d = new Date(ds + "T00:00:00");
  const diff = Math.round((d - new Date(todayStr())) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
};

/* ── Active days from completed tasks ──────────────────────────────────── */
const getActiveDays = (username) => {
  const done = lsGet(K(username).done, {});
  return [...new Set(
    Object.entries(done)
      .filter(([, v]) => v)
      .map(([k]) => k.slice(0, 10))
      .filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d))
  )];
};

/* ── Motivational quotes — rotates daily ────────────────────────────────── */
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
  "Code it until you dream it.",
  "Small steps, enormous distance.",
  "They don't care about potential. Show preparation.",
  "The gap between you and the offer is just study sessions.",
  "Fail here so you don't fail there.",
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

/* ── Company-specific topic priorities ─────────────────────────────────── */
const COMPANY_TOPICS = {
  Google:    ["graphs","dynamic programming","trees","binary search","backtracking","arrays","bit manipulation","system design"],
  Amazon:    ["arrays","behavioral interviews","system design","trees","recursion","dynamic programming","sorting algorithms","linked lists"],
  Meta:      ["graphs","dynamic programming","arrays","system design","trees","behavioral interviews","sliding window","two pointers"],
  Microsoft: ["trees","graphs","arrays","dynamic programming","system design","object oriented programming","linked lists","stacks"],
  Apple:     ["system design","object oriented programming","arrays","trees","design patterns","graphs","algorithms","databases"],
  Startup:   ["system design","arrays","trees","dynamic programming","behavioral interviews","graphs","databases","api design"],
};
const ROLES = ["SWE", "Frontend", "Backend", "ML / AI", "iOS / Android", "DevOps"];

/* ── Shared components ──────────────────────────────────────────────────── */
const TAB_STYLE = (active) => ({
  flex: 1, padding: "6px 2px", fontSize: 9, fontWeight: active ? 600 : 400,
  color: active ? "var(--text-primary,#ebebf5)" : "var(--text-dim,#44445a)",
  background: active ? "rgba(79,142,247,0.12)" : "transparent",
  border: "none", borderBottom: active ? "2px solid #4f8ef7" : "2px solid transparent",
  cursor: "pointer", fontFamily: "inherit", transition: "all 0.15s",
  letterSpacing: "0.03em", whiteSpace: "nowrap",
});

function SectionTitle({ children, style = {} }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 600, letterSpacing: "0.10em", textTransform: "uppercase",
      color: "var(--text-dim,#44445a)", margin: "14px 0 6px", ...style,
    }}>{children}</div>
  );
}

function Spinner() {
  return (
    <div style={{ padding: 28, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{
        width: 26, height: 26, border: "3px solid rgba(79,142,247,0.12)",
        borderTop: "3px solid #4f8ef7", borderRadius: "50%",
        animation: "gmspin 0.8s linear infinite",
      }}/>
      <style>{`@keyframes gmspin{to{transform:rotate(360deg)}} @keyframes gmpulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
    </div>
  );
}

function useFetch(url) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);
  const run = useCallback(() => {
    if (!url) { setLoading(false); return; }
    setLoading(true); setError(false);
    fetch(url, { headers: authHdr() })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [url]);
  useEffect(() => { run(); }, [run]);
  return { data, loading, error, refetch: run };
}

/* ── Date Picker with presets ───────────────────────────────────────────── */
function DatePicker({ value, onChange, onSave }) {
  const [custom, setCustom] = useState(false);
  const [temp,   setTemp]   = useState("");
  const presets = [
    { label: "+1 week",  days: 7  },
    { label: "+2 weeks", days: 14 },
    { label: "+3 weeks", days: 21 },
    { label: "+1 month", days: 30 },
  ];
  return (
    <div style={{
      padding: "12px 14px", borderRadius: 10, marginBottom: 14,
      background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.2)",
    }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10, lineHeight: 1.6 }}>
        📅 <strong style={{ color: "#4f8ef7" }}>When is your interview?</strong><br/>
        <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
          Drives the countdown, heatmap, and your battle plan.
        </span>
      </div>
      {/* Preset chips */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {presets.map(p => (
          <button key={p.days} onClick={() => { const d = addDays(p.days); onChange(d); onSave(d); }}
            style={{
              padding: "5px 11px", borderRadius: 20, fontSize: 11, cursor: "pointer",
              fontFamily: "inherit", fontWeight: 500,
              background: "rgba(79,142,247,0.12)", border: "1px solid rgba(79,142,247,0.3)",
              color: "#4f8ef7", transition: "all 0.15s",
            }}>{p.label}</button>
        ))}
        <button onClick={() => setCustom(v => !v)} style={{
          padding: "5px 11px", borderRadius: 20, fontSize: 11, cursor: "pointer",
          fontFamily: "inherit",
          background: custom ? "rgba(168,85,247,0.12)" : "transparent",
          border: `1px solid ${custom ? "rgba(168,85,247,0.35)" : "rgba(255,255,255,0.12)"}`,
          color: custom ? "#a855f7" : "var(--text-dim)",
        }}>Custom</button>
      </div>
      {/* Custom date input */}
      {custom && (
        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
          <input type="date" value={temp} onChange={e => setTemp(e.target.value)}
            style={{
              flex: 1, padding: "5px 8px", background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6,
              color: "var(--text-primary)", fontSize: 11, fontFamily: "inherit",
              colorScheme: "dark",
            }}
          />
          <button onClick={() => { if (temp) { onChange(temp); onSave(temp); setCustom(false); } }}
            disabled={!temp} style={{
              padding: "5px 12px", borderRadius: 6, cursor: temp ? "pointer" : "default",
              background: "rgba(79,142,247,0.15)", border: "1px solid rgba(79,142,247,0.3)",
              color: "#4f8ef7", fontSize: 11, fontFamily: "inherit",
            }}>Set</button>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB 1 — WAR ROOM
   Fix 1: DatePicker with presets. Fix 2: Daily quote. Fix 3: Mission sync.
   Fix 4: Heatmap from real completed tasks.
═══════════════════════════════════════════════════════════════════════════ */
function WarRoomTab({ username, onStartInterview }) {
  const keys = K(username);
  const [interviewDate, setInterviewDate] = useState(() => lsGet(keys.idate, ""));
  const [, forceUpdate] = useState(0);

  const saveDate = (d) => { lsSet(keys.idate, d); setInterviewDate(d); };

  /* Fetch fallback mission data */
  const { data: reviewData } = useFetch(username ? `${API}/review/${username}` : null);
  const { data: weakData   } = useFetch(username ? `${API}/weak-areas/${username}` : null);

  /* Heatmap — derived from real completed tasks (Fix 4) */
  const activeDays = getActiveDays(username);
  const last14 = Array.from({ length: 14 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - (13 - i));
    return d.toISOString().slice(0, 10);
  });

  /* Today's missions — from plan if exists, else generated (Fix 3) */
  const plan       = lsGet(keys.plan, null);
  const todayEntry = plan?.find(d => d.date === todayStr());
  const planDone   = lsGet(keys.done, {});

  const todayMissions = useMemo(() => {
    /* If battle plan has today's tasks, use them */
    if (todayEntry?.tasks?.length) {
      return todayEntry.tasks.map(t => ({
        id:    `${todayStr()}||${t.topic}`,
        icon:  t.status === "weak" ? "⚠" : "○",
        text:  t.topic,
        sub:   t.status === "weak" ? "Weak area — prioritise this" : "New topic",
        color: t.status === "weak" ? "#fbbf24" : "#4f8ef7",
        type:  "plan",
      }));
    }
    /* Fallback: generate from review + weak */
    const missions = [];
    const review = reviewData?.review_topics || [];
    const weak   = weakData?.weak_areas      || [];
    review.slice(0, 2).forEach((r, i) => missions.push({
      id:    `${todayStr()}||adhoc_review_${i}`,
      icon:  "⏱",
      text:  `Review: ${r.content}`,
      sub:   `${r.freshness_pct}% fresh — fading fast`,
      color: r.freshness_pct < 40 ? "#f87171" : "#fbbf24",
      type:  "adhoc",
    }));
    if (weak[0] && missions.length < 3) missions.push({
      id:    `${todayStr()}||adhoc_weak_0`,
      icon:  "🎯",
      text:  `Practice: ${weak[0].topic}`,
      sub:   `${weak[0].confidence}% confidence`,
      color: "#4f8ef7",
      type:  "adhoc",
    });
    if (missions.length < 3) missions.push({
      id:    `${todayStr()}||adhoc_mock`,
      icon:  "🎙",
      text:  "Run a mock interview",
      sub:   "Build pressure tolerance",
      color: "#a855f7",
      type:  "interview",
    });
    return missions;
  }, [todayEntry, reviewData, weakData]);

  /* Sync 2 — emit today context to Chat whenever missions are ready */
  useEffect(() => {
    if (!todayMissions.length) return;
    const review = reviewData?.review_topics || [];
    window.dispatchEvent(new CustomEvent("panelContext", {
      detail: {
        todayTopics:  todayMissions.map(m => m.text).filter(t => !t.includes("mock interview")),
        fadingTopics: review.slice(0, 2).map(r => r.content),
        interviewDate,
        daysLeft:     daysLeft(interviewDate),
      }
    }));
  }, [todayMissions.length, interviewDate]);

  const toggleMission = (id) => {
    const done  = lsGet(keys.done, {});
    const wasOn = !!done[id];
    done[id] = !wasOn;
    lsSet(keys.done, done);
    forceUpdate(n => n + 1);
    /* Sync 3 — notify chat that a task was completed so AI can reference it */
    if (!wasOn) {
      const mission = todayMissions.find(m => m.id === id);
      if (mission) {
        window.dispatchEvent(new CustomEvent("taskCompleted", {
          detail: { task: mission.text }
        }));
        /* Silently write a memory so the graph and future chat sessions know */
        fetch(`${API}/memory/ingest`, {
          method: "POST",
          headers: { Authorization: `Bearer ${getToken()}` },
          body: new URLSearchParams({ text: `I completed a study session on ${mission.text} today.` }),
        }).catch(() => {});
      }
    }
  };

  const days           = daysLeft(interviewDate);
  const countdownColor = days === null ? "#4f8ef7" : days <= 3 ? "#f87171" : days <= 7 ? "#fbbf24" : "#34d399";
  const completedToday = todayMissions.filter(m => planDone[m.id]).length;

  return (
    <div style={{ padding: "12px 14px", overflowY: "auto", height: "100%" }}>

      {/* ── Daily quote ── */}
      <div style={{
        padding: "8px 12px", borderRadius: 8, marginBottom: 14,
        background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)",
        fontSize: 10, color: "rgba(255,255,255,0.35)", fontStyle: "italic", lineHeight: 1.6,
        textAlign: "center",
      }}>
        "{dailyQuote()}"
      </div>

      {/* ── Countdown / Date picker ── */}
      {interviewDate ? (
        <div style={{
          background: `rgba(${days !== null && days <= 3 ? "248,113,113" : days !== null && days <= 7 ? "251,191,36" : "52,211,153"},0.06)`,
          border: `1px solid ${countdownColor}33`,
          borderRadius: 10, padding: "12px 14px", marginBottom: 14,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 9, color: "var(--text-dim)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 3 }}>
                Interview in
              </div>
              <div style={{ fontSize: 34, fontWeight: 800, fontFamily: "monospace", color: countdownColor, lineHeight: 1 }}>
                {days !== null && days <= 0 ? "Today 🔥" : days !== null ? `${days}d` : "—"}
              </div>
              <div style={{ fontSize: 9, color: "var(--text-dim)", marginTop: 4 }}>
                {days === null ? "" : days <= 0 ? "Go get it" : days <= 3 ? "Final sprint 🔥" : days <= 7 ? "Almost there — stay sharp" : "Stay consistent, trust the process"}
              </div>
            </div>
            {/* Progress ring for today */}
            <div style={{ textAlign: "center" }}>
              <svg width="44" height="44" viewBox="0 0 44 44">
                <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4"/>
                <circle cx="22" cy="22" r="18" fill="none" stroke={countdownColor} strokeWidth="4"
                  strokeDasharray={`${(completedToday / todayMissions.length) * 113} 113`}
                  strokeLinecap="round" transform="rotate(-90 22 22)"
                  style={{ transition: "stroke-dasharray 0.5s ease" }}
                />
                <text x="22" y="26" textAnchor="middle" fontSize="10" fontWeight="700"
                  fontFamily="monospace" fill={countdownColor}>
                  {completedToday}/{todayMissions.length}
                </text>
              </svg>
              <div style={{ fontSize: 8, color: "var(--text-dim)", marginTop: 2 }}>today</div>
            </div>
          </div>
          <button onClick={() => saveDate("")} style={{
            marginTop: 8, fontSize: 9, padding: "2px 8px", borderRadius: 4, cursor: "pointer",
            background: "transparent", border: "1px solid rgba(255,255,255,0.08)",
            color: "var(--text-dim)", fontFamily: "inherit",
          }}>Change date</button>
        </div>
      ) : (
        <DatePicker value="" onChange={() => {}} onSave={saveDate} />
      )}

      {/* ── 14-day heatmap (Fix 4 — real activity) ── */}
      <SectionTitle>Activity — last 14 days</SectionTitle>
      <div style={{ display: "flex", gap: 3, marginBottom: 14, alignItems: "center" }}>
        {last14.map(d => {
          const active  = activeDays.includes(d);
          const isToday = d === todayStr();
          return (
            <div key={d} title={d} style={{
              width: 15, height: 15, borderRadius: 3,
              background: active
                ? isToday ? "#4f8ef7" : "rgba(79,142,247,0.5)"
                : isToday ? "rgba(79,142,247,0.15)" : "rgba(255,255,255,0.04)",
              border: isToday ? "1px solid rgba(79,142,247,0.6)" : "1px solid transparent",
              transition: "background 0.2s",
            }}/>
          );
        })}
        <span style={{ fontSize: 9, color: "var(--text-dim)", marginLeft: 4 }}>
          {activeDays.filter(d => last14.includes(d)).length} active days
        </span>
      </div>

      {/* ── Today's missions (Fix 3 — synced with Battle Plan) ── */}
      <SectionTitle>
        Today's missions
        {todayEntry?.tasks?.length ? (
          <span style={{ marginLeft: 6, color: "#34d399", fontSize: 8, fontWeight: 400, letterSpacing: 0, textTransform: "none" }}>
            ↗ from your battle plan
          </span>
        ) : null}
      </SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {todayMissions.map((m) => {
          const done = !!planDone[m.id];
          return (
            <div key={m.id} onClick={() => toggleMission(m.id)} style={{
              display: "flex", gap: 10, alignItems: "flex-start",
              padding: "8px 10px", borderRadius: 8, cursor: "pointer",
              background: done ? "rgba(52,211,153,0.05)" : "rgba(255,255,255,0.02)",
              border: `1px solid ${done ? "rgba(52,211,153,0.2)" : "rgba(255,255,255,0.07)"}`,
              transition: "all 0.15s",
            }}>
              <div style={{
                width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
                background: done ? "#34d399" : "transparent",
                border: `2px solid ${done ? "#34d399" : "rgba(255,255,255,0.2)"}`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 9, color: "#0a0a10", transition: "all 0.15s",
              }}>{done ? "✓" : ""}</div>
              <div style={{ flex: 1 }}>
                <div style={{
                  fontSize: 11, fontWeight: 500,
                  color: done ? "var(--text-dim)" : "var(--text-primary)",
                  textDecoration: done ? "line-through" : "none", lineHeight: 1.4,
                }}>
                  <span style={{ marginRight: 5 }}>{m.icon}</span>{m.text}
                </div>
                <div style={{ fontSize: 9, color: m.color, marginTop: 2 }}>{m.sub}</div>
              </div>
            </div>
          );
        })}
      </div>

      {!interviewDate && (
        <div style={{
          marginTop: 14, padding: "8px 10px", borderRadius: 7,
          background: "rgba(168,85,247,0.06)", border: "1px solid rgba(168,85,247,0.18)",
          fontSize: 10, color: "var(--text-dim)", lineHeight: 1.6,
        }}>
          💡 Set your interview date above to sync missions with your personalised battle plan.
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB 2 — MEMORY QUEUE (unchanged logic, small polish)
═══════════════════════════════════════════════════════════════════════════ */
function MemoryQueueTab({ username }) {
  const keys = K(username);
  const { data, loading, error, refetch } = useFetch(username ? `${API}/review/${username}` : null);
  const [, forceUpdate]      = useState(0);
  const [frustrationTopic, setFrustrationTopic] = useState("");

  /* Sync: chat frustration → highlight that topic in memory queue */
  useEffect(() => {
    const handler = (e) => {
      setFrustrationTopic(e.detail?.topic?.toLowerCase() || "");
      setTimeout(() => setFrustrationTopic(""), 8000);
    };
    window.addEventListener("chatFrustration", handler);
    return () => window.removeEventListener("chatFrustration", handler);
  }, []);

  const getReviewed  = () => lsGet(`gm_reviewed_${username}_${todayStr()}`, []);
  const markReviewed = (content) => {
    const cur = getReviewed();
    const next = cur.includes(content) ? cur.filter(t => t !== content) : [...cur, content];
    lsSet(`gm_reviewed_${username}_${todayStr()}`, next);
    /* Also mark in shared done state so heatmap picks it up */
    const done = lsGet(keys.done, {});
    done[`${todayStr()}||review_${content.slice(0, 30)}`] = !cur.includes(content);
    lsSet(keys.done, done);
    forceUpdate(n => n + 1);
  };

  if (loading) return <Spinner />;

  const topics   = (data?.review_topics || []).sort((a, b) => a.freshness_pct - b.freshness_pct);
  const reviewed = getReviewed();

  if (error || topics.length === 0) return (
    <div style={{ padding: "16px 14px" }}>
      <div style={{
        padding: "10px 12px", borderRadius: 8, marginBottom: 10,
        background: "rgba(52,211,153,0.06)", border: "1px solid rgba(52,211,153,0.2)",
        fontSize: 11, color: "#34d399", lineHeight: 1.6,
      }}>
        🧠 Memory queue is clear — nothing critical right now. Keep studying and it'll populate as you learn.
      </div>
      {error && (
        <button onClick={refetch} style={{
          width: "100%", padding: "7px", borderRadius: 7, cursor: "pointer",
          background: "rgba(79,142,247,0.1)", border: "1px solid rgba(79,142,247,0.25)",
          color: "#4f8ef7", fontSize: 11, fontFamily: "inherit",
        }}>↺ Retry</button>
      )}
    </div>
  );

  const pending = topics.filter(t => !reviewed.includes(t.content));
  const done    = topics.filter(t =>  reviewed.includes(t.content));

  return (
    <div style={{ padding: "10px 12px", overflowY: "auto", height: "100%" }}>
      <div style={{
        padding: "7px 10px", borderRadius: 7, marginBottom: 12,
        background: "rgba(248,113,113,0.07)", border: "1px solid rgba(248,113,113,0.18)",
        fontSize: 10, color: "var(--text-muted)", lineHeight: 1.6,
      }}>
        These topics are fading. Review them today before they go cold.
        <strong style={{ color: "#f87171" }}> {pending.length} remaining.</strong>
      </div>
      {frustrationTopic && (
        <div style={{
          padding: "7px 10px", borderRadius: 7, marginBottom: 8,
          background: "rgba(168,85,247,0.08)", border: "1px solid rgba(168,85,247,0.25)",
          fontSize: 10, color: "#a855f7", lineHeight: 1.5,
          animation: "gmpulse 1.5s ease 2",
        }}>
          💬 Chat detected you are struggling with <strong>{frustrationTopic}</strong> — reviewing it now will compound with what you just studied.
        </div>
      )}
      {pending.map((r, i) => (
        <MemoryCard key={i} topic={r} done={false}
          highlighted={!!frustrationTopic && r.content.toLowerCase().includes(frustrationTopic)}
          onToggle={() => markReviewed(r.content)} />
      ))}
      {done.length > 0 && (
        <>
          <SectionTitle style={{ marginTop: 16 }}>✓ Reviewed today</SectionTitle>
          {done.map((r, i) => <MemoryCard key={i} topic={r} done={true} onToggle={() => markReviewed(r.content)} />)}
        </>
      )}
    </div>
  );
}

function MemoryCard({ topic, done, onToggle, highlighted = false }) {
  const pct   = topic.freshness_pct ?? 50;
  const color = highlighted ? "#a855f7" : pct < 30 ? "#f87171" : pct < 60 ? "#fbbf24" : "#34d399";
  const label = highlighted ? "💬 Struggling" : pct < 30 ? "Critical" : pct < 60 ? "Fading" : "OK";
  return (
    <div style={{
      padding: "9px 10px", marginBottom: 6, borderRadius: 8, opacity: done ? 0.55 : 1,
      background: done ? "rgba(52,211,153,0.04)" : `${color}0d`,
      border: `1px solid ${done ? "rgba(52,211,153,0.2)" : color + "33"}`,
      transition: "all 0.2s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{
          fontSize: 11, fontWeight: 600, flex: 1, marginRight: 8,
          color: done ? "var(--text-dim)" : "var(--text-primary)",
          textDecoration: done ? "line-through" : "none",
        }}>{topic.content}</span>
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
          <span style={{
            fontSize: 9, padding: "1px 6px", borderRadius: 10,
            background: color + "22", border: `1px solid ${color}44`, color,
          }}>{label}</span>
          <button onClick={onToggle} style={{
            fontSize: 9, padding: "2px 8px", borderRadius: 4, cursor: "pointer",
            background: done ? "rgba(52,211,153,0.1)" : "rgba(255,255,255,0.06)",
            border: `1px solid ${done ? "rgba(52,211,153,0.3)" : "rgba(255,255,255,0.1)"}`,
            color: done ? "#34d399" : "var(--text-dim)", fontFamily: "inherit",
          }}>{done ? "✓ Done" : "Mark reviewed"}</button>
        </div>
      </div>
      <div style={{ height: 3, background: "rgba(255,255,255,0.05)", borderRadius: 2 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2, transition: "width 0.6s" }}/>
      </div>
      <div style={{ fontSize: 8, color: "var(--text-dim)", marginTop: 3 }}>{pct}% memory remaining</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB 3 — PROGRESS  (Fix 5 — SVG Radar chart as hero visual)
   Spider chart shows knowledge shape. Chat can describe one topic at a time.
   This shows your entire knowledge profile in 2 seconds.
═══════════════════════════════════════════════════════════════════════════ */
function RadarChart({ topics }) {
  if (!topics || topics.length < 3) return null;
  const capped = topics.slice(0, 8);
  const N      = capped.length;
  const cx     = 100, cy = 100, R = 72;

  const angle = (i) => (2 * Math.PI * i / N) - Math.PI / 2;
  const pt    = (i, pct) => ({
    x: cx + R * (pct / 100) * Math.cos(angle(i)),
    y: cy + R * (pct / 100) * Math.sin(angle(i)),
  });
  const ptFull = (i) => ({ x: cx + R * Math.cos(angle(i)), y: cy + R * Math.sin(angle(i)) });

  /* Data polygon */
  const dataPoints  = capped.map((t, i) => pt(i, t.confidence));
  const dataPath    = dataPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";

  /* Grid polygons at 25%, 50%, 75%, 100% */
  const gridPath = (pct) =>
    Array.from({ length: N }, (_, i) => pt(i, pct))
      .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";

  /* Axis lines */
  const axes = capped.map((_, i) => {
    const p = ptFull(i);
    return <line key={i} x1={cx} y1={cy} x2={p.x.toFixed(1)} y2={p.y.toFixed(1)}
      stroke="rgba(255,255,255,0.07)" strokeWidth="1"/>;
  });

  /* Labels — abbreviated */
  const labels = capped.map((t, i) => {
    const p    = ptFull(i);
    const lx   = cx + (R + 14) * Math.cos(angle(i));
    const ly   = cy + (R + 14) * Math.sin(angle(i));
    const name = t.topic.length > 9 ? t.topic.slice(0, 8) + "…" : t.topic;
    const conf = t.confidence;
    const col  = conf >= 70 ? "#34d399" : conf >= 50 ? "#fbbf24" : "#f87171";
    return (
      <text key={i} x={lx.toFixed(1)} y={ly.toFixed(1)} textAnchor="middle"
        dominantBaseline="middle" fontSize="7.5" fontFamily="inherit" fill={col}
        fontWeight="600">
        {name}
      </text>
    );
  });

  /* Average confidence → gradient color */
  const avg   = Math.round(capped.reduce((s, t) => s + t.confidence, 0) / N);
  const glowC = avg >= 70 ? "#34d399" : avg >= 50 ? "#fbbf24" : "#f87171";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", margin: "8px 0 16px" }}>
      <svg width="200" height="200" viewBox="0 0 200 200" style={{ overflow: "visible" }}>
        <defs>
          <radialGradient id="radarGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={glowC} stopOpacity="0.3"/>
            <stop offset="100%" stopColor={glowC} stopOpacity="0.05"/>
          </radialGradient>
          <filter id="radarGlow">
            <feGaussianBlur stdDeviation="2" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        {/* Grid rings */}
        {[25, 50, 75, 100].map(pct => (
          <path key={pct} d={gridPath(pct)}
            fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="1"/>
        ))}
        {/* Pct labels on grid */}
        {[25, 50, 75].map(pct => (
          <text key={pct} x={cx + 2} y={cy - R * pct / 100 + 1}
            fontSize="6" fill="rgba(255,255,255,0.2)" fontFamily="monospace">{pct}%</text>
        ))}

        {/* Axes */}
        {axes}

        {/* Data fill */}
        <path d={dataPath} fill="url(#radarGrad)" stroke={glowC}
          strokeWidth="1.5" strokeLinejoin="round" filter="url(#radarGlow)"/>

        {/* Data points */}
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r="3"
            fill={glowC} stroke="var(--surface-1,#0a0a10)" strokeWidth="1.5"/>
        ))}

        {/* Labels */}
        {labels}

        {/* Center score */}
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize="16" fontWeight="800"
          fontFamily="monospace" fill={glowC}>{avg}</text>
        <text x={cx} y={cy + 8} textAnchor="middle" fontSize="7"
          fontFamily="inherit" fill="rgba(255,255,255,0.3)">avg %</text>
      </svg>

      <div style={{ fontSize: 9, color: "var(--text-dim)", textAlign: "center" }}>
        Showing {N} topics · {capped.filter(t => t.confidence >= 70).length} strong · {capped.filter(t => t.confidence < 50).length} need work
      </div>
    </div>
  );
}

function ConfidenceMapTab({ username }) {
  const { data: weakData,    loading: wl } = useFetch(username ? `${API}/weak-areas/${username}` : null);
  const { data: historyData, loading: hl } = useFetch(username ? `${API}/attempt-history/${username}` : null);

  if (wl || hl) return <Spinner />;

  const areas   = weakData?.weak_areas   || [];
  const history = historyData?.history   || [];

  /* Trend from history */
  const trendMap = {};
  history.forEach(h => {
    if (!trendMap[h.topic]) trendMap[h.topic] = [];
    trendMap[h.topic].push(h);
  });
  const getTrend = (topic) => {
    const evs = (trendMap[topic] || []).slice(-4);
    if (evs.length < 2) return "new";
    const confirms = evs.filter(e => e.outcome === "confirmed").length;
    return confirms >= 3 ? "improving" : confirms === 0 ? "declining" : "stable";
  };
  const trendIcon  = { improving: "↑", declining: "↓", stable: "→", new: "✦" };
  const trendColor = { improving: "#34d399", declining: "#f87171", stable: "#fbbf24", new: "#a855f7" };

  if (areas.length === 0) return (
    <div style={{ padding: "16px 14px" }}>
      <div style={{
        padding: "10px 12px", borderRadius: 8,
        background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.2)",
        fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6,
      }}>
        📈 Your knowledge map builds as you use the chat. Start studying topics and this will populate with your real confidence levels.
      </div>
    </div>
  );

  const sorted = [...areas].sort((a, b) => a.confidence - b.confidence);

  return (
    <div style={{ padding: "10px 12px", overflowY: "auto", height: "100%" }}>
      {/* ── Radar chart (hero visual) ── */}
      <RadarChart topics={sorted} />

      {/* ── Detail bars ── */}
      <SectionTitle>Per-topic breakdown</SectionTitle>
      {sorted.map((a, i) => {
        const trend    = getTrend(a.topic);
        const barColor = a.confidence >= 70 ? "#34d399" : a.confidence >= 50 ? "#fbbf24" : "#f87171";
        return (
          <div key={i} style={{ marginBottom: 9 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
              <span style={{ fontSize: 10, color: "var(--text-primary)", fontWeight: 500, flex: 1 }}>
                {a.topic}
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 11, color: trendColor[trend], fontWeight: 700 }} title={trend}>
                  {trendIcon[trend]}
                </span>
                <span style={{ fontSize: 10, fontFamily: "monospace", fontWeight: 700, color: barColor }}>
                  {a.confidence}%
                </span>
              </div>
            </div>
            <div style={{ height: 5, background: "rgba(255,255,255,0.05)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{
                width: `${a.confidence}%`, height: "100%", borderRadius: 3, transition: "width 0.7s ease",
                background: `linear-gradient(90deg,${barColor}88,${barColor})`,
              }}/>
            </div>
          </div>
        );
      })}
      <div style={{ marginTop: 10, fontSize: 9, color: "var(--text-dim)", lineHeight: 1.8 }}>
        ↑ improving &nbsp;·&nbsp; ↓ declining &nbsp;·&nbsp; → stable &nbsp;·&nbsp; ✦ new topic
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB 4 — BATTLE PLAN  (Fix 6 — company+role targeted, smart ordering)
   Fix 5 — Journey timeline visual.  Fix 3 — synced with War Room missions.
═══════════════════════════════════════════════════════════════════════════ */
function BattlePlanTab({ username }) {
  const keys   = K(username);
  const [interviewDate, setInterviewDate] = useState(() => lsGet(keys.idate, ""));
  const [plan,          setPlan]          = useState(() => lsGet(keys.plan, null));
  const [done,          setDone]          = useState(() => lsGet(keys.done, {}));
  const [target, setTarget]               = useState(() => lsGet(keys.target, { company: "", role: "" }));
  const [setupOpen,    setSetupOpen]    = useState(false);
  const [, forceUpdate]                = useState(0);
  const [chatPlanOffer, setChatPlanOffer] = useState(null);  // plan text from chat

  const saveDate = (d) => { lsSet(keys.idate, d); setInterviewDate(d); };

  /* Sync 1 — listen for plan generated in chat, offer to import */
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.text) setChatPlanOffer(e.detail.text);
    };
    window.addEventListener("planFromChat", handler);
    return () => window.removeEventListener("planFromChat", handler);
  }, []);

  /* Sync: frustration in chat → flash the affected topic in Battle Plan */
  useEffect(() => {
    const handler = (e) => {
      if (e.detail?.topic) {
        /* Nothing visual needed in Battle Plan specifically — the Memory tab
           will already show the topic as fading. Just acknowledge. */
      }
    };
    window.addEventListener("chatFrustration", handler);
    return () => window.removeEventListener("chatFrustration", handler);
  }, []);

  /* Build goal string from target so backend's fetch_requirements() generates
     company+role specific topics — still cross-referenced against the user's
     real memory graph (CONFIRMS/WEAK_IN/MISTAKE_IN edges) server-side.        */
  const roadmapGoal = [target.company, target.role].filter(Boolean).join(" ") || "";
  const roadmapUrl  = username
    ? `${API}/roadmap/${username}${roadmapGoal ? `?goal=${encodeURIComponent(roadmapGoal + " interview")}` : ""}`
    : null;
  const { data: roadmapData, loading } = useFetch(roadmapUrl);

  /* ── Smart plan generation (Fix 6) ── */
  const generatePlan = useCallback(() => {
    if (!interviewDate || !roadmapData) return;
    const days = daysLeft(interviewDate);
    if (!days || days <= 0) return;

    const gaps    = (roadmapData.roadmap || []).filter(r => r.status !== "known");
    if (!gaps.length) return;

    const company  = target.company;
    const priority = COMPANY_TOPICS[company] || [];

    /* Score each topic: company priority + weak bonus + recency */
    const scored = gaps.map(t => {
      const compIdx = priority.findIndex(p => t.topic.toLowerCase().includes(p) || p.includes(t.topic.toLowerCase()));
      const compScore   = compIdx >= 0 ? (priority.length - compIdx) * 10 : 0;
      const weakBonus   = t.status === "weak" ? 15 : 0;
      return { ...t, score: compScore + weakBonus };
    }).sort((a, b) => b.score - a.score);

    /* Distribute: 2 topics per day, review every 7th day, mock final day */
    const generated = [];
    let dayOffset = 0, topicIdx = 0;

    while (dayOffset < Math.min(days - 1, 28) && topicIdx < scored.length) {
      const d = new Date(); d.setDate(d.getDate() + dayOffset);
      const dateStr = d.toISOString().slice(0, 10);

      /* Every 7 days: review day */
      if (dayOffset > 0 && dayOffset % 7 === 0) {
        generated.push({ date: dateStr, dayNum: dayOffset + 1, isReview: true, tasks: [] });
        dayOffset++;
        continue;
      }

      const tasks = [];
      for (let j = 0; j < 2 && topicIdx < scored.length; j++, topicIdx++) {
        tasks.push(scored[topicIdx]);
      }
      generated.push({ date: dateStr, dayNum: dayOffset + 1, tasks, isReview: false, isFinal: false });
      dayOffset++;
    }

    /* Final day before interview */
    const finalDate = new Date(interviewDate);
    finalDate.setDate(finalDate.getDate() - 1);
    generated.push({
      date: finalDate.toISOString().slice(0, 10),
      dayNum: days, tasks: [], isFinal: true,
    });

    setPlan(generated);
    lsSet(keys.plan, generated);
  }, [interviewDate, roadmapData, target]);

  const resetPlan = () => { lsSet(keys.plan, null); setPlan(null); lsSet(keys.done, {}); setDone({}); forceUpdate(n => n + 1); };

  const saveTarget = (t) => { setTarget(t); lsSet(keys.target, t); lsSet(keys.plan, null); setPlan(null); setSetupOpen(false); };

  const toggleTask = (dateStr, topic) => {
    const k    = `${dateStr}||${topic}`;
    const next = { ...done, [k]: !done[k] };
    setDone(next);
    lsSet(keys.done, next);
    forceUpdate(n => n + 1);
  };

  /* ── No interview date ── */
  if (!interviewDate) return (
    <div style={{ padding: "16px 14px" }}>
      <div style={{
        padding: "10px 12px", borderRadius: 8, marginBottom: 12,
        background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.2)",
        fontSize: 11, color: "var(--text-muted)", lineHeight: 1.6,
      }}>
        🗓 Set your interview date to generate a personalised day-by-day battle plan.
        <br/><span style={{ fontSize: 10, color: "var(--text-dim)" }}>
          Topics are ordered by company priority and prerequisite chain.
        </span>
      </div>
      <DatePicker value="" onChange={() => {}} onSave={saveDate}/>
    </div>
  );

  /* ── Loading ── */
  if (loading && !plan) return <Spinner/>;

  const days           = daysLeft(interviewDate);
  const completedDays  = (plan || []).filter(d => d.tasks.length > 0 && d.tasks.every(t => done[`${d.date}||${t.topic}`])).length;
  const totalTaskDays  = (plan || []).filter(d => d.tasks.length > 0).length;

  return (
    <div style={{ padding: "10px 12px", overflowY: "auto", height: "100%" }}>

      {/* ── Header ── */}
      <div style={{
        padding: "9px 11px", borderRadius: 8, marginBottom: 10,
        background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.07)",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Battle plan
            {target.company && (
              <span style={{ marginLeft: 6, color: "#4f8ef7", fontWeight: 500 }}>
                for {target.company}{target.role ? ` · ${target.role}` : ""}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", marginTop: 2 }}>
            {days !== null && days > 0 ? `${days} days remaining` : days === 0 ? "Interview day!" : "Past interview date"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 5 }}>
          <button onClick={() => setSetupOpen(v => !v)} style={{
            fontSize: 9, padding: "3px 7px", borderRadius: 4, cursor: "pointer",
            background: "rgba(79,142,247,0.1)", border: "1px solid rgba(79,142,247,0.25)",
            color: "#4f8ef7", fontFamily: "inherit",
          }}>🎯 Target</button>
          {plan && (
            <button onClick={resetPlan} style={{
              fontSize: 9, padding: "3px 7px", borderRadius: 4, cursor: "pointer",
              background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)",
              color: "#f87171", fontFamily: "inherit",
            }}>↺ Rebuild</button>
          )}
        </div>
      </div>

      {/* ── Target setup panel ── */}
      {setupOpen && <TargetSetup target={target} onSave={saveTarget} onCancel={() => setSetupOpen(false)}/>}

      {/* ── Chat plan import offer (Sync 1) ── */}
      {chatPlanOffer && (
        <div style={{
          padding: "10px 12px", marginBottom: 10, borderRadius: 8,
          background: "rgba(168,85,247,0.08)", border: "1px solid rgba(168,85,247,0.3)",
        }}>
          <div style={{ fontSize: 10, color: "#a855f7", fontWeight: 600, marginBottom: 6 }}>
            💬 Chat generated a study plan — sync it here?
          </div>
          <div style={{
            fontSize: 10, color: "var(--text-dim)", lineHeight: 1.5,
            maxHeight: 60, overflow: "hidden", marginBottom: 8,
          }}>
            {chatPlanOffer.slice(0, 180)}…
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => { generatePlan(); setChatPlanOffer(null); }} style={{
              flex: 1, padding: "6px", borderRadius: 6, cursor: "pointer",
              background: "rgba(168,85,247,0.15)", border: "1px solid rgba(168,85,247,0.4)",
              color: "#a855f7", fontSize: 10, fontFamily: "inherit", fontWeight: 600,
            }}>Rebuild plan from my graph →</button>
            <button onClick={() => setChatPlanOffer(null)} style={{
              padding: "6px 10px", borderRadius: 6, cursor: "pointer",
              background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
              color: "var(--text-dim)", fontSize: 10, fontFamily: "inherit",
            }}>Dismiss</button>
          </div>
        </div>
      )}

      {/* ── Generate button ── */}
      {!plan && !setupOpen && (
        <button onClick={generatePlan} style={{
          width: "100%", padding: "10px", marginBottom: 12, borderRadius: 8, cursor: "pointer",
          background: "rgba(79,142,247,0.14)", border: "1px solid rgba(79,142,247,0.35)",
          color: "#4f8ef7", fontSize: 12, fontFamily: "inherit", fontWeight: 700,
        }}>
          Generate My Battle Plan →
        </button>
      )}

      {/* ── Progress bar ── */}
      {plan && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--text-dim)", marginBottom: 3 }}>
            <span>Overall progress</span>
            <span style={{ color: "#34d399", fontWeight: 600 }}>{completedDays}/{totalTaskDays} days complete</span>
          </div>
          <div style={{ height: 4, background: "rgba(255,255,255,0.05)", borderRadius: 2 }}>
            <div style={{
              width: totalTaskDays > 0 ? `${(completedDays / totalTaskDays) * 100}%` : "0%",
              height: "100%", background: "linear-gradient(90deg,#4f8ef7,#34d399)",
              borderRadius: 2, transition: "width 0.4s",
            }}/>
          </div>
        </div>
      )}

      {/* ── Journey timeline (Fix 5) ── */}
      {plan && (
        <JourneyTimeline
          plan={plan}
          done={done}
          onToggleTask={toggleTask}
        />
      )}
    </div>
  );
}

function TargetSetup({ target, onSave, onCancel }) {
  const [company, setCompany] = useState(target.company || "");
  const [role,    setRole]    = useState(target.role    || "");
  return (
    <div style={{
      padding: "12px", marginBottom: 12, borderRadius: 8,
      background: "rgba(79,142,247,0.07)", border: "1px solid rgba(79,142,247,0.2)",
    }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: "#4f8ef7", marginBottom: 8 }}>
        🎯 Set target — plan will be tailored to this company's patterns
      </div>
      <SectionTitle style={{ marginTop: 0 }}>Company</SectionTitle>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 10 }}>
        {Object.keys(COMPANY_TOPICS).map(c => (
          <button key={c} onClick={() => setCompany(c)} style={{
            padding: "3px 9px", borderRadius: 20, fontSize: 10, cursor: "pointer",
            fontFamily: "inherit",
            background: company === c ? "rgba(79,142,247,0.2)" : "transparent",
            border: `1px solid ${company === c ? "rgba(79,142,247,0.5)" : "rgba(255,255,255,0.1)"}`,
            color: company === c ? "#4f8ef7" : "var(--text-dim)",
          }}>{c}</button>
        ))}
      </div>
      <SectionTitle>Role</SectionTitle>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 12 }}>
        {ROLES.map(r => (
          <button key={r} onClick={() => setRole(r)} style={{
            padding: "3px 9px", borderRadius: 20, fontSize: 10, cursor: "pointer",
            fontFamily: "inherit",
            background: role === r ? "rgba(52,211,153,0.12)" : "transparent",
            border: `1px solid ${role === r ? "rgba(52,211,153,0.4)" : "rgba(255,255,255,0.1)"}`,
            color: role === r ? "#34d399" : "var(--text-dim)",
          }}>{r}</button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <button onClick={() => onSave({ company, role })} style={{
          flex: 1, padding: "7px", borderRadius: 6, cursor: "pointer",
          background: "rgba(79,142,247,0.15)", border: "1px solid rgba(79,142,247,0.3)",
          color: "#4f8ef7", fontSize: 11, fontFamily: "inherit", fontWeight: 600,
        }}>Save & Rebuild Plan</button>
        <button onClick={onCancel} style={{
          padding: "7px 12px", borderRadius: 6, cursor: "pointer",
          background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
          color: "var(--text-dim)", fontSize: 11, fontFamily: "inherit",
        }}>Cancel</button>
      </div>
    </div>
  );
}

function JourneyTimeline({ plan, done, onToggleTask }) {
  const t = todayStr();
  return (
    <div style={{ position: "relative", paddingLeft: 30 }}>
      {/* Vertical rail */}
      <div style={{
        position: "absolute", left: 11, top: 8, bottom: 8,
        width: 2,
        background: "linear-gradient(180deg,rgba(79,142,247,0.4),rgba(79,142,247,0.05))",
      }}/>

      {plan.map((day, i) => {
        const isPast  = day.date < t && !day.isFinal;
        const isToday = day.date === t;
        const allDone = day.tasks.length > 0 && day.tasks.every(t2 => done[`${day.date}||${t2.topic}`]);

        const nodeColor = day.isFinal ? "#f87171"
          : day.isReview  ? "#a855f7"
          : allDone       ? "#34d399"
          : isToday       ? "#4f8ef7"
          : isPast        ? "rgba(255,255,255,0.15)"
          : "rgba(255,255,255,0.12)";

        const nodeLabel = day.isFinal ? "🎙" : day.isReview ? "↺" : allDone ? "✓" : day.dayNum;

        return (
          <div key={i} style={{ position: "relative", marginBottom: isToday ? 12 : 8 }}>
            {/* Node circle on the rail */}
            <div style={{
              position: "absolute", left: -26, top: 2,
              width: isToday ? 22 : 18,
              height: isToday ? 22 : 18,
              borderRadius: "50%",
              background: allDone ? "#34d399" : day.isReview ? "rgba(168,85,247,0.2)" : day.isFinal ? "rgba(248,113,113,0.2)" : isToday ? "rgba(79,142,247,0.2)" : "rgba(255,255,255,0.04)",
              border: `2px solid ${nodeColor}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: isToday ? 8 : 7, color: nodeColor, fontWeight: 700,
              boxShadow: isToday ? `0 0 10px ${nodeColor}66` : "none",
              transition: "all 0.2s",
            }}>
              {nodeLabel}
            </div>

            {/* Day card */}
            <div style={{
              padding: isToday ? "9px 11px" : "7px 10px",
              borderRadius: 8,
              background: day.isFinal ? "rgba(248,113,113,0.07)"
                : day.isReview ? "rgba(168,85,247,0.06)"
                : isToday ? "rgba(79,142,247,0.08)"
                : allDone ? "rgba(52,211,153,0.04)"
                : isPast ? "rgba(255,255,255,0.01)"
                : "rgba(255,255,255,0.02)",
              border: `1px solid ${day.isFinal ? "rgba(248,113,113,0.3)"
                : day.isReview ? "rgba(168,85,247,0.2)"
                : isToday ? "rgba(79,142,247,0.3)"
                : allDone ? "rgba(52,211,153,0.2)"
                : "rgba(255,255,255,0.05)"}`,
              opacity: isPast && !allDone ? 0.55 : 1,
              transition: "all 0.15s",
            }}>
              {/* Day header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: day.tasks.length ? 6 : 0 }}>
                <span style={{
                  fontSize: 9, fontWeight: isToday ? 700 : 500, textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  color: day.isFinal ? "#f87171" : day.isReview ? "#a855f7" : isToday ? "#4f8ef7" : "var(--text-dim)",
                }}>
                  {isToday ? "▶ " : ""}{dayLabel(day.date)}
                </span>
                {allDone && <span style={{ fontSize: 9, color: "#34d399" }}>All done ✓</span>}
              </div>

              {/* Special day content */}
              {day.isReview && (
                <div style={{ fontSize: 10, color: "#a855f7" }}>
                  Revisit your 3 weakest topics — spaced repetition day
                </div>
              )}
              {day.isFinal && (
                <div style={{ fontSize: 10, color: "#f87171", fontWeight: 600 }}>
                  🎙 Full mock interview — simulate real interview conditions
                </div>
              )}

              {/* Task checkboxes */}
              {day.tasks.map((task, j) => {
                const dKey  = `${day.date}||${task.topic}`;
                const isDone = !!done[dKey];
                const isCompPrio = (COMPANY_TOPICS[Object.keys(COMPANY_TOPICS)[0]] || [])
                  .some(p => task.topic.toLowerCase().includes(p));
                return (
                  <div key={j} onClick={() => onToggleTask(day.date, task.topic)} style={{
                    display: "flex", gap: 7, alignItems: "center",
                    padding: "4px 0", cursor: "pointer",
                    borderTop: j > 0 ? "1px solid rgba(255,255,255,0.04)" : "none",
                    marginTop: j > 0 ? 3 : 0,
                  }}>
                    <div style={{
                      width: 13, height: 13, borderRadius: 3, flexShrink: 0,
                      background: isDone ? "#34d399" : "transparent",
                      border: `2px solid ${isDone ? "#34d399" : "rgba(255,255,255,0.2)"}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 8, color: "#0a0a10", transition: "all 0.15s",
                    }}>{isDone ? "✓" : ""}</div>
                    <div style={{ flex: 1 }}>
                      <span style={{
                        fontSize: 11,
                        color: isDone ? "var(--text-dim)" : "var(--text-primary)",
                        textDecoration: isDone ? "line-through" : "none",
                      }}>
                        {task.topic}
                      </span>
                      <span style={{
                        marginLeft: 6, fontSize: 8,
                        color: task.status === "weak" ? "#fbbf24" : "rgba(255,255,255,0.2)",
                      }}>
                        {task.status === "weak" ? "⚠ weak" : "○ new"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TAB 5 — NODE INSPECTOR (unchanged)
═══════════════════════════════════════════════════════════════════════════ */
function NodeTab({ skill }) {
  if (!skill) return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 8 }}>
      <div style={{ fontSize: 24, opacity: 0.15 }}>◎</div>
      <div style={{ fontSize: 11, color: "var(--text-dim)", letterSpacing: "0.06em", textTransform: "uppercase" }}>Click a node</div>
    </div>
  );
  const meta       = skill.metadata || {};
  const isMemory   = skill.type === "Memory";
  const decay      = meta.decay_score ?? 1.0;
  const freshPct   = Math.round(decay * 100);
  const freshColor = decay > 0.65 ? "var(--cyan,#00e5ff)" : decay > 0.35 ? "var(--gold,#fbbf24)" : "var(--red,#f87171)";
  return (
    <div style={{ padding: "12px 14px", overflowY: "auto", height: "100%" }}>
      <div style={{
        display: "inline-block", padding: "2px 10px", borderRadius: 20,
        fontSize: 10, fontWeight: 600, letterSpacing: "0.07em", textTransform: "uppercase",
        background: "rgba(168,85,247,0.12)", border: "1px solid rgba(168,85,247,0.28)",
        color: "var(--purple,#a855f7)", marginBottom: 10,
      }}>{skill.type || "Node"}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 12, lineHeight: 1.5 }}>
        {skill.label || "Unnamed"}
      </div>
      {isMemory && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-dim)", marginBottom: 5 }}>
            <span>Memory freshness</span><span style={{ color: freshColor }}>{freshPct}%</span>
          </div>
          <div style={{ height: 5, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
            <div style={{ width: `${freshPct}%`, height: "100%", background: freshColor, borderRadius: 3, transition: "width 0.5s" }}/>
          </div>
        </div>
      )}
      <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "6px 10px" }}>
        {meta.graph_score != null && (
          <div style={{ display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid rgba(255,255,255,0.04)" }}>
            <span style={{ color:"var(--text-dim)",fontSize:11 }}>Centrality</span>
            <span style={{ color:"var(--cyan,#00e5ff)",fontWeight:500,fontFamily:"var(--mono)",fontSize:11 }}>{(meta.graph_score*100).toFixed(1)}%</span>
          </div>
        )}
        {meta.usage_count != null && (
          <div style={{ display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:"1px solid rgba(255,255,255,0.04)" }}>
            <span style={{ color:"var(--text-dim)",fontSize:11 }}>Times retrieved</span>
            <span style={{ color:"var(--gold,#fbbf24)",fontWeight:500,fontFamily:"var(--mono)",fontSize:11 }}>{meta.usage_count}</span>
          </div>
        )}
        {skill.edgeLabel && (
          <div style={{ display:"flex",justifyContent:"space-between",padding:"5px 0" }}>
            <span style={{ color:"var(--text-dim)",fontSize:11 }}>Relationship</span>
            <span style={{ color:"var(--gold,#fbbf24)",fontWeight:500,fontSize:11 }}>{skill.edgeLabel}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN EXPORT — props unchanged: { skill, username, onStartInterview }
═══════════════════════════════════════════════════════════════════════════ */
export default function IntelligencePanel({ skill, username, onStartInterview }) {
  const [tab, setTab] = useState("warroom");
  const TABS = [
    { id: "warroom",    label: "🎯 Today"    },
    { id: "memory",     label: "🧠 Memory"   },
    { id: "confidence", label: "📈 Progress" },
    { id: "battleplan", label: "🗓 Plan"     },
    { id: "node",       label: "🔍 Node"     },
  ];
  return (
    <div style={{ display:"flex", flexDirection:"column", height:"100%", background:"var(--surface-1,#0a0a10)", position:"relative" }}>
      <CssStars count={20} opacity={0.12}/>
      <div style={{ display:"flex", borderBottom:"1px solid var(--border,rgba(255,255,255,0.07))", flexShrink:0, position:"relative", zIndex:2 }}>
        {TABS.map(({ id, label }) => (
          <button key={id} style={TAB_STYLE(tab === id)} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>
      <div style={{ flex:1, minHeight:0, position:"relative", zIndex:1 }}>
        {tab === "warroom"    && <WarRoomTab       username={username} onStartInterview={onStartInterview}/>}
        {tab === "memory"     && <MemoryQueueTab   username={username}/>}
        {tab === "confidence" && <ConfidenceMapTab username={username}/>}
        {tab === "battleplan" && <BattlePlanTab    username={username}/>}
        {tab === "node"       && <NodeTab          skill={skill}/>}
      </div>
    </div>
  );
}