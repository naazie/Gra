/**
 * GraphMind Edges v11 — animated semantic edges
 * CONTRADICTS: red pulsing dashed line (visible warning)
 * PREREQUISITE_OF/REQUIRES: purple solid
 * WEAK_IN: red dim
 * STRONG_IN: green
 * TARGETS_COMPANY: cyan
 * Default: white transparent
 */
import React, { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const REL_COLORS = {
  PREREQUISITE_OF: "#a855f7",
  REQUIRES:        "#a855f7",
  WEAK_IN:         "#f87171",
  STRONG_IN:       "#34d399",
  CONTRADICTS:     "#ff4444",
  MENTIONS:        "rgba(255,255,255,0.15)",
  RELATED_TO:      "rgba(255,255,255,0.12)",
  LEARNING_GOAL:   "#4f8ef7",
  TARGETS_COMPANY: "#00e5ff",
  WORKED_ON:       "#1dd4a8",
  CONFIRMS:        "#34d399",
  MISTAKE_IN:      "#f87171",
  DEFAULT:         "rgba(255,255,255,0.10)",
};

function edgeColor(label) {
  if (!label) return REL_COLORS.DEFAULT;
  const upper = label.toUpperCase();
  const key   = Object.keys(REL_COLORS).find(k => upper.includes(k));
  return key ? REL_COLORS[key] : REL_COLORS.DEFAULT;
}

function hexToThree(hex) {
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) return new THREE.Color(0xffffff);
  return new THREE.Color(hex);
}

// Animated CONTRADICTS edge — pulses red/gold
function ContradictsEdge({ src, tgt }) {
  const matRef  = useRef();
  const phaseRef = useRef(Math.random() * Math.PI * 2);

  const geometry = useMemo(() => {
    return new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(...src.position),
      new THREE.Vector3(...tgt.position),
    ]);
  }, [src, tgt]);

  useFrame(({ clock }) => {
    if (!matRef.current) return;
    const t = clock.getElapsedTime() + phaseRef.current;
    // Pulse between red and bright gold
    const pulse = (Math.sin(t * 2.5) + 1) / 2;  // 0..1
    const r = Math.round(255);
    const g = Math.round(pulse * 100);
    const b = 0;
    matRef.current.color.setRGB(r/255, g/255, b/255);
    matRef.current.opacity = 0.4 + pulse * 0.5;
  });

  return (
    <line geometry={geometry}>
      <lineBasicMaterial ref={matRef} color="#ff4444" transparent opacity={0.7} />
    </line>
  );
}

export default function Edges({ nodes, links }) {
  const contradicts = [];
  const regular     = [];

  links.forEach((link) => {
    const src = nodes.find(n => String(n.id) === String(link.source));
    const tgt = nodes.find(n => String(n.id) === String(link.target));
    if (!src || !tgt) return;
    const label = (link.label || "").toUpperCase();
    if (label.includes("CONTRADICTS")) {
      contradicts.push({ src, tgt, id: `${link.source}-${link.target}` });
    } else {
      regular.push({ src, tgt, label: link.label, id: `${link.source}-${link.target}` });
    }
  });

  const regularLines = useMemo(() => {
    return regular.map(({ src, tgt, label, id }) => ({
      geometry: new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(...src.position),
        new THREE.Vector3(...tgt.position),
      ]),
      color: edgeColor(label),
      label,
      id,
    }));
  }, [JSON.stringify(regular.map(r => r.id))]);

  return (
    <>
      {/* Regular semantic edges */}
      {regularLines.map((line) => {
        const isSemantic = line.label &&
          !["MENTIONS","DEFAULT","RELATED_TO"].includes(line.label.toUpperCase());
        return (
          <line key={line.id} geometry={line.geometry}>
            <lineBasicMaterial
              color={hexToThree(line.color)}
              transparent
              opacity={isSemantic ? 0.6 : 0.18}
            />
          </line>
        );
      })}

      {/* CONTRADICTS edges — animated red pulse */}
      {contradicts.map(({ src, tgt, id }) => (
        <ContradictsEdge key={id} src={src} tgt={tgt} />
      ))}
    </>
  );
}
