"""
SO1-c / SO2-d — Embedded Firmware Pseudocode
=============================================
Fuel + GPS acquisition, filtering, preprocessing, and transmission.

This file documents the firmware architecture for:
  SO1-c  Fuel sensor reading, filtering, preprocessing
  SO1-d  Drift/noise/variance logging
  SO2-a  IoT communication (LoRa primary, GSM backup)
  SO2-b  Structured data schema for cloud transmission
  SO2-d  Buffering and retry logic
  SO3-a  GPS capture at 5-second intervals

Target hardware assumptions:
  MCU         : ESP32 (dual-core, 240 MHz, WiFi+BT built-in)
  Fuel sensor : Resistive float sensor on ADC pin → 10-bit ADC (0–4095)
                OR OBD-II ELM327 via UART/Bluetooth
  GPS module  : u-blox NEO-6M (UART, 9600 baud, NMEA sentences)
  LoRa module : SX1276 (SPI, 915 MHz) — primary long-range communication
  GSM module  : SIM800L (UART) — backup when LoRa out of range
  Display     : SSD1306 128×64 OLED (I2C)
  RTC         : DS3231 or NTP sync for accurate timestamps
"""

import time
import json
import math

# ══════════════════════════════════════════════════════════════════════════════
#  SO1-c: FUEL SENSOR ACQUISITION AND FILTERING
# ══════════════════════════════════════════════════════════════════════════════

# Hardware assumption:
#   Fuel float sensor: 0 Ω (empty) → 180 Ω (full) → voltage divider on ADC
#   ADC reading: 0 (empty) → ~3000 (full) on 12-bit ADC

FUEL_ADC_EMPTY = 400     # ADC value at empty (calibrated)
FUEL_ADC_FULL  = 3600    # ADC value at full  (calibrated)
MOVING_AVG_N   = 5       # window for moving average filter

_fuel_buffer = []


def read_raw_adc(pin=34):
    """
    Pseudocode: Read raw ADC value from fuel sensor pin.
    Real code: from machine import ADC, Pin; adc = ADC(Pin(34)); return adc.read()
    """
    # Simulated for documentation purposes
    return 2800 + int((time.time() % 100) * 5)   # placeholder


def adc_to_fuel_pct(adc_val: int) -> float:
    """
    SO1-a: Convert raw ADC reading to fuel percentage.
    Applies calibration map: linear between EMPTY and FULL.
    Achieves ±5% accuracy per SO1 requirement when properly calibrated.
    """
    pct = (adc_val - FUEL_ADC_EMPTY) / (FUEL_ADC_FULL - FUEL_ADC_EMPTY) * 100.0
    return max(0.0, min(100.0, pct))


def moving_average_filter(new_val: float) -> float:
    """
    SO1-c: Moving average filter to reduce sensor noise.
    Maintains a sliding window of the last N readings.
    """
    _fuel_buffer.append(new_val)
    if len(_fuel_buffer) > MOVING_AVG_N:
        _fuel_buffer.pop(0)
    return sum(_fuel_buffer) / len(_fuel_buffer)


