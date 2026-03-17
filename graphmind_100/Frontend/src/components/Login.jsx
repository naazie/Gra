// import React, { useState } from "react";
// import { useNavigate } from "react-router-dom";
// import "./Auth.css";

// function Login({ onLogin, switchToSignup }) {
//   <span onClick={switchToSignup}>Sign up</span>
//   const [email, setEmail] = useState("");
//   const [password, setPassword] = useState("");
//   const navigate = useNavigate();

//   // DHRITI CODE
//   // const handleSubmit = (e) => {
//   //   e.preventDefault();
//   //   if (email && password) {
//   //     onLogin({ email });
//   //     navigate("/app", { replace: true });
//   //   }
//   // };

//   // HUMA CHANGED TO 
//   const handleSubmit = async (e) => {
//     e.preventDefault();
//     if (email && password) {
//       try {
//         const response = await fetch(`http://127.0.0.1:8000/login?username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`, {
//           method: "POST",
//         });

//         if (response.ok) {
//           // --- NEW: Persist the session ---
//           localStorage.setItem("graphmind_user", JSON.stringify({ email }));
          
//           onLogin({ email }); 
//           navigate("/app", { replace: true });
//         } else {
//           const errorData = await response.json();
//           alert(errorData.detail || "Login failed");
//         }
//       } catch (error) {
//         console.error("Login error:", error);
//       }
//     }
//   };
  
//   return (
//     <div className="auth-container">
//       <form className="auth-box" onSubmit={handleSubmit}>
//         <h2>Login</h2>

//         <input
//           type="email"
//           placeholder="Email"
//           value={email}
//           onChange={(e) => setEmail(e.target.value)}
//         />

//         <input
//           type="password"
//           placeholder="Password"
//           value={password}
//           onChange={(e) => setPassword(e.target.value)}
//         />

//         <button type="submit">Login</button>

//         <p>
//           Don't have an account?{" "}
//           <span onClick={() => navigate("/signup")} className="link">
//             Sign up
//           </span>
//         </p>
//       </form>
//     </div>
//   );
// }

// export default Login;
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";
import "./Auth.css";

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (username && password) {
      try {
        const response = await fetch(
          `http://127.0.0.1:8000/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
          { method: "POST" }
        );

        if (response.ok) {
          // Persist using username
          localStorage.setItem("graphmind_user", JSON.stringify({ username }));
          onLogin({ username }); 
          navigate("/app", { replace: true });
        } else {
          const errorData = await response.json();
          alert(errorData.detail || "Login failed");
        }
      } catch (error) {
        console.error("Login error:", error);
        alert("Could not connect to server");
      }
    }
  };
  
  return (
    <div className="auth-container">
      <div className="stars-container">
        <Canvas camera={{ position: [0, 0, 1] }} style={{ width: "100%", height: "100%" }}>
          <Stars radius={100} depth={50} count={5000} factor={4} fade speed={2} />
        </Canvas>
      </div>
      <form className="auth-box" onSubmit={handleSubmit}>
        <h2>Login</h2>

        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />

        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button type="submit">Login</button>

        <p>
          Don't have an account?{" "}
          <span onClick={() => navigate("/signup")} className="link">
            Sign up
          </span>
        </p>
      </form>
    </div>
  );
}

export default Login;