/**
 * GraphMind — Chat v10.1
 *
 * Merges v10.0 (god-tier) with onboarding MCQ card:
 *   - All v10 features preserved: JWT authHeaders, session continuity,
 *     file upload, interview mode, spaced-repetition review badge,
 *     corrections display, backtrack indicator, CitationCard why_retrieved,
 *     New Chat button, warm memory reaction, empty-Ollama hint.
 *   - Onboarding MCQ card: keyword-triggered PrereqOnboarding replaces
 *     free-form prereq questioning for interview-prep intents.
 *   - Bubble handles "onboarding" sender type, passes user + handlers.
 *   - onboarding state (onboardingId) co-exists with interviewMode state.
 *   - Onboarding bubbles excluded from session history persistence.
 *   - Onboarding suppressed when interviewMode is active.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import CssStars from "./CssStars";
import PrereqOnboarding from "./PrereqOnboarding";

const API         = "http://localhost:8000";
const MAX_HISTORY = 100;
const HIST_KEY    = (u, sid) => `gm_chat_${u}_${sid}`;
const SID_KEY     = (u)      => `gm_session_${u}`;

/* ── Panel sync helpers ───────────────────────────────────────────────────── */
function detectsPlan(text) {
  if (!text) return false;
  return [
    /day\s*\d+\s*[:\-]/i,
    /week\s*\d+/i,
    /study plan/i,
    /roadmap/i,
    /your plan for/i,
    /\d+\.\s+\w{3,}/,
  ].some(r => r.test(text));
}
function detectsFrustration(text) {
  if (!text) return false;
  return /(stuck|cannot|confused|struggling|frustrated|lost|no idea|help me|failing|don.t understand|can.t)/i.test(text);
}
function extractTopic(text) {
  if (!text) return "";
  const m = text.match(/(dynamic programming|dp|graphs?|trees?|binary search|arrays?|recursion|backtracking|system design|linked lists?|stacks?|heaps?|sorting|bfs|dfs)/i);
  return m ? m[1] : "";
}

/* ── Onboarding trigger keywords ─────────────────────────────────────────── */
const ONBOARDING_TRIGGERS = [
  /prepare.*interview/i,
  /interview.*prep/i,
  /google.*interview/i,
  /meta.*interview/i,
  /amazon.*interview/i,
  /microsoft.*interview/i,
  /crack.*interview/i,
  /get.*job/i,
  /study.*plan/i,
  /roadmap.*interview/i,
];

function needsOnboarding(text) {
  return ONBOARDING_TRIGGERS.some(re => re.test(text));
}

/* ── Auth ─────────────────────────────────────────────────────────────────── */
function getToken()    { return localStorage.getItem("graphmind_token") || ""; }
function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/* ── Session persistence ──────────────────────────────────────────────────── */
function loadHistory(u, sid) {
  try { const r = localStorage.getItem(HIST_KEY(u, sid)); return r ? JSON.parse(r) : null; }
  catch { return null; }
}
function saveHistory(u, sid, msgs) {
  try {
    // Never persist loading spinners or live onboarding cards
    const keep = msgs
      .filter(m => m.sender !== "loading" && m.sender !== "onboarding")
      .slice(-MAX_HISTORY);
    localStorage.setItem(HIST_KEY(u, sid), JSON.stringify(keep));
  } catch (_) {}
}

/* ── Citation card ────────────────────────────────────────────────────────── */
function CitationCard({ c, i }) {
  return (
    <div className="cite-card">
      <div className="cite-meta">
        [{i + 1}] {c.why_retrieved || `score: ${c.relevance_score}`}
      </div>
      {c.breakdown && (
        <div className="cite-meta" style={{ marginTop: 2, opacity: 0.6 }}>
          cosine:{c.breakdown.cosine_sim?.toFixed(3)}
          {" "}graph:{c.breakdown.graph_score?.toFixed(3)}
        </div>
      )}
      <div className="cite-text">{c.snippet || c.title || "(no preview)"}</div>
    </div>
  );
}

function MBadge({ cls, lbl, val }) {
  return (
    <span className={`mbadge ${cls}`}>
      <span className="lbl">{lbl}</span>
      <span className="v">{val}</span>
    </span>
  );
}

