/**
 * SkillNode — 3D sphere node for the GraphMind mindmap.
 *
 * Colour logic:
 *   Memory nodes — colour interpolates from bright cyan (fresh, decay=1.0)
 *                  to dim red (stale, decay≈0) based on decay_score.
 *   Concept nodes — fixed teal.
 *   Cited nodes   — glowing gold ring (emissive intensity boosted).
 *
 * decay_score is provided by the backend's get_visual_graph() and reflects
 * e^(-lambda * days_since_last_reinforced).
 */

import React, { useRef } from "react";

function lerpHex(a, b, t) {
  const parse = (hex) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bv = Math.round(ab + (bb - ab) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bv
    .toString(16)
    .padStart(2, "0")}`;
}

const FRESH_COLOR = "#00ffff";   // bright cyan  — recently reinforced
const STALE_COLOR = "#ff3333";   // dim red       — decayed / stale
const CONCEPT_COLOR = "#1dd4a8"; // teal          — concept nodes
const CITED_COLOR = "#ffd700";   // gold          — cited in last response

function SkillNode({ skill, onClick, isCited = false }) {
  const meshRef = useRef();

  const decay = skill?.metadata?.decay_score ?? 1.0;
  const type  = skill?.type ?? "Memory";

  let color;
  let emissiveIntensity;
  let size;

  if (isCited) {
    color            = CITED_COLOR;
    emissiveIntensity = 3.5;
    size             = 0.45;
  } else if (type === "Concept") {
    color            = CONCEPT_COLOR;
    emissiveIntensity = 1.0;
    size             = 0.22;
  } else {
    // Memory node: interpolate by decay (0=stale red, 1=fresh cyan)
    color            = lerpHex(STALE_COLOR, FRESH_COLOR, Math.max(0, Math.min(1, decay)));
    emissiveIntensity = 1.0 + decay * 1.5;
    size             = 0.3 + decay * 0.1;
  }

  return (
    <mesh ref={meshRef} position={skill.position} onClick={onClick}>
      <sphereGeometry args={[size, 32, 32]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={emissiveIntensity}
        metalness={0.8}
        roughness={0.2}
      />
    </mesh>
  );
}

export default SkillNode;
