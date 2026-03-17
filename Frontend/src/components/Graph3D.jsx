import React from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import SkillNode from "./SkillNode";
import Edges from "./Edges";

export default function Graph3D({ graphData, onSelectNode, citedNodeIds = [] }) {
  const { nodes = [], links = [] } = graphData || {};

  const citedSet = new Set(
    citedNodeIds.flatMap(id => [String(id)])
  );

  const isCited = (node) =>
    citedSet.has(String(node.id)) ||
    citedSet.has(String(node?.metadata?.uuid));

  return (
    <div style={{ flex: 1, height: "100%", position: "relative" }}>
      <Canvas
        camera={{ position: [0, 0, 16], fov: 58 }}
        gl={{ antialias: true, alpha: true }}
      >
        {/* Atmosphere */}
        <fog attach="fog" args={["#000000", 18, 45]} />
        <ambientLight intensity={0.25} />
        <pointLight position={[10, 10, 10]}  intensity={0.8} color="#4f8ef7" />
        <pointLight position={[-10, -8, -6]} intensity={0.5} color="#a855f7" />
        <pointLight position={[0, -12, 8]}   intensity={0.3} color="#00e5ff" />

        {/* Background stars */}
        <Stars radius={120} depth={60} count={3500} factor={4} fade speed={0.8} saturation={0.1} />

        {/* Edges rendered first (behind nodes) */}
        <Edges nodes={nodes} links={links} />

        {/* Nodes */}
        {nodes.map((node) => (
          <SkillNode
            key={node.id}
            skill={node}
            onClick={() => onSelectNode && onSelectNode(node)}
            isCited={isCited(node)}
          />
        ))}

        <OrbitControls
          enableZoom
          enableRotate
          enableDamping
          dampingFactor={0.06}
          rotateSpeed={0.5}
          minDistance={4}
          maxDistance={40}
        />
      </Canvas>

      {/* Empty state overlay */}
      {nodes.length === 0 && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          pointerEvents: "none", gap: 8,
        }}>
          <div style={{ fontSize: 32, opacity: 0.15 }}>🧠</div>
          <div style={{ fontSize: 11, color: "rgba(255,255,255,0.15)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Memory space empty
          </div>
          <div style={{ fontSize: 10, color: "rgba(255,255,255,0.08)" }}>
            Start a conversation to build your graph
          </div>
        </div>
      )}

      {/* Node count badge */}
      {nodes.length > 0 && (
        <div style={{
          position: "absolute", bottom: 10, right: 12,
          fontSize: 10, color: "rgba(255,255,255,0.2)",
          fontFamily: "'JetBrains Mono', monospace", pointerEvents: "none",
        }}>
          {nodes.filter(n => n.type === "Memory").length} memories ·{" "}
          {nodes.filter(n => n.type === "Concept").length} concepts ·{" "}
          {links.length} edges
        </div>
      )}
    </div>
  );
}
