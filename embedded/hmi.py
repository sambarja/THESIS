"""
GO-c / SO5-c — Driver-Side Embedded HMI
=========================================
MicroPython code for ESP32 / Raspberry Pi Pico W.

Hardware:
  - Push button (GPIO 14)  : Start / Stop tracking
  - Buzzer      (GPIO 15)  : Audible rest + maintenance alerts
  - LED Green   (GPIO 16)  : Normal / Online
  - LED Amber   (GPIO 17)  : Low fuel or approaching threshold
  - LED Red     (GPIO 18)  : Alert active (rest due / maintenance due)
  - OLED 128×64 (I2C SDA=21, SCL=22) : Status display (optional)

The HMI polls the backend /fleet/status endpoint every 30 seconds,
reads the alert state for its own vehicle, and drives the indicators.

Backend URL and vehicle_id are configured in config.json on the device.

Wiring diagram:
  ESP32 3.3V → Button → GPIO14 (pull-down)
  ESP32 GPIO15 → 100Ω → Buzzer → GND
  ESP32 GPIO16 → 220Ω → LED Green → GND
  ESP32 GPIO17 → 220Ω → LED Amber → GND
  ESP32 GPIO18 → 220Ω → LED Red   → GND
  ESP32 GPIO21 (SDA), GPIO22 (SCL) → OLED VCC=3.3V, GND=GND

Flash this file to the ESP32 as main.py using Thonny or ampy.
"""

import time
import json
import network
import urequests
from machine import Pin, PWM, I2C, Timer

# ── Load config from config.json ───────────────────────────────────────────────
try:
    with open('config.json') as f:
        cfg = json.load(f)
except:
    cfg = {}

WIFI_SSID    = cfg.get('wifi_ssid',    'YOUR_WIFI_SSID')
WIFI_PASS    = cfg.get('wifi_pass',    'YOUR_WIFI_PASS')
BACKEND_URL  = cfg.get('backend_url',  'http://192.168.1.100:5000')
VEHICLE_ID   = cfg.get('vehicle_id',   'YOUR_VEHICLE_ID')
POLL_INTERVAL = cfg.get('poll_s',      30)    # seconds between backend polls

# ── GPIO pin setup ─────────────────────────────────────────────────────────────
btn_pin    = Pin(14, Pin.IN,  Pin.PULL_DOWN)   # Start/Stop tracking
rest_btn   = Pin(13, Pin.IN,  Pin.PULL_DOWN)   # REST / Pause button
buzzer_pwm = PWM(Pin(15), freq=2000, duty=0)
led_green  = Pin(16, Pin.OUT)
led_amber  = Pin(17, Pin.OUT)
led_red    = Pin(18, Pin.OUT)

# ── Optional OLED (comment out if not used) ────────────────────────────────────
OLED_AVAILABLE = False
try:
    from ssd1306 import SSD1306_I2C
    i2c  = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
    oled = SSD1306_I2C(128, 64, i2c)
    OLED_AVAILABLE = True
except:
    pass

# ── State ──────────────────────────────────────────────────────────────────────
tracking_active = False
trip_paused     = False     # True when driver has pressed REST
current_trip_id = None      # Set when a trip is active
last_status     = {}

# ── LED helpers ────────────────────────────────────────────────────────────────
def all_leds_off():
    led_green.off(); led_amber.off(); led_red.off()

def set_leds(green=False, amber=False, red=False):
    led_green.value(green)
    led_amber.value(amber)
    led_red.value(red)

def buzzer_beep(freq=2000, duration_ms=200, count=1, gap_ms=100):
    buzzer_pwm.freq(freq)
    for _ in range(count):
        buzzer_pwm.duty(512)   # 50% duty
        time.sleep_ms(duration_ms)
        buzzer_pwm.duty(0)
        time.sleep_ms(gap_ms)

def buzzer_off():
    buzzer_pwm.duty(0)

# ── OLED display ───────────────────────────────────────────────────────────────
def oled_show(lines):
    if not OLED_AVAILABLE:
        return
    oled.fill(0)
    for i, line in enumerate(lines[:6]):
        oled.text(str(line)[:16], 0, i * 10)
    oled.show()

# ── WiFi connection ────────────────────────────────────────────────────────────
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    print(f"[HMI] Connecting to {WIFI_SSID}…")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(20):
        if wlan.isconnected():
            print(f"[HMI] WiFi connected: {wlan.ifconfig()[0]}")
            return True
        time.sleep(1)
    print("[HMI] WiFi failed")
    return False

# ── Poll backend ───────────────────────────────────────────────────────────────
def poll_backend():
    global last_status
    try:
        url = f"{BACKEND_URL}/fleet/status"
        r   = urequests.get(url, timeout=5)
        if r.status_code == 200:
            fleet = r.json()
            r.close()
            for truck in fleet:
                if truck.get('vehicle_id') == VEHICLE_ID:
                    last_status = truck
                    return truck
    except Exception as e:
        print(f"[HMI] Poll error: {e}")
    return None

