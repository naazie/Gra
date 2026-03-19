import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";

const API = "http://localhost:8000";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) return;
    setError(""); setLoading(true);
    try {
      const r = await fetch(
        `${API}/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
        { method: "POST" }
      );
      if (r.ok) {
        const d = await r.json();
        // Store JWT token + username
        localStorage.setItem("graphmind_user",  JSON.stringify({ username: d.username }));
        localStorage.setItem("graphmind_token", d.token);
        onLogin({ username: d.username, token: d.token });
        navigate("/app", { replace: true });
      } else {
        const d = await r.json();
        setError(d.detail || "Invalid credentials");
      }
    } catch { setError("Cannot connect to GraphMind server"); }
    finally  { setLoading(false); }
  };

  return (
    <div className="auth-container">
      <div className="stars-container">
        <Canvas camera={{ position: [0, 0, 1] }}>
          <Stars radius={120} depth={60} count={5000} factor={4} fade speed={1.5} />
        </Canvas>
      </div>
      <div className="auth-bg-glow-1" /><div className="auth-bg-glow-2" />
      <div className="auth-card">
        <div className="auth-logo">
          <div className="auth-logo-orb">🧠</div>
          <h1>GraphMind</h1>
          <p>AI Long-Term Memory Engine</p>
        </div>
        {error && <div className="auth-err">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="auth-field">
            <label>Username</label>
            <input type="text" placeholder="your username" value={username}
              onChange={e => setUsername(e.target.value)} autoFocus />
          </div>
          <div className="auth-field">
            <label>Password</label>
            <input type="password" placeholder="••••••••" value={password}
              onChange={e => setPassword(e.target.value)} />
          </div>
          <button className="auth-btn" type="submit" disabled={loading || !username || !password}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="auth-switch">No account? <span onClick={() => navigate("/signup")}>Create one</span></div>
        <div className="auth-demo">Demo: <strong>demo</strong> / <strong>graphmind2026</strong></div>
      </div>
    </div>
  );
}
