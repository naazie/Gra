import React, { useMemo } from "react";
import * as THREE from "three";

const REL_COLORS = {
  PREREQUISITE_OF: "#a855f7",
  REQUIRES:        "#a855f7",
  WEAK_IN:         "#f87171",
  STRONG_IN:       "#34d399",
  CONTRADICTS:     "#fbbf24",
  MENTIONS:        "rgba(255,255,255,0.18)",
  RELATED_TO:      "rgba(255,255,255,0.14)",
  LEARNING_GOAL:   "#4f8ef7",
  TARGETS_COMPANY: "#00e5ff",
  WORKED_ON:       "#1dd4a8",
  DEFAULT:         "rgba(255,255,255,0.12)",
};

function edgeColor(label) {
  if (!label) return REL_COLORS.DEFAULT;
  const key = Object.keys(REL_COLORS).find(k => label.toUpperCase().includes(k));
  return key ? REL_COLORS[key] : REL_COLORS.DEFAULT;
}

function hexToThree(hex) {
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) return new THREE.Color(0xffffff);
  return new THREE.Color(hex);
}

export default function Edges({ nodes, links }) {
  const lines = useMemo(() => {
    return links.map((link) => {
      const src = nodes.find(n => String(n.id) === String(link.source));
      const tgt = nodes.find(n => String(n.id) === String(link.target));
      if (!src || !tgt) return null;
      return {
        geometry: new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(...src.position),
          new THREE.Vector3(...tgt.position),
        ]),
        color: edgeColor(link.label),
        label: link.label,
        id: `${link.source}-${link.target}`,
      };
    }).filter(Boolean);
  }, [nodes, links]);

  return (
    <>
      {lines.map((line) => {
        const isSemantic = line.label && !["MENTIONS","DEFAULT"].includes(line.label);
        return (
          <line key={line.id} geometry={line.geometry}>
            <lineBasicMaterial
              color={hexToThree(line.color)}
              transparent
              opacity={isSemantic ? 0.55 : 0.22}
            />
          </line>
        );
      })}
    </>
  );
}
