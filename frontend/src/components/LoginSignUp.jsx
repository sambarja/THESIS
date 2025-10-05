// LoginSignUp.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../assets/LoginSignUp.css';
import user_icon from '../assets/person.png';
import email_icon from '../assets/email.png';
import password_icon from '../assets/password.png';


    // TODO: replace with API call once backend is ready

const LoginSignUp = ({ setIsLoggedIn }) => {
  const [action, setAction] = useState("Login");

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const navigate = useNavigate();

  const handleSubmit = () => {
    if (action === "Login") {
      // Dummy login validation
      if (email === "user" && password === "1234") {
        setIsLoggedIn(true);
        navigate("/"); // Redirect to dashboard
      } else {
        alert("Invalid email or password");
      }
    } else {
      // For now, just log user data
      console.log("Registered:", { name, email, password });
      alert("Account created. Now login.");
      setAction("Login");
    }
  };

  return (
    <div className='container'>
      <div className="header">
        <div className="text">{action}</div>
        <div className="underline"></div>
      </div>
      <div className="inputs">
        {action === "Login" ? null : (
          <div className="input">
            <img src={user_icon} alt="" />
            <input
              type="text"
              placeholder="Enter Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        )}

        <div className="input">
          <img src={email_icon} alt="" />
          <input
            type="email"
            placeholder="Enter E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="input">
          <img src={password_icon} alt="" />
          <input
            type="password"
            placeholder="Enter Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
      </div>

      {action === "Sign Up" ? null : (
        <div className="forgot-password">
          Lost Password? <span>Click Here!</span>
        </div>
      )}

      <div className="submit-container">
        <div
          className={action === "Login" ? "submit gray" : "submit"}
          onClick={() => setAction("Sign Up")}
        >
          Sign Up
        </div>
        <div
          className={action === "Sign Up" ? "submit gray" : "submit"}
          onClick={() => setAction("Login")}
        >
          Login
        </div>
      </div>

      <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center' }}>
  <button className="submit" onClick={handleSubmit}>
    {action}
  </button>
</div>

    </div>
  );
};

export default LoginSignUp;
