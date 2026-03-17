import React, { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Graph3D from "./components/Graph3D";
import Sidebar from "./components/Sidebar";
import Login from "./components/Login";
import Signup from "./components/Signup";
import Chat from "./components/Chat";

function MainApp({ user, setUser }) {
  const [selectedSkill, setSelectedSkill]   = useState(null);
  const [isBrainOpen, setIsBrainOpen]       = useState(true);
  const [graphData, setGraphData]           = useState({ nodes: [], links: [] });
  // citedNodeIds: node_ids from the most recent query response
  // passed to Graph3D so cited nodes glow gold in the 3D mindmap
  const [citedNodeIds, setCitedNodeIds]     = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    if (!user?.username) return;
    fetch(`http://127.0.0.1:8000/graph-visuals/${user.username}`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => data && setGraphData(data))
      .catch(() => {});
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem("graphmind_user");
    setUser(null);
    navigate("/login");
  };

  return (
    <div className="dashboard">
      <button className="logout-btn" onClick={handleLogout}>
        Logout
      </button>

      <div className={`chat-section ${isBrainOpen ? "" : "full"}`}>
        <Chat
          user={user}
          setGraphData={setGraphData}
          setCitedNodeIds={setCitedNodeIds}
        />
      </div>

      <div className={`brain-section ${isBrainOpen ? "open" : "collapsed"}`}>
        <button
          className={`toggle-btn ${isBrainOpen ? "open" : "collapsed"}`}
          onClick={() => setIsBrainOpen(!isBrainOpen)}
        >
          <span className="chev">{isBrainOpen ? "›" : "‹"}</span>
        </button>

        {isBrainOpen && (
          <>
            <div className="brain-top">
              <Graph3D
                graphData={graphData}
                onSelectNode={setSelectedSkill}
                citedNodeIds={citedNodeIds}
              />
            </div>
            <div className="brain-bottom">
              <Sidebar skill={selectedSkill} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem("graphmind_user");
    return saved ? JSON.parse(saved) : null;
  });

  return (
    <Routes>
      <Route path="/login"  element={user ? <Navigate to="/app" /> : <Login  onLogin={setUser}  />} />
      <Route path="/signup" element={user ? <Navigate to="/app" /> : <Signup onSignup={setUser} />} />
      <Route path="/app"    element={user ? <MainApp user={user} setUser={setUser} /> : <Navigate to="/login" />} />
      <Route path="*"       element={<Navigate to="/login" />} />
    </Routes>
  );
}

export default App;
