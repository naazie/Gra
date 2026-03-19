/**
 * GraphMind SkillNode v11
 *
 * Cited nodes: sequential gold pulse with staggered entrance delay
 * Memory nodes: decay colour + breathing animation
 * Concept nodes: fixed teal
 * CONFIRMS nodes: bright green flash on first render
 */
import React, { useRef, useEffect } from "react";
import { useFrame } from "@react-three/fiber";

function lerp(a, b, t) { return a + (b - a) * t; }

function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1,3),16)/255,
    parseInt(hex.slice(3,5),16)/255,
    parseInt(hex.slice(5,7),16)/255,
  ];
}

function lerpColor(a, b, t) {
  const [ar,ag,ab] = hexToRgb(a);
  const [br,bg,bb] = hexToRgb(b);
  const r = Math.round(lerp(ar,br,t)*255).toString(16).padStart(2,"0");
  const g = Math.round(lerp(ag,bg,t)*255).toString(16).padStart(2,"0");
  const bv= Math.round(lerp(ab,bb,t)*255).toString(16).padStart(2,"0");
  return `#${r}${g}${bv}`;
}

export default function SkillNode({ skill, onClick, isCited = false, citedIndex = 0 }) {
  const meshRef  = useRef();
  const glowRef  = useRef();
  const phaseRef = useRef(Math.random() * Math.PI * 2);
  // For sequential cited animation — each node lights up 300ms after previous
  const citedStartRef = useRef(null);

  const decay   = skill?.metadata?.decay_score ?? 1.0;
  const usage   = skill?.metadata?.usage_count  ?? 0;
  const type    = skill?.type ?? "Memory";

  // When isCited becomes true, record the time + stagger by index
  useEffect(() => {
    if (isCited) {
      // citedIndex * 300ms stagger — nodes light up one by one
      citedStartRef.current = performance.now() + citedIndex * 300;
    } else {
      citedStartRef.current = null;
    }
  }, [isCited, citedIndex]);

  let baseColor;
  if (type === "Concept")    baseColor = "#1dd4a8";
  else                        baseColor = lerpColor("#ff3333", "#00e5ff", Math.max(0, Math.min(1, decay)));

  const baseSize = isCited
    ? 0.44
    : type === "Concept"
    ? 0.20
    : 0.28 + Math.min(usage * 0.02, 0.12) + decay * 0.06;

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const t   = clock.getElapsedTime() + phaseRef.current;
    const now = performance.now();

    if (isCited && citedStartRef.current !== null) {
      const elapsed = now - citedStartRef.current;

      if (elapsed < 0) {
        // Not yet — stay dim until stagger delay passes
        meshRef.current.scale.setScalar(0.3);
        meshRef.current.material.emissiveIntensity = 0.2;
        return;
      }

      // Entrance burst: scale from 0.3 → 1.6 → 1.0 in 600ms
      if (elapsed < 600) {
        const progress = elapsed / 600;
        const scale = progress < 0.5
          ? lerp(0.3, 1.6, progress * 2)
          : lerp(1.6, 1.0, (progress - 0.5) * 2);
        meshRef.current.scale.setScalar(scale);
        meshRef.current.material.emissiveIntensity = 4.0;
        meshRef.current.material.color.set("#ffd700");
        meshRef.current.material.emissive.set("#ffd700");
      } else {
        // Steady gold pulse after entrance
        const pulse = 1 + Math.sin(t * 3.5) * 0.12;
        meshRef.current.scale.setScalar(pulse);
        meshRef.current.material.emissiveIntensity = 2.5 + Math.sin(t * 3.5) * 1.0;
        meshRef.current.material.color.set("#fbbf24");
        meshRef.current.material.emissive.set("#fbbf24");
      }

      // Outer glow ring
      if (glowRef.current) {
        glowRef.current.scale.setScalar(1.6 + Math.sin(t * 2.0) * 0.2);
        glowRef.current.material.opacity = 0.06 + Math.sin(t * 2.0) * 0.04;
      }
      return;
    }

    // Non-cited
    if (glowRef.current) glowRef.current.scale.setScalar(0);

    if (type === "Concept") {
      meshRef.current.scale.setScalar(1 + Math.sin(t * 1.2) * 0.05);
      meshRef.current.material.color.set(baseColor);
      meshRef.current.material.emissive.set(baseColor);
      meshRef.current.material.emissiveIntensity = 1.0;
    } else {
      meshRef.current.scale.setScalar(1 + Math.sin(t * 0.9 + phaseRef.current) * 0.04);
      meshRef.current.material.color.set(baseColor);
      meshRef.current.material.emissive.set(baseColor);
      meshRef.current.material.emissiveIntensity = (0.8 + decay * 1.6) + Math.sin(t * 1.1) * 0.3;
    }
  });

  return (
    <group position={skill.position}>
      {/* Outer glow shell — only visible when cited */}
      <mesh ref={glowRef} scale={0}>
        <sphereGeometry args={[baseSize, 12, 12]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.08} />
      </mesh>

      <mesh ref={meshRef} onClick={onClick}>
        <sphereGeometry args={[baseSize, 32, 32]} />
        <meshStandardMaterial
          color={isCited ? "#fbbf24" : baseColor}
          emissive={isCited ? "#fbbf24" : baseColor}
          emissiveIntensity={isCited ? 3.0 : type === "Concept" ? 1.0 : 0.8 + decay * 1.6}
          metalness={isCited ? 0.9 : 0.7}
          roughness={isCited ? 0.1 : 0.25}
        />
      </mesh>
    </group>
  );
}
