/**
 * Graph3D — 3D mindmap using @react-three/fiber.
 *
 * Props:
 *   graphData      {nodes[], links[]}  — live graph from backend
 *   onSelectNode   (node) => void      — node click handler
 *   citedNodeIds   string[]            — node_ids from the last query's citations
 *                                        These nodes glow gold in the scene.
 */

import React from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import SkillNode from "./SkillNode";
import Edges from "./Edges";

function Graph3D({ graphData, onSelectNode, citedNodeIds = [] }) {
  const { nodes = [], links = [] } = graphData || {};

  const citedSet = new Set(
    citedNodeIds.map((id) => String(id))
  );

  return (
    <div style={{ flex: 1, height: "100vh" }}>
      <Canvas camera={{ position: [0, 0, 15], fov: 60 }}>
        <fog attach="fog" args={["#000000", 10, 40]} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={1.2} />
        <pointLight position={[-5, -5, -5]} intensity={1} />
        <Stars radius={100} depth={50} count={4000} factor={4} fade speed={2} />

        {nodes.map((node) => {
          const nodeUuid = node?.metadata?.uuid ?? node.id;
          const cited    = citedSet.has(String(nodeUuid)) || citedSet.has(String(node.id));
          return (
            <SkillNode
              key={node.id}
              skill={node}
              onClick={() => onSelectNode(node)}
              isCited={cited}
            />
          );
        })}

        <Edges nodes={nodes} links={links} />

        <OrbitControls
          enableZoom
          enableRotate
          enableDamping
          dampingFactor={0.05}
        />
      </Canvas>
    </div>
  );
}

export default Graph3D;
