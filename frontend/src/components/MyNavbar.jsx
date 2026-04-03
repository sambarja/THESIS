import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import Navbar from "react-bootstrap/Navbar";
import Nav from "react-bootstrap/Nav";
import Container from "react-bootstrap/Container";

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
    "/":          "Dashboard",
    "/map":       "Live Map",
    "/analytics": "Analytics",
    "/alerts":    "Alerts",
    "/logs":      "Logs",
    "/settings":  "Settings",
  };

  const currentTitle = pageTitles[location.pathname] || "Fleet Manager";

  return (
    <Navbar bg="dark" data-bs-theme="dark" expand="lg" className="w-100 py-0">
      <Container fluid className="px-3">
        {/* Brand */}
        <Navbar.Brand as="span" className="text-white d-flex align-items-center gap-2 py-2">
          <img
            src="/tempLogo.svg"
            alt="Logo"
            width="32"
            height="32"
            className="d-inline-block"
          />
          <span className="d-none d-sm-inline">Fleet Manager</span>
        </Navbar.Brand>

        {/* Mobile: page title in center */}
        <span className="text-white fw-semibold d-lg-none mx-auto">{currentTitle}</span>

        {/* Hamburger toggle */}
        <Navbar.Toggle aria-controls="main-nav" />

        {/* Collapsible nav */}
        <Navbar.Collapse id="main-nav">
          <Nav className="me-auto">
            <Nav.Link as={NavLink} to="/">Dashboard</Nav.Link>
            <Nav.Link as={NavLink} to="/map">Map</Nav.Link>
            <Nav.Link as={NavLink} to="/analytics">Analytics</Nav.Link>
            <Nav.Link as={NavLink} to="/alerts">Alerts</Nav.Link>
            <Nav.Link as={NavLink} to="/logs">Logs</Nav.Link>
            <Nav.Link as={NavLink} to="/settings">Settings</Nav.Link>
          </Nav>

          {/* Desktop: page title center — push clock to right */}
          <div className="text-white text-center flex-grow-1 d-none d-lg-block">
            <span className="fw-semibold">{currentTitle}</span>
          </div>

          {/* Clock — shown inline in collapse on mobile, right-aligned on desktop */}
          <div className="text-white text-end py-2 py-lg-0" style={{ fontSize: '0.82rem', lineHeight: 1.4 }}>
            <div className="d-none d-lg-block">{day}</div>
            <div>{time}</div>
          </div>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default MyNavbar;
