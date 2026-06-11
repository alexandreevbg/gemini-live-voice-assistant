#!/usr/bin/env python3
"""
Wi-Fi configuration portal for Chochko voice assistant.
Self-contained — no dependencies on voiceAssist directory.
Hardware: ReSpeaker 2-mic button (GPIO17), APA102 LEDs via SPI.
"""
import os
import subprocess
import datetime
import time
import socket
import threading
import atexit
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs

import spidev
from gpiozero import Button

# --- Configuration ---
HOTSPOT_SSID           = "Chochko-WiFi-Setup"
HOTSPOT_PASSWORD       = "chochko123"
HOTSPOT_IP             = "192.168.4.1"
BUTTON_PIN             = 17
PORTAL_TIMEOUT_SECONDS = 300
CREDENTIALS            = {}

# --- Logging ---
script_dir = os.path.dirname(os.path.abspath(__file__))

def log(message):
    ts   = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {message}"
    print(line)

# --- LEDs (APA102 via SPI) ---
# Fatal — hardware is required
try:
    _spi = spidev.SpiDev()
    _spi.open(0, 0)
    _spi.max_speed_hz = 1000000
    log("LED: SPI initialized ✓")
except Exception as e:
    raise RuntimeError(f"FATAL: Cannot initialize LEDs via SPI: {e}") from e

N_LEDS = 3
BLUE   = (0, 0, 80)
RED    = (80, 0, 0)

def _led_write(r, g, b):
    buf = [0] * 4
    for _ in range(N_LEDS):
        buf += [0xFF, b, g, r]   # APA102: BGR order
    buf += [0xFF] * 4
    _spi.xfer2(buf)

def led_all(color: tuple):
    _led_write(*color)

def led_off():
    _led_write(0, 0, 0)

class LedController:
    def __init__(self):
        self._stop   = threading.Event()
        self._thread = None

    def startup_blink(self):
        log("LED: startup blink")
        led_all(BLUE)
        time.sleep(0.5)
        led_off()

    def start_pulse(self, color=BLUE):
        self.stop_pulse()
        self._stop = threading.Event()
        self._color = color
        self._thread = threading.Thread(
            target=self._pulse_loop, daemon=True
        )
        self._thread.start()
        log(f"LED: pulse {'blue' if color == BLUE else 'red'}")

    def _pulse_loop(self):
        while not self._stop.is_set():
            led_all(self._color)
            if self._stop.wait(0.5):
                break
            led_off()
            if self._stop.wait(0.5):
                break

    def stop_pulse(self):
        if self._thread and self._thread.is_alive():
            self._stop.set()
            self._thread.join(timeout=2)

    def turn_off(self):
        self.stop_pulse()
        led_off()
        _spi.close()
        log("LED: off")

# --- Button ---
try:
    _button = Button(BUTTON_PIN, pull_up=True)
    log(f"GPIO: Button on pin {BUTTON_PIN} ✓")
except Exception as e:
    raise RuntimeError(f"FATAL: Cannot initialize button on GPIO{BUTTON_PIN}: {e}") from e

def is_button_pressed() -> bool:
    return _button.is_pressed

def wait_for_button_release():
    while _button.is_pressed:
        time.sleep(0.05)
    time.sleep(0.1)

# --- System Commands ---
def run_cmd(command, check=True) -> bool:
    # Prepend sudo for nmcli and reboot/poweroff commands
    if command[0] in ('nmcli', 'reboot', 'poweroff'):
        command = ['sudo'] + command
    log(f"CMD: {' '.join(command)}")
    try:
        r = subprocess.run(
            command, check=check, capture_output=True,
            text=True, timeout=30
        )
        if r.stdout: log(f"  OUT: {r.stdout.strip()}")
        if r.stderr: log(f"  ERR: {r.stderr.strip()}")
        return True
    except Exception as e:
        log(f"  ERROR: {e}")
        return False

def check_internet(host="8.8.8.8", port=53, timeout=3) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
        log("Internet OK ✓")
        return True
    except Exception:
        log("No internet")
        return False

def get_last_wifi() -> str | None:
    """Get most recently used WiFi connection name."""
    try:
        r = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE,TIMESTAMP', 'connection', 'show'],
            capture_output=True, text=True
        )
        wifi = []
        for line in r.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3 and parts[1] == '802-11-wireless':
                name = parts[0]
                ts   = parts[2]
                if name != HOTSPOT_SSID:
                    wifi.append((name, ts))
        wifi.sort(key=lambda x: x[1], reverse=True)
        return wifi[0][0] if wifi else None
    except Exception as e:
        log(f"get_last_wifi error: {e}")
        return None

