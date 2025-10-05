import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import Navbar from "react-bootstrap/Navbar";
import Nav from "react-bootstrap/Nav";

function MyNavbar() {
  const [dateTime, setDateTime] = useState(new Date());
  const location = useLocation();

  // live clock
  useEffect(() => {
    const timer = setInterval(() => setDateTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const day = dateTime.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
  const time = dateTime.toLocaleTimeString();

  // map paths to titles
  const pageTitles = {
    "/": "Dashboard",
    "/alerts": "Alerts",
    "/logs": "Logs",
    "/settings": "Settings",
  };

  const currentTitle = pageTitles[location.pathname] || "Fleet Manager";

  return (
    <Navbar bg="dark" data-bs-theme="dark" expand="lg" className="w-100">
      <div className="d-flex justify-content-between align-items-center w-100 px-3">
        {/* Left: Logo + Nav Links */}
        <div className="d-flex align-items-center">
          <Navbar.Brand as="span" className="mx-auto text-white">

            <img
              src="/tempLogo.svg"
              alt="Logo"
              width="40"
              height="40"
              className="d-inline-block align-top me-2"
            />
            Fleet Manager
          </Navbar.Brand>
          <Nav className="me-auto">
            <Nav.Link as={NavLink} to="/">Dashboard</Nav.Link>
            <Nav.Link as={NavLink} to="/alerts">Alerts</Nav.Link>
            <Nav.Link as={NavLink} to="/logs">Logs</Nav.Link>
            <Nav.Link as={NavLink} to="/settings">Settings</Nav.Link>
          </Nav>
        </div>

        {/* Center: Dynamic Title */}
        <div className="text-center flex-grow-1">
          <h5 className="text-white m-0">{currentTitle}</h5>
        </div>

        {/* Right: Day & Time */}
        <div className="text-end text-white">
          <div>{day}</div>
          <div>{time}</div>
        </div>
      </div>
    </Navbar>
  );
}

export default MyNavbar;
