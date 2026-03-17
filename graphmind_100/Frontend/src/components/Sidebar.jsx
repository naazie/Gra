/**
 * GraphMind — Sidebar v4.0
 * Shows rich node metadata when a node is clicked in the 3D mindmap:
 *   - Node type (Memory / Concept)
 *   - Content snippet
 *   - decay_score with visual freshness bar
 *   - graph_score (centrality)
 *   - usage_count (how many times retrieved)
 *   - confidence_score
 *   - timestamp
 *   - relationship label (edge type, e.g. PREREQUISITE_OF)
 */

import React from "react";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";

function FreshnessBar({ value }) {
  const pct   = Math.round((value ?? 1) * 100);
  const color = value > 0.6 ? "#00ffcc"
              : value > 0.3 ? "#f0a500"
              : "#ff4444";
  return (
    <div style={{ marginTop: 4 }}>
      <div style={{
        background: "rgba(255,255,255,0.08)",
        borderRadius: 4,
        height: 6,
        width: "100%",
        overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: 4,
          transition: "width 0.4s ease",
        }} />
      </div>
      <div style={{ fontSize: 11, color, marginTop: 2 }}>{pct}% fresh</div>
    </div>
  );
}

function MetaRow({ label, value, color }) {
  if (value === undefined || value === null) return null;
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "5px 0",
      borderBottom: "1px solid rgba(255,255,255,0.06)",
      fontSize: 12,
    }}>
      <span style={{ color: "rgba(255,255,255,0.45)", fontSize: 11 }}>{label}</span>
      <span style={{ color: color || "#e6edf3", fontWeight: 500 }}>{value}</span>
    </div>
  );
}

function Sidebar({ skill }) {
  const starsEl = (
    <div className="stars-container">
      <Canvas camera={{ position: [0, 0, 1] }} style={{ width: "100%", height: "100%" }}>
        <Stars radius={100} depth={50} count={2000} factor={4} fade speed={2} />
      </Canvas>
    </div>
  );

  if (!skill) {
    return (
      <div className="sidebar" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        {starsEl}
        <div style={{ position: "relative", zIndex: 1, textAlign: "center", color: "rgba(255,255,255,0.35)", fontSize: 13 }}>
          <div style={{ fontSize: 28, marginBottom: 8 }}>🧠</div>
          Click a node to inspect its memory
        </div>
      </div>
    );
  }

  const meta    = skill.metadata || {};
  const isMemory = skill.type === "Memory";
  const typeColor = isMemory ? "#a78bfa" : "#1dd4a8";

  const decayVal     = meta.decay_score       ?? 1.0;
  const graphScore   = meta.graph_score       != null ? (meta.graph_score * 100).toFixed(1) + "%" : null;
  const confidence   = meta.confidence_score  != null ? (meta.confidence_score * 100).toFixed(0) + "%" : null;
  const usageCount   = meta.usage_count       != null ? meta.usage_count : null;
  const timestamp    = meta.timestamp
    ? new Date(meta.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : null;

  return (
    <div className="sidebar" style={{ overflowY: "auto" }}>
      {starsEl}
      <div style={{ position: "relative", zIndex: 1 }}>

        {/* Type badge */}
        <div style={{
          display: "inline-block",
          background: isMemory ? "rgba(167,139,250,0.15)" : "rgba(29,212,168,0.15)",
          color: typeColor,
          borderRadius: 20,
          padding: "2px 10px",
          fontSize: 11,
          fontWeight: 600,
          marginBottom: 8,
          letterSpacing: "0.05em",
        }}>
          {skill.type || "Node"}
        </div>

        {/* If it's an edge label */}
        {skill.label && skill.type !== "Memory" && skill.type !== "Concept" && (
          <div style={{
            background: "rgba(255,200,80,0.1)",
            color: "#ffd166",
            borderRadius: 6,
            padding: "4px 8px",
            fontSize: 11,
            marginBottom: 8,
          }}>
            ⟶ {skill.label}
          </div>
        )}

        {/* Label / content */}
        <h2 style={{
          fontSize: 14,
          fontWeight: 600,
          color: "#e6edf3",
          margin: "0 0 12px 0",
          lineHeight: 1.5,
          wordBreak: "break-word",
        }}>
          {skill.label || "Unnamed node"}
        </h2>

        {/* Freshness bar — only for Memory nodes */}
        {isMemory && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginBottom: 2 }}>Memory freshness</div>
            <FreshnessBar value={decayVal} />
          </div>
        )}

        {/* Metadata rows */}
        <div style={{
          background: "rgba(255,255,255,0.04)",
          borderRadius: 8,
          padding: "8px 12px",
          marginBottom: 10,
        }}>
          <MetaRow label="Graph centrality" value={graphScore}  color="#78c8ff" />
          <MetaRow label="Confidence"        value={confidence}  color="#a8e6cf" />
          <MetaRow label="Times retrieved"   value={usageCount !== null ? String(usageCount) : null} color="#ffd166" />
          <MetaRow label="Stored on"         value={timestamp}   color="rgba(255,255,255,0.55)" />
          {meta.uuid && (
            <MetaRow
              label="ID"
              value={meta.uuid.slice(0, 8) + "…"}
              color="rgba(255,255,255,0.3)"
            />
          )}
        </div>

        {/* Relationship label if edge was selected */}
        {skill.edgeLabel && (
          <div style={{
            background: "rgba(255,200,80,0.08)",
            border: "1px solid rgba(255,200,80,0.2)",
            borderRadius: 6,
            padding: "6px 10px",
            fontSize: 12,
            color: "#ffd166",
          }}>
            Relationship: <strong>{skill.edgeLabel}</strong>
          </div>
        )}

      </div>
    </div>
  );
}

export default Sidebar;