/* ── Bubble ───────────────────────────────────────────────────────────────── */
function Bubble({ msg, user, onOnboardingDone, onOnboardingSkip }) {
  const [showCite, setShowCite] = useState(false);

  if (msg.sender === "loading") {
    return (
      <div className="message-bubble ai loading">
        <div className="loading-dots"><span /><span /><span /></div>
      </div>
    );
  }

  /* Interactive onboarding MCQ card */
  if (msg.sender === "onboarding") {
    return (
      <div className="message-bubble ai" style={{ background: "none", border: "none", padding: 0 }}>
        <PrereqOnboarding
          username={user?.username}
          onDone={onOnboardingDone}
          onSkip={onOnboardingSkip}
        />
      </div>
    );
  }

  return (
    <div className={`message-bubble ${msg.sender}${msg.streaming ? " streaming" : ""}`}
         style={{ maxWidth: "90%" }}>

      <div className="message-content">
        {msg.text || (
          <span style={{ color: "var(--text-dim)", fontStyle: "italic" }}>
            (empty — check Ollama is running: <code>ollama serve</code>)
          </span>
        )}
      </div>

      {/* Auto-correction indicator */}
      {msg.corrections?.length > 0 && (
        <div style={{ marginTop: 5, fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--mono)" }}>
          ✏ Auto-corrected: {msg.corrections.slice(0, 2).join(", ")}
        </div>
      )}

      {/* Backtrack / prerequisite-check badge — only while the response is
          still streaming. Clears automatically when streaming ends. */}
      {msg.backtrack_active && msg.streaming && (
        <div style={{
          marginTop: 6, fontSize: 10, display: "inline-flex", alignItems: "center",
          gap: 4, padding: "2px 8px",
          background: "rgba(168,85,247,0.08)", border: "1px solid rgba(168,85,247,0.2)",
          borderRadius: 20, color: "var(--purple)", fontFamily: "var(--mono)",
        }}>
          ◎ checking prerequisites
        </div>
      )}

      {msg.metrics?.retrieval_ms !== undefined && (
        <div className="metrics-row">
          <MBadge cls="ret" lbl="Retrieval completed in" val={`${msg.metrics.retrieval_ms}ms`} />
          {msg.metrics.llm_ms != null && (
            <MBadge cls="llm" lbl="LLM" val={`${msg.metrics.llm_ms}ms`} />
          )}
          {msg.type && <MBadge cls="typ" lbl="intent" val={msg.type} />}
        </div>
      )}

      {msg.entities?.length > 0 && (
        <div className="entity-tags">
          {msg.entities.map((e, i) => <span key={i} className="etag">#{e}</span>)}
        </div>
      )}

      {!!msg.conflict && <div className="conflict-box">⚠ {msg.conflict}</div>}

      {msg.citations?.length > 0 && (
        <>
          <div className="cite-toggle" onClick={() => setShowCite(v => !v)}>
            {showCite ? "▾" : "▸"} {msg.citations.length} memor{msg.citations.length > 1 ? "ies" : "y"} used
          </div>
          {showCite && msg.citations.map((c, i) => <CitationCard key={i} c={c} i={i} />)}
        </>
      )}
    </div>
  );
}

/* ── Main Chat ────────────────────────────────────────────────────────────── */
export default function Chat({ user, setGraphData, setCitedNodeIds, setStats }) {
  const username = user?.username || "";

  const [sessionId, setSessionId] = useState(() =>
    localStorage.getItem(SID_KEY(username)) || crypto.randomUUID()
  );

  const [messages, setMessages] = useState(() => {
    const sid   = localStorage.getItem(SID_KEY(username)) || "";
    const saved = loadHistory(username, sid);
    if (saved?.length) return saved;
    return [{
      id:     0,
      text:   `Hey ${username || "there"} — what are you working on today?`,
      sender: "ai",
    }];
  });

  const [input,           setInput]          = useState("");
  const [processing,      setProcessing]     = useState(false);
  const [streaming,       setStreaming]       = useState(false);
  const [uploading,       setUploading]      = useState(false);
  const [interviewMode,   setInterviewMode]  = useState(false);
  const [interviewSessId, setInterviewSessId]= useState("");
  const [reviewSuggested, setReviewSuggested]= useState([]);
  const [onboardingId,    setOnboardingId]   = useState(null);
  const [panelContext,    setPanelContext]    = useState(null);
  const [syncFlash,       setSyncFlash]       = useState("");

  const abortRef = useRef(null);
  const endRef   = useRef(null);
  const streamId = useRef(null);
  const fileRef  = useRef(null);

  /* Persist history */
  useEffect(() => {
    if (username && sessionId) saveHistory(username, sessionId, messages);
  }, [messages, username, sessionId]);

  useEffect(() => {
    if (username && sessionId)
      localStorage.setItem(SID_KEY(username), sessionId);
  }, [username, sessionId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  /* Listen for startInterview event from IntelligencePanel */
  useEffect(() => {
    const handler = () => { startInterview("", "coding"); };
    window.addEventListener("startInterview", handler);
    return () => window.removeEventListener("startInterview", handler);
  }, []);

  /* Sync 2 — Panel → Chat: receive today context from IntelligencePanel */
  useEffect(() => {
    const handler = (e) => {
      setPanelContext(e.detail || null);
    };
    window.addEventListener("panelContext", handler);
    return () => window.removeEventListener("panelContext", handler);
  }, []);

  /* Sync: receive "task completed" flash confirmation from panel */
  useEffect(() => {
    const handler = (e) => {
      setSyncFlash(e.detail?.task || "task");
      setTimeout(() => setSyncFlash(""), 3000);
    };
    window.addEventListener("taskCompleted", handler);
    return () => window.removeEventListener("taskCompleted", handler);
  }, []);

  const refreshGraph = useCallback(async () => {
    try {
      const r = await fetch(`${API}/recall/${username}`, { headers: authHeaders() });
      if (!r.ok) return;
      const d = await r.json();
      if (setGraphData && d.graph_data) setGraphData(d.graph_data);
      if (setStats) setStats(s => ({ ...s, memories: d.memory_count }));
    } catch (_) {}
  }, [username, setGraphData, setStats]);

  const push = (msg) =>
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), ...msg }]);

  /* ── Onboarding handlers ──────────────────────────────────────────────── */
  const handleOnboardingDone = useCallback((summary) => {
    setMessages(prev => prev.map(m =>
      m.id === onboardingId
        ? { ...m, sender: "ai", text: summary }
        : m
    ));
    setOnboardingId(null);
    refreshGraph();
  }, [onboardingId, refreshGraph]);

  const handleOnboardingSkip = useCallback(() => {
    setMessages(prev => prev.map(m =>
      m.id === onboardingId
        ? { ...m, sender: "ai", text: "No problem — just tell me what you'd like to work on and we'll get started." }
        : m
    ));
    setOnboardingId(null);
  }, [onboardingId]);

  /* ── New Chat ─────────────────────────────────────────────────────────── */
  const newChat = async () => {
    try {
      const r = await fetch(`${API}/chat/new`, {
        method: "POST",
        headers: authHeaders(),
      });
      const d   = r.ok ? await r.json() : {};
      const sid = d.session_id || crypto.randomUUID();
      setSessionId(sid);
      setMessages([{ id: 0, text: "Fresh start — what do you want to work on?", sender: "ai" }]);
    } catch {
      const sid = crypto.randomUUID();
      setSessionId(sid);
      setMessages([{ id: 0, text: "New conversation started.", sender: "ai" }]);
    }
    setOnboardingId(null);
  };

  /* ── Stop stream ──────────────────────────────────────────────────────── */
  const stopStream = () => {
    abortRef.current?.abort();
    setProcessing(false);
    setMessages(prev =>
      prev.map(m => m.id === streamId.current ? { ...m, streaming: false } : m)
    );
  };

  /* ── File upload ──────────────────────────────────────────────────────── */
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    push({ text: `Uploading: ${file.name}…`, sender: "user" });
    try {
      const form = new FormData();
      form.append("username", username);
      form.append("file", file);
      const r = await fetch(`${API}/memory/file`, {
        method: "POST",
        headers: authHeaders(),
        body: form,
      });
      const d = await r.json();
      push({
        text:   d.message || (d.success ? `Got it — "${file.name}" is being processed.` : `Error: ${d.detail}`),
        sender: "ai",
      });
      await refreshGraph();
    } catch (err) {
      push({ text: `Upload failed: ${err.message}`, sender: "error" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  /* ── Standard (non-streaming) send ───────────────────────────────────── */
  const sendStandard = async (text) => {
    const r = await fetch(
      `${API}/chat?username=${encodeURIComponent(username)}&text=${encodeURIComponent(text)}&session_id=${sessionId}`,
      { method: "POST", headers: authHeaders(), signal: abortRef.current.signal }
    );
    const d = await r.json();
    setMessages(prev => prev.filter(m => m.sender !== "loading"));

    push({
      text:             d.answer?.trim() || "(empty — check Ollama)",
      sender:           "ai",
      type:             d.type,
      citations:        d.memory_citations || [],
      entities:         d.entities         || [],
      conflict:         d.conflict_alert   || "",
      corrections:      d.corrections      || [],
      backtrack_active: false,   // response complete — badge only shows during streaming
      metrics: {
        retrieval_ms: d.retrieval_time_ms,
        llm_ms:       d.llm_generation_time_ms,
      },
    });

    if (d.memory_citations?.length) {
      const ids = d.memory_citations.map(c => c.node_id).filter(Boolean);
      if (setCitedNodeIds) setCitedNodeIds(ids);
    }
    if (setStats && d.retrieval_time_ms != null)
      setStats(s => ({ ...s, lastRetrievalMs: d.retrieval_time_ms }));
    if (d.review_suggested?.length)
      setReviewSuggested(d.review_suggested);

    /* Sync 1 — detect plan in AI response → notify panel */
    const answer = d.answer || "";
    if (detectsPlan(answer)) {
      window.dispatchEvent(new CustomEvent("planFromChat", {
        detail: { text: answer, timestamp: Date.now() }
      }));
    }
    /* Sync: detect frustration in user text → notify panel to highlight topic */
    if (detectsFrustration(text)) {
      const topic = extractTopic(text);
      window.dispatchEvent(new CustomEvent("chatFrustration", { detail: { topic } }));
    }
  };

  /* ── SSE streaming send ───────────────────────────────────────────────── */
  const sendSSE = async (text) => {
    const r = await fetch(
      `${API}/chat?username=${encodeURIComponent(username)}&text=${encodeURIComponent(text)}&stream=true&session_id=${sessionId}`,
      { method: "POST", headers: authHeaders(), signal: abortRef.current.signal }
    );
    const id = Date.now();
    streamId.current = id;
    setMessages(prev => [
      ...prev.filter(m => m.sender !== "loading"),
      { id, text: "", sender: "ai", streaming: true, citations: [], entities: [], metrics: {}, corrections: [] },
    ]);

    const reader  = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let citations = [], entities = [], corrections = [], retrieval_ms = null, backtrack_active = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const p = JSON.parse(line.slice(6));
          if (p.type === "meta") {
            retrieval_ms     = p.retrieval_ms;
            citations        = p.citations        || [];
            entities         = p.entities         || [];
            corrections      = p.corrections      || [];
            backtrack_active = p.backtrack_active || false;
            if (setCitedNodeIds) setCitedNodeIds(citations.map(c => c.node_id).filter(Boolean));
            if (setStats) setStats(s => ({ ...s, lastRetrievalMs: p.retrieval_ms }));
          } else if (p.type === "token") {
            setMessages(prev =>
              prev.map(m => m.id === id ? { ...m, text: m.text + p.content } : m)
            );
          } else if (p.type === "done") {
            setMessages(prev => {
              const updated = prev.map(m => m.id === id ? {
                ...m, streaming: false, citations, entities, corrections, backtrack_active,
                metrics: { retrieval_ms, llm_ms: p.generation_ms },
              } : m);
              /* Sync 1 — detect plan in streamed response */
              const finalMsg = updated.find(m => m.id === id);
              if (finalMsg && detectsPlan(finalMsg.text)) {
                window.dispatchEvent(new CustomEvent("planFromChat", {
                  detail: { text: finalMsg.text, timestamp: Date.now() }
                }));
              }
              return updated;
            });
          }
        } catch (_) {}
      }
    }
  };

  /* ── Interview mode ───────────────────────────────────────────────────── */
  const startInterview = async (company = "", type = "coding") => {
    try {
      const r = await fetch(`${API}/interview/start`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ target_company: company, question_type: type }),
      });
      const d = await r.json();
      setInterviewMode(true);
      setInterviewSessId(d.session_id);
      push({
        text:   `🎙 Mock Interview Started${company ? ` — ${company}` : ""}\n\nInterviewer: ${d.question}`,
        sender: "ai",
      });
    } catch (e) {
      push({ text: `Failed to start interview: ${e.message}`, sender: "error" });
    }
  };

  const sendInterview = async (text) => {
    const r = await fetch(`${API}/interview/respond`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ session_id: interviewSessId, answer: text }),
      signal: abortRef.current.signal,
    });
    const d = await r.json();
    setMessages(prev => prev.filter(m => m.sender !== "loading"));

    let responseText = `Interviewer: ${d.response}`;
    if (d.misconception) responseText += `\n\n💡 Note: ${d.misconception}`;
    push({ text: responseText, sender: "ai", type: "interview" });

    if (d.is_done && d.scorecard) {
      const sc = d.scorecard;
      const scorecardText = [
        "━━ Interview Complete ━━\n",
        `Overall: ${sc.overall}/10 ${sc.would_pass ? "✓ Would pass" : "✗ Not yet"}\n`,
        `Problem solving: ${sc.problem_solving}/10\n`,
        `Communication: ${sc.communication}/10\n`,
        `Technical depth: ${sc.technical_depth}/10\n\n`,
        `Best moment: ${sc.strongest_moment}\n`,
        `Work on: ${sc.biggest_gap}\n`,
        `Next step: ${sc.next_steps}\n\n`,
        sc.summary,
      ].join("");
      push({ text: scorecardText, sender: "ai", type: "scorecard" });
      setInterviewMode(false);
      setInterviewSessId("");
      await refreshGraph();
    }
  };

  /* ── Main send dispatcher ─────────────────────────────────────────────── */
  const send = async () => {
    if (!input.trim() || !username || processing) return;
    const text = input;
    push({ text, sender: "user" });
    setInput("");

    /* Onboarding shortcut — only when not already in interview mode */
    if (needsOnboarding(text) && !onboardingId && !interviewMode) {
      const oid = Date.now() + 0.5;
      setOnboardingId(oid);
      push({ id: oid, sender: "onboarding", text: "" });
      return;
    }

    /* Sync: detect frustration before sending */
    if (detectsFrustration(text)) {
      const topic = extractTopic(text);
      window.dispatchEvent(new CustomEvent("chatFrustration", { detail: { topic } }));
    }

    /* Sync 2 — inject today context from panel as a hidden prefix so the AI
       knows what the student is currently working on without them having to say */
    let enrichedText = text;
    if (panelContext && !interviewMode) {
      const ctx = panelContext;
      const parts = [];
      if (ctx.todayTopics?.length)  parts.push(`Today I am working on: ${ctx.todayTopics.join(", ")}`);
      if (ctx.fadingTopics?.length) parts.push(`Topics fading in memory: ${ctx.fadingTopics.join(", ")}`);
      if (ctx.interviewDate)        parts.push(`Interview in ${ctx.daysLeft} days`);
      if (parts.length) enrichedText = `[${parts.join(' | ')}] ${text}`;
    }

    setProcessing(true);
    abortRef.current = new AbortController();
    if (!streaming) push({ sender: "loading" });
    try {
      if (interviewMode && interviewSessId) {
        await sendInterview(enrichedText);
      } else if (streaming) {
        await sendSSE(enrichedText);
      } else {
        await sendStandard(enrichedText);
        await refreshGraph();
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setMessages(prev => prev.filter(m => m.sender !== "loading"));
        push({ text: `Error: ${e.message}`, sender: "error" });
      }
    } finally {
      setProcessing(false);
    }
  };

  /* ── Render ───────────────────────────────────────────────────────────── */
  return (
    <div className="chat-wrapper">
      <CssStars count={55} opacity={0.35} />

      {/* Spaced repetition review badge */}
      {reviewSuggested.length > 0 && (
        <div style={{
          position: "relative", zIndex: 2,
          padding: "6px 16px", background: "rgba(251,191,36,0.08)",
          borderBottom: "1px solid rgba(251,191,36,0.2)",
          fontSize: 11, color: "var(--gold,#fbbf24)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <span>⏱ Due for review:</span>
          {reviewSuggested.map((t, i) => (
            <span key={i} style={{
              padding: "1px 7px", background: "rgba(251,191,36,0.12)",
              border: "1px solid rgba(251,191,36,0.3)", borderRadius: 20,
              fontSize: 10, cursor: "pointer",
            }} onClick={() => setInput(`Tell me about ${t}`)}>
              {t}
            </span>
          ))}
          <span style={{ marginLeft: "auto", cursor: "pointer", opacity: 0.5 }}
                onClick={() => setReviewSuggested([])}>✕</span>
        </div>
      )}

      {/* Sync flash — task completed confirmation from panel */}
      {syncFlash && (
        <div style={{
          position: "relative", zIndex: 2,
          padding: "5px 16px", background: "rgba(52,211,153,0.08)",
          borderBottom: "1px solid rgba(52,211,153,0.2)",
          fontSize: 10, color: "#34d399",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          ✓ Panel: marked <strong>{syncFlash}</strong> complete — I will take that into account
        </div>
      )}

      {/* Panel context banner — shows what today's plan is injecting */}
      {panelContext?.todayTopics?.length > 0 && (
        <div style={{
          position: "relative", zIndex: 2,
          padding: "5px 16px", background: "rgba(79,142,247,0.06)",
          borderBottom: "1px solid rgba(79,142,247,0.12)",
          fontSize: 10, color: "rgba(79,142,247,0.7)",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <span>🎯 Panel context active:</span>
          {panelContext.todayTopics.map((t, i) => (
            <span key={i} style={{
              padding: "1px 6px", background: "rgba(79,142,247,0.1)",
              border: "1px solid rgba(79,142,247,0.25)", borderRadius: 20, fontSize: 9,
            }}>{t}</span>
          ))}
          <span style={{ marginLeft: "auto", cursor: "pointer", opacity: 0.4, fontSize: 11 }}
                onClick={() => setPanelContext(null)}>✕</span>
        </div>
      )}

      <div className="messages-list">
        {messages.map(m => (
          <Bubble
            key={m.id}
            msg={m}
            user={user}
            onOnboardingDone={handleOnboardingDone}
            onOnboardingSkip={handleOnboardingSkip}
          />
        ))}
        <div ref={endRef} />
      </div>

      <div className="input-area">
        <div className="input-opts">
          <button onClick={newChat} disabled={processing} style={{
            background: "var(--surface-3,#22222c)", border: "1px solid var(--border,rgba(255,255,255,0.07))",
            borderRadius: 6, color: "var(--text-muted,#8888a4)", fontSize: 11,
            padding: "3px 10px", cursor: "pointer", fontFamily: "inherit",
          }}>+ New chat</button>

          <label className={`stream-lbl${streaming ? " on" : ""}`}
                 onClick={() => setStreaming(v => !v)}>
            <div className={`pill-track${streaming ? " on" : ""}`} />
            Stream
          </label>

          <span style={{ color: "var(--text-dim)", fontSize: 11 }}>·</span>

          <label style={{
            fontSize: 11, color: "var(--text-muted)", cursor: "pointer",
            fontFamily: "var(--mono)", padding: "2px 6px",
            border: "1px solid var(--border)", borderRadius: 4,
          }} title="Upload PDF, image, or text">
            {uploading ? "Uploading…" : "📎 File"}
            <input type="file" ref={fileRef} accept=".pdf,.png,.jpg,.jpeg,.txt,.md"
                   style={{ display: "none" }} onChange={handleFileUpload} disabled={uploading} />
          </label>

          <span style={{ color: "var(--text-dim)", fontSize: 11 }}>·</span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-dim)" }}>
            GraphMind v10 · Hybrid RAG
          </span>
        </div>

        <div className="input-row">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Tell me something, or ask what you know…"
            disabled={processing && !streaming}
            autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck="false"
          />
          {processing
            ? <button className="stop-btn" onClick={stopStream}>Stop</button>
            : <button className="send-btn" onClick={send} disabled={!input.trim()}>Send</button>
          }
        </div>
      </div>
    </div>
  );
}