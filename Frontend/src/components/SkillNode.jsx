import React, { useRef } from "react";
import { useFrame } from "@react-three/fiber";

function lerp(a, b, t) { return a + (b - a) * t; }

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3),16)/255;
  const g = parseInt(hex.slice(3,5),16)/255;
  const b = parseInt(hex.slice(5,7),16)/255;
  return [r, g, b];
}

function lerpColor(a, b, t) {
  const [ar,ag,ab] = hexToRgb(a);
  const [br,bg,bb] = hexToRgb(b);
  const r = Math.round(lerp(ar,br,t)*255).toString(16).padStart(2,"0");
  const g = Math.round(lerp(ag,bg,t)*255).toString(16).padStart(2,"0");
  const bv= Math.round(lerp(ab,bb,t)*255).toString(16).padStart(2,"0");
  return `#${r}${g}${bv}`;
}

export default function SkillNode({ skill, onClick, isCited = false }) {
  const meshRef  = useRef();
  const glowRef  = useRef();
  const phaseRef = useRef(Math.random() * Math.PI * 2);

  const decay   = skill?.metadata?.decay_score ?? 1.0;
  const usage   = skill?.metadata?.usage_count  ?? 0;
  const type    = skill?.type ?? "Memory";

  // base colour
  let baseColor;
  if (isCited)          baseColor = "#fbbf24";
  else if (type === "Concept") baseColor = "#1dd4a8";
  else                  baseColor = lerpColor("#ff3333", "#00e5ff", Math.max(0, Math.min(1, decay)));

  // base size
  const baseSize = isCited          ? 0.42
                 : type === "Concept" ? 0.20
                 : 0.28 + Math.min(usage * 0.02, 0.12) + decay * 0.06;

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const t = clock.getElapsedTime() + phaseRef.current;

    if (isCited) {
      // Gold pulse: rhythmic scale + emissive burst
      const pulse = 1 + Math.sin(t * 3.5) * 0.12;
      meshRef.current.scale.setScalar(pulse);
      meshRef.current.material.emissiveIntensity = 2.5 + Math.sin(t * 3.5) * 1.2;
    } else if (type === "Concept") {
      // Gentle float
      const s = 1 + Math.sin(t * 1.2) * 0.05;
      meshRef.current.scale.setScalar(s);
    } else {
      // Memory: float + slight emissive breathe based on decay
      const s = 1 + Math.sin(t * 0.9 + phaseRef.current) * 0.04;
      meshRef.current.scale.setScalar(s);
      meshRef.current.material.emissiveIntensity = (0.8 + decay * 1.6) + Math.sin(t * 1.1) * 0.3;
    }
  });

  const emissive = isCited ? 3.0 : type === "Concept" ? 1.0 : 0.8 + decay * 1.6;

  return (
    <group position={skill.position}>
      {/* Outer glow shell for cited nodes */}
      {isCited && (
        <mesh ref={glowRef} scale={1.8}>
          <sphereGeometry args={[baseSize, 16, 16]} />
          <meshBasicMaterial color="#fbbf24" transparent opacity={0.08} />
        </mesh>
      )}
      <mesh ref={meshRef} onClick={onClick}>
        <sphereGeometry args={[baseSize, 32, 32]} />
        <meshStandardMaterial
          color={baseColor}
          emissive={baseColor}
          emissiveIntensity={emissive}
          metalness={isCited ? 0.9 : 0.7}
          roughness={isCited ? 0.1 : 0.25}
          transparent={type === "Concept"}
          opacity={type === "Concept" ? 0.85 : 1.0}
        />
      </mesh>
    </group>
  );
}
