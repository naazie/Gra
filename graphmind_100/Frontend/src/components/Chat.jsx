/**
 * GraphMind — Chat component v4.0
 * New in this version:
 *   - Calls setCitedNodeIds(ids) after every query response so cited
 *     memory nodes glow gold in the 3D mindmap (closes the UI auditability loop).
 *   - Passes setCitedNodeIds through the SSE streaming path as well.
 */

import React, { useState, useEffect, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";

const API_BASE_URL = "http://localhost:8000";

function MetricsBadge({ label, value, color }) {
  return (
    <span style={{
      display: "inline-block",
      background: color || "rgba(255,255,255,0.08)",
      borderRadius: "12px",
      padding: "2px 10px",
      fontSize: "11px",
      color: "#aaa",
      marginRight: "6px",
      marginTop: "3px",
    }}>
      {label}: <strong style={{ color: "#fff" }}>{value}</strong>
    </span>
  );
}

function CitationCard({ citation, index }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.05)",
      borderRadius: "8px",
      padding: "8px 10px",
      marginTop: "5px",
      borderLeft: "3px solid rgba(120,200,255,0.4)",
    }}>
      <div style={{ fontSize: "11px", color: "rgba(120,200,255,0.85)", marginBottom: "3px" }}>
        [{index + 1}] relevance: {citation.relevance_score}
        {citation.breakdown && (
          <span style={{ marginLeft: "8px", color: "#666" }}>
            vec: {citation.breakdown.cosine_sim?.toFixed(3)} |
            graph: {citation.breakdown.graph_score?.toFixed(3)} |
            w_v: {citation.breakdown.w_vector} |
            w_g: {citation.breakdown.w_graph}
          </span>
        )}
      </div>
      <div style={{ fontSize: "12px", color: "#bbb", lineHeight: 1.5 }}>
        {citation.snippet}
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const [showCitations, setShowCitations] = useState(false);

  return (
    <div className={`message-bubble ${msg.sender}`} style={{ maxWidth: "90%", marginBottom: "12px" }}>
      <div className="message-content" style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
        {msg.text}
      </div>

      {/* §1.2E — mandatory retrieval time display */}
      {msg.metrics && msg.metrics.retrieval_ms !== undefined && (
        <div style={{ marginTop: "8px", display: "flex", flexWrap: "wrap" }}>
          <MetricsBadge
            label="Retrieval completed in"
            value={`${msg.metrics.retrieval_ms}ms`}
            color="rgba(30,200,120,0.15)"
          />
          {msg.metrics.llm_ms !== undefined && (
            <MetricsBadge label="LLM" value={`${msg.metrics.llm_ms}ms`} />
          )}
          {msg.metrics.total_ms !== undefined && (
            <MetricsBadge label="Total" value={`${msg.metrics.total_ms}ms`} />
          )}
          {msg.type && (
            <MetricsBadge
              label="intent"
              value={msg.type}
              color={msg.type === "memory"
                ? "rgba(255,200,50,0.12)"
                : "rgba(80,160,255,0.12)"}
            />
          )}
        </div>
      )}

      {/* Entities extracted by intent classifier */}
      {msg.entities && msg.entities.length > 0 && (
        <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "4px" }}>
          {msg.entities.map((e, i) => (
            <span key={i} style={{
              background: "rgba(150,100,255,0.15)",
              color: "#c9a8ff",
              borderRadius: "10px",
              padding: "2px 8px",
              fontSize: "11px",
            }}>#{e}</span>
          ))}
        </div>
      )}

      {/* §1.7 contradiction alert */}
      {msg.conflict_alert && (
        <div style={{
          marginTop: "6px",
          background: "rgba(255,100,50,0.12)",
          borderRadius: "8px",
          padding: "6px 10px",
          fontSize: "12px",
          color: "#ffaa80",
        }}>
          ⚠️ {msg.conflict_alert}
        </div>
      )}

      {/* §1.6 auditability — memory citations */}
      {msg.citations && msg.citations.length > 0 && (
        <div style={{ marginTop: "6px" }}>
          <button
            onClick={() => setShowCitations(!showCitations)}
            style={{
              background: "none", border: "none",
              color: "rgba(120,200,255,0.7)",
              cursor: "pointer", fontSize: "11px", padding: 0,
            }}
          >
            {showCitations ? "▾ Hide" : "▸ Show"} {msg.citations.length} memory source{msg.citations.length !== 1 ? "s" : ""}
          </button>
          {showCitations && msg.citations.map((c, i) => (
            <CitationCard key={i} citation={c} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function Chat({ user, setGraphData, setCitedNodeIds }) {
  const [messages, setMessages]       = useState([{
    text: `Welcome back, ${user?.username || "Explorer"}! Tell me something new, or ask what I remember.`,
    sender: "ai",
  }]);
  const [input, setInput]             = useState("");
  const [isProcessing, setProcessing] = useState(false);
  const [streamMode, setStreamMode]   = useState(false);
  const messagesEndRef                = useRef(null);
  const streamMsgId                   = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const pushMsg = (msg) => setMessages((prev) => [...prev, msg]);

  const refreshGraph = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/recall/${user.username}`);
      if (res.ok) {
        const data = await res.json();
        if (setGraphData && data.graph_data) setGraphData(data.graph_data);
      }
    } catch (_) {}
  };

  // ── Standard (non-streaming) send ────────────────────────────────────────
  const sendStandard = async (userText) => {
    const res  = await fetch(
      `${API_BASE_URL}/chat?username=${encodeURIComponent(user.username)}&text=${encodeURIComponent(userText)}`,
      { method: "POST" }
    );
    const data = await res.json();

    // Highlight cited nodes in 3D graph
    const citedIds = (data.memory_citations || []).map((c) => c.node_id).filter(Boolean);
    if (setCitedNodeIds) setCitedNodeIds(citedIds);

    pushMsg({
      text:           data.answer || "(no response)",
      sender:         "ai",
      type:           data.type,
      citations:      data.memory_citations || [],
      entities:       data.entities         || [],
      conflict_alert: data.conflict_alert   || "",
      metrics: {
        retrieval_ms: data.retrieval_time_ms,
        llm_ms:       data.llm_generation_time_ms,
        total_ms:     data.total_time_ms,
      },
    });
  };

  // ── SSE Streaming send (§1.7) ─────────────────────────────────────────────
  const sendStreaming = async (userText) => {
    const res = await fetch(
      `${API_BASE_URL}/chat?username=${encodeURIComponent(user.username)}&text=${encodeURIComponent(userText)}&stream=true`,
      { method: "POST" }
    );

    const id = `stream-${Date.now()}`;
    streamMsgId.current = id;
    pushMsg({ id, text: "", sender: "ai", citations: [], entities: [], metrics: {} });

    const reader  = res.body.getReader();
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
          const payload = JSON.parse(line.slice(6));

          if (payload.type === "meta") {
            retrieval_ms = payload.retrieval_ms;
            citations    = payload.citations || [];
            entities     = payload.entities  || [];
            // Highlight cited nodes immediately when metadata arrives
            const citedIds = citations.map((c) => c.node_id).filter(Boolean);
            if (setCitedNodeIds) setCitedNodeIds(citedIds);

          } else if (payload.type === "token") {
            setMessages((prev) => prev.map((m) =>
              m.id === id ? { ...m, text: m.text + payload.content } : m
            ));

          } else if (payload.type === "done") {
            setMessages((prev) => prev.map((m) =>
              m.id === id ? {
                ...m, citations, entities,
                metrics: {
                  retrieval_ms,
                  llm_ms:   payload.generation_ms,
                  total_ms: payload.total_ms,
                },
              } : m
            ));

          } else if (payload.type === "error") {
            setMessages((prev) => prev.map((m) =>
              m.id === id ? { ...m, text: `Error: ${payload.message}`, sender: "error" } : m
            ));
          }
        } catch (_) {}
      }
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || !user || isProcessing) return;
    const userText = input;
    pushMsg({ text: userText, sender: "user" });
    setInput("");
    setProcessing(true);
    try {
      if (streamMode) await sendStreaming(userText);
      else            await sendStandard(userText);
      await refreshGraph();
    } catch (err) {
      pushMsg({ text: `Connection to GraphMind failed: ${err.message}`, sender: "error" });
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="chat-wrapper">
      <div className="stars-container">
        <Canvas camera={{ position: [0, 0, 1] }} style={{ width: "100%", height: "100%" }}>
          <Stars radius={100} depth={50} count={6000} factor={4} fade speed={2} />
        </Canvas>
      </div>

      <div className="messages-list">
        {messages.map((msg, i) => (
          <MessageBubble key={msg.id || i} msg={msg} />
        ))}
        {isProcessing && !streamMode && (
          <div className="message-bubble ai loading">
            <span className="dot">.</span><span className="dot">.</span><span className="dot">.</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <div style={{
          display: "flex", alignItems: "center", gap: "10px",
          padding: "6px 14px", fontSize: "12px", color: "#666",
          borderTop: "1px solid rgba(255,255,255,0.05)",
        }}>
          <label style={{
            display: "flex", alignItems: "center", gap: "5px",
            cursor: "pointer", color: streamMode ? "#78c8ff" : "#666",
          }}>
            <input
              type="checkbox"
              checked={streamMode}
              onChange={(e) => setStreamMode(e.target.checked)}
            />
            Streaming
          </label>
          <span style={{ color: "#333" }}>|</span>
          <span>GraphMind v4.0 · Hybrid RAG Memory Engine</span>
        </div>
        <div style={{ display: "flex", gap: "8px", padding: "0 12px 14px" }}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            placeholder="Tell me a fact, or ask what you know..."
            disabled={isProcessing}
          />
          <button onClick={sendMessage} disabled={isProcessing || !input.trim()}>
            {isProcessing ? "..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Chat;
