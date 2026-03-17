// import React, { useState } from "react";
// import { useNavigate } from "react-router-dom";
// import "./Auth.css";

// function Signup({ onSignup, switchToLogin }) {
//   <span onClick={switchToLogin}>Login</span>
//   const [name, setName] = useState("");
//   const navigate = useNavigate();
//   const [email, setEmail] = useState("");
//   const [password, setPassword] = useState("");

//   // Dhrit
//   // const handleSubmit = (e) => {
//   //   e.preventDefault();
//   //   if (name && email && password) {
//   //     onSignup({ name, email });
//   //     navigate("/app", { replace: true });
//   //   }
//   // };


//   // Huma's Change
//   const handleSubmit = async (e) => {
//     e.preventDefault();
//     if (name && email && password) {
//       try {
//         // Calling the /register endpoint
//         const response = await fetch(`http://127.0.0.1:8000/register?username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`, {
//           method: "POST",
//         });

//         if (response.ok) {
//           onSignup({ name, email });
//           navigate("/app", { replace: true });
//         } else {
//           const errorData = await response.json();
//           alert(errorData.detail || "Signup failed");
//         }
//       } catch (error) {
//         console.error("Signup error:", error);
//         alert("Could not connect to server");
//       }
//     }
//   };

//   return (
//     <div className="auth-container">
//       <form className="auth-box" onSubmit={handleSubmit}>
//         <h2>Sign Up</h2>

//         <input
//           type="text"
//           placeholder="Full Name"
//           value={name}
//           onChange={(e) => setName(e.target.value)}
//         />

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

//         <button type="submit">Create Account</button>

//         <p>
//           Already have an account?{" "}
//           <span onClick={() => navigate("/login")} className="link">
//             Login
//           </span>
//         </p>
//       </form>
//     </div>
//   );
// }

// export default Signup;
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Canvas } from "@react-three/fiber";
import { Stars } from "@react-three/drei";
import "./Auth.css";

function Signup({ onSignup }) {
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (name && username && password) {
      try {
        const response = await fetch(
          `http://127.0.0.1:8000/register?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
          { method: "POST" }
        );

        if (response.ok) {
          // Store session and update state
          localStorage.setItem("graphmind_user", JSON.stringify({ username }));
          onSignup({ name, username });
          navigate("/app", { replace: true });
        } else {
          const errorData = await response.json();
          alert(errorData.detail || "Signup failed");
        }
      } catch (error) {
        console.error("Signup error:", error);
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
        <h2>Sign Up</h2>

        <input
          type="text"
          placeholder="Full Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

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

        <button type="submit">Create Account</button>

        <p>
          Already have an account?{" "}
          <span onClick={() => navigate("/login")} className="link">
            Login
          </span>
        </p>
      </form>
    </div>
  );
}

export default Signup;