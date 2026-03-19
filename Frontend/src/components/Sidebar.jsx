import React from "react";
import CssStars from "./CssStars";

function FreshnessBar({ value }) {
  const pct   = Math.round((value ?? 1) * 100);
  const color = value > 0.65 ? "var(--cyan)"
              : value > 0.35 ? "var(--gold)"
              : "var(--red)";
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: 10, color: "var(--text-dim)", marginBottom: 5,
        fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.06em",
      }}>
        <span>Memory freshness</span>
        <span style={{ color }}>{pct}%</span>
      </div>
      <div style={{ height: 5, background: "rgba(255,255,255,0.06)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{
          width: `${pct}%`, height: "100%", background: color,
          borderRadius: 3, transition: "width 0.5s ease",
        }} />
      </div>
    </div>
  );
}

function Row({ label, value, color }) {
  if (value == null || value === "") return null;
  return (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "center",
      padding: "5px 0", borderBottom: "1px solid rgba(255,255,255,0.04)", fontSize: 12,
    }}>
      <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{label}</span>
      <span style={{ color: color || "var(--text-muted)", fontWeight: 500, fontFamily: "var(--mono)", fontSize: 11 }}>
        {value}
      </span>
    </div>
  );
}

// Maps type name to a static rgba background + border colour string.
// Replaces color-mix() for full cross-browser compatibility.
const TYPE_STYLES = {
  Memory:  { bg: "rgba(168,85,247,0.12)",  border: "rgba(168,85,247,0.28)",  color: "var(--purple)" },
  Concept: { bg: "rgba(29,212,168,0.12)",  border: "rgba(29,212,168,0.28)",  color: "var(--teal)"   },
  default: { bg: "rgba(79,142,247,0.12)",  border: "rgba(79,142,247,0.28)",  color: "var(--blue)"   },
};

export default function Sidebar({ skill }) {
  if (!skill) {
    return (
      <div className="sidebar" style={{
        display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", gap: 8,
      }}>
        <CssStars count={30} opacity={0.2} />
        <div style={{ position: "relative", zIndex: 1, textAlign: "center" }}>
          <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.18 }}>◎</div>
          <div style={{
            fontSize: 11, color: "var(--text-dim)",
            letterSpacing: "0.06em", textTransform: "uppercase",
          }}>
            Click a node
          </div>
        </div>
      </div>
    );
  }

  const meta      = skill.metadata || {};
  const isMemory  = skill.type === "Memory";
  const typeStyle = TYPE_STYLES[skill.type] || TYPE_STYLES.default;

  const decay      = meta.decay_score       ?? 1.0;
  const graphScore = meta.graph_score       != null
    ? (meta.graph_score * 100).toFixed(1) + "%" : null;
  const conf       = meta.confidence_score  != null
    ? (meta.confidence_score * 100).toFixed(0) + "%" : null;
  const ts         = meta.timestamp
    ? new Date(meta.timestamp).toLocaleDateString(undefined, {
        month: "short", day: "numeric", year: "numeric",
      })
    : null;

  return (
    <div className="sidebar" style={{ overflowY: "auto" }}>
      <CssStars count={30} opacity={0.2} />
      <div style={{ position: "relative", zIndex: 1 }}>

        {/* Type pill — static rgba, no color-mix() */}
        <div style={{
          display: "inline-block",
          padding: "2px 10px", borderRadius: 20,
          fontSize: 10, fontWeight: 600, letterSpacing: "0.07em",
          textTransform: "uppercase",
          background: typeStyle.bg,
          border: `1px solid ${typeStyle.border}`,
          color: typeStyle.color,
          marginBottom: 10,
        }}>
          {skill.type || "Node"}
        </div>

        {/* Edge label */}
        {skill.edgeLabel && (
          <div style={{
            background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)",
            borderRadius: 6, padding: "3px 8px", fontSize: 10, color: "var(--gold)",
            fontFamily: "var(--mono)", marginBottom: 8,
          }}>
            ⟶ {skill.edgeLabel}
          </div>
        )}

        {/* Label */}
        <h2 style={{
          fontSize: 13, fontWeight: 600, color: "var(--text-primary)",
          margin: "0 0 14px", lineHeight: 1.5, wordBreak: "break-word",
        }}>
          {skill.label || "Unnamed"}
        </h2>

        {/* Freshness bar — Memory nodes only */}
        {isMemory && <FreshnessBar value={decay} />}

        {/* Metadata table */}
        <div style={{
          background: "rgba(255,255,255,0.03)", borderRadius: 8,
          padding: "6px 10px", marginBottom: 10,
        }}>
          <Row label="Centrality"      value={graphScore}  color="var(--cyan)"   />
          <Row label="Confidence"      value={conf}        color="var(--green)"  />
          <Row label="Times retrieved"
               value={meta.usage_count != null ? String(meta.usage_count) : null}
               color="var(--gold)" />
          <Row label="Stored"          value={ts}          color="var(--text-muted)" />
          <Row label="ID"
               value={meta.uuid ? meta.uuid.slice(0, 8) + "…" : null}
               color="var(--text-dim)" />
        </div>

        {/* Relationship type */}
        {skill.edgeLabel && (
          <div style={{
            background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.18)",
            borderRadius: 6, padding: "6px 10px", fontSize: 11, color: "var(--gold)",
          }}>
            <span style={{ color: "var(--text-dim)", marginRight: 6 }}>Relationship:</span>
            <strong>{skill.edgeLabel}</strong>
          </div>
        )}
      </div>
    </div>
  );
}
