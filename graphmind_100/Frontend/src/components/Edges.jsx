// import React from "react";
// import * as THREE from "three";

// function Edges({ nodes, links }) {
//   return (
//     <>
//       {links.map((link, index) => {
//         // Find the source and target nodes based on their IDs
//         const sourceNode = nodes.find((n) => n.id === link.source);
//         const targetNode = nodes.find((n) => n.id === link.target);

//         if (!sourceNode || !targetNode) return null;

//         const points = [
//           new THREE.Vector3(...sourceNode.position),
//           new THREE.Vector3(...targetNode.position)
//         ];

//         const geometry = new THREE.BufferGeometry().setFromPoints(points);

//         return (
//           <line key={index} geometry={geometry}>
//             <lineBasicMaterial color="rgba(255, 255, 255, 0.3)" />
//           </line>
//         );
//       })}
//     </>
//   );
// }

// export default Edges;
import React, { useMemo } from "react";
import * as THREE from "three";

function Edges({ nodes, links }) {
  // useMemo prevents recalculating geometry on every frame
  const lines = useMemo(() => {
    return links.map((link) => {
      // Find source and target nodes
      // We use String() to ensure IDs match even if one is a number and one is a string
      const sourceNode = nodes.find((n) => String(n.id) === String(link.source));
      const targetNode = nodes.find((n) => String(n.id) === String(link.target));

      if (!sourceNode || !targetNode) return null;

      const points = [
        new THREE.Vector3(...sourceNode.position),
        new THREE.Vector3(...targetNode.position),
      ];

      return {
        geometry: new THREE.BufferGeometry().setFromPoints(points),
        id: `${link.source}-${link.target}`,
      };
    }).filter(Boolean); // Remove nulls
  }, [nodes, links]);

  return (
    <>
      {lines.map((line) => (
        <line key={line.id} geometry={line.geometry}>
          <lineBasicMaterial 
            color="#ffffff" 
            transparent 
            opacity={0.4} 
            linewidth={1} // Note: linewidth > 1 doesn't work in most browsers
          />
        </line>
      ))}
    </>
  );
}

export default Edges;