def read_fuel_level() -> dict:
    """
    SO1-c: Full fuel acquisition pipeline.
    Returns filtered fuel level + noise metrics for SO1-d.
    """
    samples = [adc_to_fuel_pct(read_raw_adc()) for _ in range(10)]
    raw_avg  = sum(samples) / len(samples)
    filtered = moving_average_filter(raw_avg)

    # SO1-d: noise / variance metrics
    variance = sum((s - raw_avg)**2 for s in samples) / len(samples)
    std_dev  = math.sqrt(variance)

    return {
        'fuel_pct':  round(filtered, 2),
        'raw_avg':   round(raw_avg, 2),
        'std_dev':   round(std_dev, 4),
        'variance':  round(variance, 4),
        'n_samples': len(samples),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SO3-a: GPS ACQUISITION (5-SECOND INTERVALS)
# ══════════════════════════════════════════════════════════════════════════════

def parse_nmea_gprmc(sentence: str) -> dict | None:
    """
    Parse GPRMC NMEA sentence from u-blox GPS module.
    Example: $GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A

    Returns dict with lat, lon, speed_kmh, timestamp or None if invalid.
    """
    try:
        parts = sentence.split(',')
        if parts[0] != '$GPRMC' or parts[2] != 'A':
            return None   # not GPRMC or no fix

        # Latitude: DDMM.MMMMM → decimal degrees
        lat_raw = float(parts[3])
        lat_deg = int(lat_raw / 100)
        lat_min = lat_raw - lat_deg * 100
        lat     = lat_deg + lat_min / 60
        if parts[4] == 'S':
            lat = -lat

        # Longitude: DDDMM.MMMMM → decimal degrees
        lon_raw = float(parts[5])
        lon_deg = int(lon_raw / 100)
        lon_min = lon_raw - lon_deg * 100
        lon     = lon_deg + lon_min / 60
        if parts[6] == 'W':
            lon = -lon

        # Speed: knots → km/h
        speed_kmh = float(parts[7]) * 1.852

        return {
            'latitude':   round(lat, 6),
            'longitude':  round(lon, 6),
            'speed_kmph': round(speed_kmh, 1),
        }
    except Exception:
        return None


def read_gps(uart_port=2, timeout_ms=2000) -> dict | None:
    """
    SO3-a: Read GPS from UART, parse GPRMC sentence.
    Real code: from machine import UART; uart = UART(2, 9600)
    Returns lat/lon/speed or None if no fix.
    """
    # Pseudocode — in real firmware:
    # uart = UART(2, baudrate=9600, tx=17, rx=16)
    # deadline = time.ticks_ms() + timeout_ms
    # while time.ticks_ms() < deadline:
    #     line = uart.readline()
    #     if line and b'GPRMC' in line:
    #         result = parse_nmea_gprmc(line.decode('ascii', errors='ignore').strip())
    #         if result: return result
    # return None
    return {'latitude': 14.5995, 'longitude': 120.9842, 'speed_kmph': 65.0}


# ══════════════════════════════════════════════════════════════════════════════
#  SO1-d: DRIFT AND VARIANCE LOGGING
# ══════════════════════════════════════════════════════════════════════════════

drift_log = []

def log_drift_sample(fuel_reading: dict, manual_pct: float = None):
    """
    SO1-d: Log sensor reading with optional manual comparison value.
    Used to build SO1-b accuracy validation dataset.
    """
    entry = {
        'timestamp':  time.time(),
        'sensor_pct': fuel_reading['fuel_pct'],
        'raw_avg':    fuel_reading['raw_avg'],
        'std_dev':    fuel_reading['std_dev'],
        'variance':   fuel_reading['variance'],
        'manual_pct': manual_pct,
        'error_pct':  abs(fuel_reading['fuel_pct'] - manual_pct) if manual_pct else None,
    }
    drift_log.append(entry)
    # In real firmware: write to SD card or flash filesystem
    # with open('/drift_log.csv', 'a') as f:
    #     f.write(','.join(str(v) for v in entry.values()) + '\n')
    return entry


# ══════════════════════════════════════════════════════════════════════════════
#  SO2-d: TRANSMISSION WITH BUFFERING AND RETRY
# ══════════════════════════════════════════════════════════════════════════════

TX_BUFFER   = []
MAX_BUFFER  = 50      # hold up to 50 readings if network is down
MAX_RETRIES = 3
RETRY_DELAY = 5       # seconds


def build_payload(fuel: dict, gps: dict, vehicle_id: str, odometer: float) -> dict:
    """
    SO2-b: Build structured telemetry payload for cloud transmission.
    """
    return {
        'vehicle_id': vehicle_id,
        'fuel_level': fuel['fuel_pct'],
        'speed_kmph': gps['speed_kmph'] if gps else None,
        'odometer_km': round(odometer, 1),
        'latitude':   gps['latitude']  if gps else None,
        'longitude':  gps['longitude'] if gps else None,
        'sent_at':    time.time(),   # SO2-c: timestamp for latency calc
    }


def transmit_lora(payload: dict) -> bool:
    """
    SO2-a: Transmit via LoRa (SX1276).
    Real code uses a LoRa library (e.g., uLoRa).
    Returns True on success.
    """
    # lora.send(json.dumps(payload).encode())
    # return lora.send_and_wait_for_ack()
    print(f"[LoRa] TX: {payload['vehicle_id']} fuel={payload['fuel_level']}%")
    return True   # placeholder


def transmit_gsm(payload: dict, backend_url: str) -> bool:
    """
    SO2-a: Fallback to GSM HTTP POST (SIM800L).
    Real code uses AT commands via UART.
    """
    # gsm.post(backend_url + '/telemetry', json.dumps(payload))
    print(f"[GSM]  TX: {payload['vehicle_id']} fuel={payload['fuel_level']}%")
    return True   # placeholder


def transmit_with_retry(payload: dict, backend_url: str) -> bool:
    """
    SO2-d: Try LoRa first, fall back to GSM, buffer if both fail.
    """
    for attempt in range(MAX_RETRIES):
        try:
            if transmit_lora(payload):
                return True
        except Exception:
            pass

        try:
            if transmit_gsm(payload, backend_url):
                return True
        except Exception:
            pass

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    # Both failed — buffer the payload
    if len(TX_BUFFER) < MAX_BUFFER:
        TX_BUFFER.append(payload)
        print(f"[TX] Buffered (buffer size: {len(TX_BUFFER)})")
    else:
        TX_BUFFER.pop(0)   # drop oldest
        TX_BUFFER.append(payload)
        print("[TX] Buffer full — dropped oldest reading")
    return False


def flush_buffer(backend_url: str):
    """
    SO2-d: Retry buffered readings when connection is restored.
    """
    sent = []
    for payload in TX_BUFFER:
        if transmit_lora(payload) or transmit_gsm(payload, backend_url):
            sent.append(payload)
    for p in sent:
        TX_BUFFER.remove(p)
    if sent:
        print(f"[TX] Flushed {len(sent)} buffered readings")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN FIRMWARE LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main_loop(vehicle_id: str, backend_url: str):
    """
    Main 5-second telemetry loop combining all SO1–SO3 functions.
    SO3-a: GPS captured every 5 seconds.
    SO2-c: sent_at timestamp included in every payload.
    """
    odometer   = 0.0
    last_gps   = None
    INTERVAL   = 5   # seconds — SO3 requirement

    print(f"[firmware] Starting telemetry for vehicle {vehicle_id}")

    while True:
        loop_start = time.time()

        # SO1-c: Read and filter fuel level
        fuel = read_fuel_level()

        # SO3-a: Read GPS
        gps = read_gps()
        if gps and last_gps:
            # Compute distance increment (Haversine simplified)
            dlat = gps['latitude']  - last_gps['latitude']
            dlon = gps['longitude'] - last_gps['longitude']
            dist = math.sqrt(dlat**2 + dlon**2) * 111.0   # rough km
            odometer += dist
        last_gps = gps

        # SO2-b: Build payload
        payload = build_payload(fuel, gps, vehicle_id, odometer)

        # SO1-d: Log drift sample (manual_pct=None unless doing calibration)
        log_drift_sample(fuel)

        # SO2-d: Transmit with retry
        transmit_with_retry(payload, backend_url)

        # Flush buffer if connection was restored
        if TX_BUFFER:
            flush_buffer(backend_url)

        # Sleep for remainder of interval
        elapsed = time.time() - loop_start
        sleep_s = max(0, INTERVAL - elapsed)
        time.sleep(sleep_s)


# SO1-e: Mechanical housing design notes
HOUSING_NOTES = """
SO1-e — Sensor Housing Design Notes
=====================================
Material     : ABS plastic enclosure (IP65 rated) for fuel/vibration exposure
Mounting     : DIN rail mount inside cab instrument panel
Sensor cable : Shielded 2-wire cable, max 3m between float and ECU connector
Vibration    : Rubber gaskets on all mounting points; moving average filter
               (N=5) compensates for vibration-induced reading noise
Fuel exposure: Sensor probe is stainless steel 316L; connector is IP67
Connector    : Deutsch DT series (industry standard for truck environments)
EMC          : Ferrite beads on power lines; shielded enclosure
Temperature  : Operating range -20°C to +70°C (tropical/Southeast Asian climate)
"""


if __name__ == '__main__':
    # Documentation / simulation mode
    print("Firmware pseudocode — run on ESP32 hardware via MicroPython")
    print(HOUSING_NOTES)

    # Simulate one reading
    fuel = read_fuel_level()
    gps  = read_gps()
    p    = build_payload(fuel, gps, 'TRUCK-01', 12345.6)
    print("Sample payload:", json.dumps(p, indent=2))
