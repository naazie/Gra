import React, { useMemo } from "react";

/**
 * CssStars — pure CSS animated star particles.
 * Replaces three @react-three/fiber Canvas instances that were running
 * as background decorations in Chat and Sidebar.
 * Zero WebGL context cost. Identical visual result.
 */
export default function CssStars({ count = 60, opacity = 0.45 }) {
  const stars = useMemo(() => {
    return Array.from({ length: count }, (_, i) => ({
      id:      i,
      top:     `${Math.random() * 100}%`,
      left:    `${Math.random() * 100}%`,
      size:    Math.random() * 1.8 + 0.5,
      dur:     `${(Math.random() * 4 + 2).toFixed(1)}s`,
      dur2:    `${(Math.random() * 10 + 6).toFixed(1)}s`,
      delay:   `-${(Math.random() * 5).toFixed(1)}s`,
      delay2:  `-${(Math.random() * 8).toFixed(1)}s`,
    }));
  }, [count]);

  return (
    <div className="css-stars" style={{ opacity }}>
      {stars.map(s => (
        <span
          key={s.id}
          style={{
            top:    s.top,
            left:   s.left,
            width:  s.size,
            height: s.size,
            "--dur":    s.dur,
            "--dur2":   s.dur2,
            "--delay":  s.delay,
            "--delay2": s.delay2,
          }}
        />
      ))}
    </div>
  );
}
