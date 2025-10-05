import { useState } from "react";
import "../assets/Settings.css";


const Settings = () => {
  const [thresholds, setThresholds] = useState({
    restHours: "6",
    restDistance: "300",
    maintenanceDistance: "5000",
  });

  const handleThresholdChange = (field) => (event) => {
    setThresholds((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleThresholdSubmit = (event) => {
    event.preventDefault();
    // TODO: replace with API call once backend is ready
    console.log("Updated alert thresholds", thresholds);
    alert("Alert thresholds updated (mock action)");
  };

  return (
    <div className="settings-wrapper">

      <section className="settings-card">
        <header className="settings-card-header">
          <h2>User Management</h2>
        </header>
        <div className="settings-card-actions">
          <button type="button">Add User</button>
          <button type="button" className="danger">
            Delete User
          </button>
        </div>
      </section>

      <section className="settings-card">
        <header className="settings-card-header">
          <h2>Alert Thresholds</h2>
          <p>Fine-tune alerts for driver rest and maintenance scheduling.</p>
        </header>
        <form className="settings-form" onSubmit={handleThresholdSubmit}>
          <label className="settings-field">
            <span>Rest Hours</span>
            <input
              type="number"
              min="0"
              value={thresholds.restHours}
              onChange={handleThresholdChange("restHours")}
            />
          </label>
          <label className="settings-field">
            <span>Rest Distance (km)</span>
            <input
              type="number"
              min="0"
              value={thresholds.restDistance}
              onChange={handleThresholdChange("restDistance")}
            />
          </label>
          <label className="settings-field">
            <span>Maintenance Distance (km)</span>
            <input
              type="number"
              min="0"
              value={thresholds.maintenanceDistance}
              onChange={handleThresholdChange("maintenanceDistance")}
            />
          </label>
          <div className="settings-form-actions">
            <button type="submit">Save Thresholds</button>
          </div>
        </form>
      </section>

      <section className="settings-card">
        <header className="settings-card-header">
          <h2>Fleet Settings</h2>
          <p>Keep your fleet roster up-to-date.</p>
        </header>
        <div className="settings-card-actions">
          <button type="button">Add Truck</button>
          <button type="button" className="danger">
            Delete Truck
          </button>
        </div>
      </section>
    </div>
  );
};

export default Settings;