# --- Network ---
def start_hotspot() -> bool:
    log("Starting hotspot...")
    run_cmd(["nmcli", "device", "disconnect", "wlan0"], check=False)
    time.sleep(1)
    run_cmd(["nmcli", "connection", "delete", HOTSPOT_SSID], check=False)
    time.sleep(1)

    if not run_cmd([
        "nmcli", "connection", "add",
        "type", "wifi", "ifname", "wlan0",
        "con-name", HOTSPOT_SSID,
        "autoconnect", "no",
        "ssid", HOTSPOT_SSID
    ]):
        return False

    if not run_cmd([
        "nmcli", "connection", "modify", HOTSPOT_SSID,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless-security.key-mgmt", "wpa-psk",
        "802-11-wireless-security.psk", HOTSPOT_PASSWORD,
        "ipv4.method", "shared",
        "ipv4.addresses", f"{HOTSPOT_IP}/24",
    ]):
        return False

    return run_cmd(["nmcli", "connection", "up", HOTSPOT_SSID])

def stop_hotspot(reconnect=True):
    log("Stopping hotspot...")
    run_cmd(["nmcli", "connection", "down",   HOTSPOT_SSID], check=False)
    run_cmd(["nmcli", "connection", "delete", HOTSPOT_SSID], check=False)
    if reconnect:
        last = get_last_wifi()
        if last:
            log(f"Reconnecting to: {last}")
            run_cmd(["nmcli", "connection", "up", last], check=False)
            time.sleep(3)
        else:
            log("No saved WiFi to reconnect to")

def scan_wifi() -> list:
    log("Scanning WiFi...")
    try:
        run_cmd(["nmcli", "device", "wifi", "rescan"])
        time.sleep(3)
        r = subprocess.check_output(
            ['nmcli', '-t', '-f', 'SSID', 'dev', 'wifi', 'list']
        ).decode('utf-8')
        return sorted(set(
            line.strip() for line in r.splitlines()
            if line.strip() and line.strip() != HOTSPOT_SSID
        ))
    except Exception as e:
        log(f"Scan error: {e}")
        return []

def add_wifi_network(ssid, password) -> bool:
    log(f"Connecting to: {ssid}")
    if subprocess.run(
        ['nmcli', 'connection', 'show', ssid], capture_output=True
    ).returncode == 0:
        run_cmd(["nmcli", "connection", "delete", ssid], check=False)
        time.sleep(1)
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd.extend(["password", password])
    return run_cmd(cmd)

# --- Web Server ---
class ConfigHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress access log

    def do_GET(self):
        if self.path == '/':
            html_path = os.path.join(script_dir, "index.html")
            try:
                with open(html_path, "r") as f:
                    html = f.read()
                options = "".join(
                    f'<option value="{s}">{s}</option>'
                    for s in scan_wifi()
                )
                html = html.replace("<!--WIFI_OPTIONS-->", options)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            except FileNotFoundError:
                log(f"FATAL: index.html not found at {html_path}")
                self.wfile.write(b"Error: index.html not found")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/configure':
            length   = int(self.headers['Content-Length'])
            data     = self.rfile.read(length).decode('utf-8')
            params   = parse_qs(data)
            ssid     = params.get('ssid', [None])[0]
            password = params.get('password', [''])[0]
            if ssid:
                CREDENTIALS['ssid']     = ssid
                CREDENTIALS['password'] = password
                log(f"Credentials received: {ssid}")
                success_path = os.path.join(script_dir, "success.html")
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                try:
                    with open(success_path, "rb") as f:
                        self.wfile.write(f.read())
                except FileNotFoundError:
                    self.wfile.write(b"Configuration received. Rebooting.")
            else:
                self.send_error(400, "SSID not provided")
        else:
            self.send_error(404)