# ── Apply alert logic ──────────────────────────────────────────────────────────
def apply_alerts(status):
    """
    SO5: Drive LEDs and buzzer based on backend status.

    Rules:
      RED + 3 beeps  : rest_needed OR maintenance_due
      AMBER + 1 beep : fuel ≤ 25%  OR approaching rest (≥ 80% of threshold)
      GREEN           : all normal
    """
    if not status:
        # No data — amber blink
        set_leds(amber=True)
        return

    rest_needed  = status.get('rest_needed',     False)
    maint_due    = status.get('maintenance_due', False)
    fuel_low     = (status.get('fuel_level') or 100) <= 25
    fuel_warning = (status.get('fuel_level') or 100) <= 40
    approaching  = status.get('rest_progress_pct', 0) >= 80

    lines = [
        f"TRUCK: {status.get('plate_number','?')}",
        f"FUEL: {status.get('fuel_level','?')}%",
        f"SPD:  {status.get('speed_kmph','?')} km/h",
        f"ODO:  {status.get('odometer_km','?')} km",
        '',
        '',
    ]

    if trip_paused:
        set_leds(amber=True)
        buzzer_off()
        oled_show(['RESTING', 'Trip Paused', '', f"FUEL:{status.get('fuel_level','?')}%", 'Press REST', 'to resume'])
        return

    if rest_needed or maint_due:
        # CRITICAL alert
        set_leds(red=True)
        buzzer_beep(freq=2000, duration_ms=300, count=3, gap_ms=150)
        if rest_needed:
            lines[4] = '! REST NEEDED'
        if maint_due:
            lines[5] = '! MAINTENANCE'
        oled_show(lines)

    elif fuel_low or approaching:
        # WARNING
        set_leds(amber=True)
        buzzer_beep(freq=1000, duration_ms=150, count=1)
        if fuel_low:
            lines[4] = '! LOW FUEL'
        if approaching:
            lines[5] = 'REST SOON'
        oled_show(lines)

    else:
        # Normal
        set_leds(green=True)
        buzzer_off()
        lines[4] = 'ALL NORMAL'
        oled_show(lines)

# ── Backend trip control ────────────────────────────────────────────────────────
def call_trip_pause():
    if not current_trip_id:
        return False
    try:
        r = urequests.post(f"{BACKEND_URL}/trip/pause",
                           data=json.dumps({'trip_id': current_trip_id}),
                           headers={'Content-Type': 'application/json'}, timeout=5)
        ok = r.status_code in (200, 201)
        r.close()
        return ok
    except Exception as e:
        print(f"[HMI] Pause error: {e}")
        return False

def call_trip_resume():
    if not current_trip_id:
        return False
    try:
        r = urequests.post(f"{BACKEND_URL}/trip/resume",
                           data=json.dumps({'trip_id': current_trip_id}),
                           headers={'Content-Type': 'application/json'}, timeout=5)
        ok = r.status_code in (200, 201)
        r.close()
        return ok
    except Exception as e:
        print(f"[HMI] Resume error: {e}")
        return False

# ── REST/PAUSE button handler ──────────────────────────────────────────────────
def check_rest_button():
    global trip_paused
    if not tracking_active:
        return
    if rest_btn.value():
        time.sleep_ms(50)   # debounce
        if rest_btn.value():
            if not trip_paused:
                # Pause / start resting
                if call_trip_pause():
                    trip_paused = True
                    print("[HMI] Trip PAUSED — driver resting")
                    set_leds(amber=True)
                    buzzer_beep(freq=1000, duration_ms=200, count=2)
                    oled_show(['RESTING', 'Trip Paused', '', 'Press REST', 'btn to resume', ''])
            else:
                # Resume driving
                if call_trip_resume():
                    trip_paused = False
                    print("[HMI] Trip RESUMED")
                    set_leds(green=True)
                    buzzer_beep(freq=1500, duration_ms=100, count=2)
                    oled_show(['RESUMED', 'Trip Active', '', VEHICLE_ID, '', ''])
            time.sleep_ms(600)   # hold-off

# ── Button handler (start/stop tracking) ──────────────────────────────────────
def check_button():
    global tracking_active, trip_paused
    if btn_pin.value():
        time.sleep_ms(50)   # debounce
        if btn_pin.value():
            tracking_active = not tracking_active
            if tracking_active:
                trip_paused = False
                print("[HMI] Tracking STARTED")
                buzzer_beep(freq=1500, duration_ms=100, count=2)
                set_leds(green=True)
                oled_show(['TRACKING', 'STARTED', '', VEHICLE_ID, '', ''])
            else:
                trip_paused = False
                print("[HMI] Tracking STOPPED")
                buzzer_beep(freq=800, duration_ms=300, count=1)
                all_leds_off()
                oled_show(['TRACKING', 'STOPPED', '', '', '', ''])
            time.sleep_ms(500)   # hold-off

# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    print("[HMI] Driver HMI starting…")
    all_leds_off()
    oled_show(['FLEET HMI', 'Starting…', '', '', '', ''])

    # Connect WiFi
    if connect_wifi():
        set_leds(green=True)
        time.sleep(1)
    else:
        set_leds(amber=True)

    last_poll = 0

    while True:
        check_button()
        check_rest_button()

        now = time.time()
        if tracking_active and not trip_paused and (now - last_poll) >= POLL_INTERVAL:
            print("[HMI] Polling backend…")
            status    = poll_backend()
            last_poll = now
            if status:
                print(f"[HMI] Status: fuel={status.get('fuel_level')}% "
                      f"rest={status.get('rest_needed')} "
                      f"maint={status.get('maintenance_due')}")
                apply_alerts(status)
            else:
                set_leds(amber=True)   # connection issue

        time.sleep_ms(100)

main()
