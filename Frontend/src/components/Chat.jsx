import React, { useState, useEffect, useRef, useCallback } from "react";
import CssStars from "./CssStars";

const API = "http://localhost:8000";

function MBadge({ cls, lbl, val }) {
  return (
    <span className={`mbadge ${cls}`}>
      <span className="lbl">{lbl}</span>
      <span className="v">{val}</span>
    </span>
  );
}

function CitationCard({ c, i }) {
  return (
    <div className="cite-card">
      <div className="cite-meta">
        [{i + 1}] score: {c.relevance_score}
        {c.breakdown && (
          <span className="bd">
            {" "}vec:{c.breakdown.cosine_sim?.toFixed(3)}
            {" "}graph:{c.breakdown.graph_score?.toFixed(3)}
            {" "}w_v:{c.breakdown.w_vector} w_g:{c.breakdown.w_graph}
          </span>
        )}
      </div>
      <div className="cite-text">{c.snippet || c.title}</div>
    </div>
  );
}

function Bubble({ msg }) {
  const [showCite, setShowCite] = useState(false);

  if (msg.sender === "loading") {
    return (
      <div className="message-bubble ai loading">
        <div className="loading-dots"><span /><span /><span /></div>
      </div>
    );
  }

  return (
    <div
      className={`message-bubble ${msg.sender}${msg.streaming ? " streaming" : ""}`}
      style={{ maxWidth: "90%" }}
    >
      <div className="message-content">{msg.text}</div>

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

      {msg.conflict && <div className="conflict-box">⚠ {msg.conflict}</div>}

      {msg.citations?.length > 0 && (
        <>
          <div className="cite-toggle" onClick={() => setShowCite(v => !v)}>
            {showCite ? "▾" : "▸"}{" "}
            {msg.citations.length} memory source{msg.citations.length > 1 ? "s" : ""}
          </div>
          {showCite && msg.citations.map((c, i) => <CitationCard key={i} c={c} i={i} />)}
        </>
      )}
    </div>
  );
}

export default function Chat({ user, setGraphData, setCitedNodeIds, setStats }) {
  const [messages,   setMessages]   = useState([{
    id: 0,
    text: `Welcome back, ${user?.username || "Explorer"}. Tell me something or ask what I remember.`,
    sender: "ai",
  }]);
  const [input,      setInput]      = useState("");
  const [processing, setProcessing] = useState(false);
  const [streaming,  setStreaming]  = useState(false);
  const abortRef  = useRef(null);
  const endRef    = useRef(null);
  const streamId  = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const refreshGraph = useCallback(async () => {
    try {
      const r = await fetch(`${API}/recall/${user.username}`);
      if (!r.ok) return;
      const d = await r.json();
      if (setGraphData && d.graph_data) setGraphData(d.graph_data);
      if (setStats) setStats(s => ({ ...s, memories: d.memory_count }));
    } catch (_) {}
  }, [user, setGraphData, setStats]);

  const push = (msg) =>
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), ...msg }]);

  const stopStream = () => {
    abortRef.current?.abort();
    setProcessing(false);
    setMessages(prev =>
      prev.map(m => m.id === streamId.current ? { ...m, streaming: false } : m)
    );
  };

  const sendStandard = async (text) => {
    const r = await fetch(
      `${API}/chat?username=${encodeURIComponent(user.username)}&text=${encodeURIComponent(text)}`,
      { method: "POST", signal: abortRef.current.signal }
    );
    const d = await r.json();
    setMessages(prev => prev.filter(m => m.sender !== "loading"));
    push({
      text:      d.answer || "(no response)",
      sender:    "ai",
      type:      d.type,
      citations: d.memory_citations || [],
      entities:  d.entities || [],
      conflict:  d.conflict_alert || "",
      metrics: {
        retrieval_ms: d.retrieval_time_ms,
        llm_ms:       d.llm_generation_time_ms,
      },
    });
    if (d.memory_citations?.length) {
      const ids = d.memory_citations.map(c => c.node_id).filter(Boolean);
      if (setCitedNodeIds) setCitedNodeIds(ids);
      if (setStats) setStats(s => ({ ...s, lastRetrievalMs: d.retrieval_time_ms }));
    }
  };

  const sendSSE = async (text) => {
    const r = await fetch(
      `${API}/chat?username=${encodeURIComponent(user.username)}&text=${encodeURIComponent(text)}&stream=true`,
      { method: "POST", signal: abortRef.current.signal }
    );
    const id = Date.now();
    streamId.current = id;
    setMessages(prev => [
      ...prev.filter(m => m.sender !== "loading"),
      { id, text: "", sender: "ai", streaming: true, citations: [], entities: [], metrics: {} },
    ]);

    const reader  = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let citations = [], entities = [], retrieval_ms = null;

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
            retrieval_ms = p.retrieval_ms;
            citations    = p.citations || [];
            entities     = p.entities  || [];
            if (setCitedNodeIds) setCitedNodeIds(citations.map(c => c.node_id).filter(Boolean));
            if (setStats) setStats(s => ({ ...s, lastRetrievalMs: p.retrieval_ms }));
          } else if (p.type === "token") {
            setMessages(prev =>
              prev.map(m => m.id === id ? { ...m, text: m.text + p.content } : m)
            );
          } else if (p.type === "done") {
            setMessages(prev =>
              prev.map(m => m.id === id ? {
                ...m, streaming: false, citations, entities,
                metrics: { retrieval_ms, llm_ms: p.generation_ms },
              } : m)
            );
          }
        } catch (_) {}
      }
    }
  };

  const send = async () => {
    if (!input.trim() || !user || processing) return;
    const text = input;
    push({ text, sender: "user" });
    setInput("");
    setProcessing(true);
    abortRef.current = new AbortController();
    if (!streaming) push({ sender: "loading" });
    try {
      if (streaming) await sendSSE(text);
      else           await sendStandard(text);
      await refreshGraph();
    } catch (e) {
      if (e.name !== "AbortError") {
        setMessages(prev => prev.filter(m => m.sender !== "loading"));
        push({ text: `Error: ${e.message}`, sender: "error" });
      }
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="chat-wrapper">
      {/* CSS stars — zero WebGL cost */}
      <CssStars count={55} opacity={0.4} />

      <div className="messages-list">
        {messages.map(m => <Bubble key={m.id} msg={m} />)}
        <div ref={endRef} />
      </div>

      <div className="input-area">
        <div className="input-opts">
          <label
            className={`stream-lbl${streaming ? " on" : ""}`}
            onClick={() => setStreaming(v => !v)}
          >
            <div className={`pill-track${streaming ? " on" : ""}`} />
            Stream
          </label>
          <span style={{ color: "var(--text-dim)", fontSize: 11 }}>·</span>
          <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-dim)" }}>
            GraphMind v7 · Hybrid RAG
          </span>
        </div>
        <div className="input-row">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Tell me something, or ask what you know…"
            disabled={processing && !streaming}
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