# --- Portal ---
def run_portal(led: LedController) -> bool:
    """
    Run captive web portal.
    Returns True  → credentials submitted → reboot follows.
    Returns False → cancelled by button → reconnect to previous.
    """
    global CREDENTIALS
    CREDENTIALS = {}

    if not start_hotspot():
        log("FATAL: could not start hotspot")
        return False

    led.start_pulse(BLUE)
    log(f"Portal active → connect to '{HOTSPOT_SSID}' / '{HOTSPOT_PASSWORD}' → http://{HOTSPOT_IP}")

    # Wait for button release before watching for cancel
    wait_for_button_release()

    cancelled = threading.Event()
    done      = threading.Event()

    def watch_cancel():
        time.sleep(0.5)  # debounce
        while not done.is_set():
            if is_button_pressed():
                log("Button — cancelling portal")
                cancelled.set()
                done.set()
                break
            time.sleep(0.1)

    threading.Thread(target=watch_cancel, daemon=True).start()

    httpd      = HTTPServer(('', 80), ConfigHTTPRequestHandler)
    httpd.timeout = 1
    start_time = time.time()

    while not done.is_set():
        httpd.handle_request()
        if CREDENTIALS:
            done.set()
        if (time.time() - start_time) > PORTAL_TIMEOUT_SECONDS:
            log("Portal timeout")
            done.set()

    httpd.server_close()
    led.stop_pulse()
    led_off()

    if cancelled.is_set():
        log("Portal cancelled — reconnecting to previous network")
        stop_hotspot(reconnect=True)
        return False

    stop_hotspot(reconnect=False)

    if CREDENTIALS:
        ssid     = CREDENTIALS['ssid']
        password = CREDENTIALS['password']
        if add_wifi_network(ssid, password):
            log("Verifying connection...")
            for i in range(15):
                if check_internet():
                    log(f"SUCCESS — rebooting")
                    time.sleep(3)
                    run_cmd(["reboot"], check=False)
                    return True
                log(f"Attempt {i+1}/15...")
                time.sleep(2)
            log("FAILED to verify — rebooting")
            run_cmd(["nmcli", "connection", "delete", ssid], check=False)
        else:
            log("Connection command failed — rebooting")
        time.sleep(3)
        run_cmd(["reboot"], check=False)
        return True

    return False

# --- Red blink: retry connection or launch portal on button ---
RED_BLINK_COUNT = 10

def _wait_button(duration, step=0.05) -> bool:
    """Sleep up to `duration` seconds, returning True early if button pressed."""
    elapsed = 0.0
    while elapsed < duration:
        if is_button_pressed():
            return True
        time.sleep(step)
        elapsed += step
    return False

def red_blink_cycle(led: LedController, blinks=RED_BLINK_COUNT) -> bool:
    """
    Blink red `blinks` times while watching for a button press.
    Returns True  → button pressed → caller should run the portal.
    Returns False → finished blinking → caller should retry the connection.
    """
    log(f"Red blink x{blinks} — press button for setup portal")
    wait_for_button_release()
    for i in range(blinks):
        led_all(RED)
        if _wait_button(0.5):
            led_off()
            log(f"Button pressed (blink {i+1}/{blinks})")
            time.sleep(0.2)
            return True
        led_off()
        if _wait_button(0.5):
            log(f"Button pressed (blink {i+1}/{blinks})")
            time.sleep(0.2)
            return True
    return False

# --- Main ---
def main():
    led = LedController()
    atexit.register(led.turn_off)
    atexit.register(stop_hotspot)

    led.startup_blink()

    # Button held at startup → portal immediately
    if is_button_pressed():
        log("Button held at startup → portal")
        if run_portal(led):
            return
        # Portal cancelled → fall through to red-blink loop below

    # WiFi OK → exit
    elif check_internet():
        log("WiFi OK — exiting")
        atexit.unregister(stop_hotspot)
        return

    else:
        log("No WiFi")

    # Red-blink loop: blink 10×, then retry the connection.
    # A button press during the blinking launches the setup portal.
    while True:
        if red_blink_cycle(led):
            # Button pressed → run portal
            if run_portal(led):
                return
            # Portal cancelled → back to red blink
        else:
            # Finished 10 blinks → retry connection (router may be back)
            log("Retrying connection...")
            last = get_last_wifi()
            if last:
                run_cmd(["nmcli", "connection", "up", last], check=False)
                time.sleep(3)
            if check_internet():
                log("WiFi reconnected — exiting")
                atexit.unregister(stop_hotspot)
                return
            log("Still no WiFi")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"FATAL: {e}")
        import traceback
        log(traceback.format_exc())
        stop_hotspot()