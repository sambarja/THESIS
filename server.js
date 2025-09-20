require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { createClient } = require('@supabase/supabase-js');
const bcrypt = require('bcryptjs');


const app = express();
app.use(bodyParser.json());

// Supabase client
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
);

const PORT = process.env.PORT || 5000;

// ----------------------
// Health check endpoint
// ----------------------
app.get('/', (req, res) => {
  res.json({ status: 'ok', service: 'Fleet Monitoring API' });
});

// ----------------------
// User login
// ----------------------
app.post('/login', async (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) return res.status(400).json({ error: 'Email and password required' });

  const { data: users, error } = await supabase
    .from('users')
    .select('*')
    .eq('email', email)
    .single();

  if (error || !users) return res.status(401).json({ error: 'Invalid email or password' });

  const match = await bcrypt.compare(password, users.password_hash);
  if (!match) return res.status(401).json({ error: 'Invalid email or password' });

  res.status(200).json({ user_id: users.id, role: users.role, email: users.email });
});

// ----------------------
// Vehicle registration (only assign to driver)
// ----------------------
app.post('/vehicles', async (req, res) => {
  const { plate_number, user_id } = req.body;

  if (!plate_number || !user_id) {
    return res.status(400).json({ error: 'plate_number and user_id are required' });
  }

  // Ensure the user exists and is a driver
  const { data: user, error: userErr } = await supabase
    .from('users')
    .select('id, role')
    .eq('id', user_id)
    .single();

  if (userErr || !user) return res.status(400).json({ error: 'Invalid user_id' });
  if (user.role !== 'driver') return res.status(403).json({ error: 'Only drivers can be assigned to vehicles' });

  const { data, error } = await supabase
    .from('vehicles')
    .insert([{ plate_number, user_id }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);
});

// ----------------------
// Sensor data ingestion
// ----------------------
app.post('/vehicles/:vehicleId/sensor', async (req, res) => {
  const { vehicleId } = req.params;
  const { user_id, fuel_level, speed_kmph, odometer_km, latitude, longitude } = req.body;

  // Check vehicle ownership
  const { data: vehicle, error: vErr } = await supabase
    .from('vehicles')
    .select('user_id')
    .eq('id', vehicleId)
    .single();

  if (vErr || !vehicle) return res.status(404).json({ error: 'Vehicle not found' });
  if (vehicle.user_id !== user_id) return res.status(403).json({ error: 'Only assigned driver can post sensor data' });

  const { data, error } = await supabase
    .from('sensor_data')
    .insert([{
      vehicle_id: vehicleId,
      fuel_level,
      speed_kmph,
      odometer_km,
      latitude,
      longitude
    }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);
});

// ----------------------
// Alerts creation (driver or admin)
// ----------------------
app.post('/vehicles/:vehicleId/alerts', async (req, res) => {
  const { vehicleId } = req.params;
  const { user_id, type, severity, details } = req.body;

  if (!type || !severity || !details) {
    return res.status(400).json({ error: 'type, severity, and details are required' });
  }

  // Check if user can post alert (driver assigned or admin)
  const { data: user, error: userErr } = await supabase
    .from('users')
    .select('role')
    .eq('id', user_id)
    .single();
  if (userErr || !user) return res.status(404).json({ error: 'User not found' });

  const { data: vehicle, error: vehicleErr } = await supabase
    .from('vehicles')
    .select('user_id')
    .eq('id', vehicleId)
    .single();
  if (vehicleErr || !vehicle) return res.status(404).json({ error: 'Vehicle not found' });

  if (user.role !== 'admin' && vehicle.user_id !== user_id) {
    return res.status(403).json({ error: 'Only assigned driver or admin can create alerts' });
  }

  const { data, error } = await supabase
    .from('alerts')
    .insert([{
      vehicle_id: vehicleId,
      type,
      severity,
      details
    }])
    .select();

  if (error) return res.status(400).json({ error: error.message });
  res.status(201).json(data[0]);
});

// ----------------------
// Fetch vehicles
// ----------------------
app.get('/vehicles', async (req, res) => {
  const { data, error } = await supabase.from('vehicles').select();
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// Fetch alerts for a vehicle
// ----------------------
app.get('/vehicles/:vehicleId/alerts', async (req, res) => {
  const { vehicleId } = req.params;
  const { data, error } = await supabase.from('alerts').select().eq('vehicle_id', vehicleId);
  if (error) return res.status(400).json({ error: error.message });
  res.json(data);
});

// ----------------------
// Get all sensor data for a vehicle
// ----------------------
app.get('/vehicles/:vehicleId/sensor', async (req, res) => {
  const { vehicleId } = req.params;
  const { data, error } = await supabase
    .from('sensor_data')
    .select('*')
    .eq('vehicle_id', vehicleId)
    .order('created_at', { ascending: true });
  if (error) return res.status(400).json({ error: error.message });
  res.status(200).json(data);
});

// ----------------------
// Start server
// ----------------------
app.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
