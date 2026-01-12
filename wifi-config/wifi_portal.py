#!/usr/bin/env python3
"""
A self-contained Wi-Fi configuration portal for a headless Raspberry Pi.

This script checks for an internet connection. If none is found, or if a
button is pressed, it creates a Wi-Fi hotspot and serves a web page to
allow a user to select a new network, enter credentials, and connect.
It uses NetworkManager for network control, gpiozero for button input,
and apa102_pi for LED feedback.
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

# Hardware-specific libraries
from gpiozero import Button
from apa102_pi.driver import apa102

# --- Configuration ---
HOTSPOT_SSID = "Chochko-WiFi-Setup"
HOTSPOT_PASSWORD = "chochko123"
HOTSPOT_IP = "192.168.4.1"
BUTTON_PINS = [12, 13]          # GPIO pins to force the hotspot
PORTAL_TIMEOUT_SECONDS = 120    # 2 minutes to wait for user input
CREDENTIALS = {}                # Dictionary to hold credentials from the web form
MAX_LOG_FILES = 10              # Maximum number of log files to keep

# --- Logging Setup ---
# To ensure logs are always in the correct user's home directory, we determine
# the path based on the script's location. This is reliable for both manual
# `sudo` execution and for the systemd service.
# It assumes the project is located in a user's home directory, e.g., /home/chochko/wifi-config/
script_dir = os.path.dirname(os.path.abspath(__file__))  # -> /home/chochko/wifi-config
user_home_dir = os.path.dirname(script_dir)              # -> /home/chochko

# A simple fallback if the script is not in the expected location (e.g. /usr/bin)
if not user_home_dir.startswith('/home'):
    user_home_dir = '/root'

LOG_DIR = os.path.join(user_home_dir, "logs", "chochko-wifi")
os.makedirs(LOG_DIR, exist_ok=True)
LOGFILE = os.path.join(LOG_DIR, f"portal-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log")

def log(message):
    """Prints a message and writes it to the log file."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    with open(LOGFILE, "a") as f:
        f.write(log_message + "\n")

def rotate_logs(log_directory, max_files):
    """Deletes the oldest log files if the number of logs exceeds max_files."""
    try:
        # Get a list of all log files in the directory
        log_files = [f for f in os.listdir(log_directory) if f.startswith('portal-') and f.endswith('.log')]
        
        # Sort the files by name (which works because of the timestamp format), oldest first
        log_files.sort()

        # If we have more files than we want to keep
        if len(log_files) > max_files:
            # Calculate how many to delete
            num_to_delete = len(log_files) - max_files
            logs_to_delete = log_files[:num_to_delete]
            
            log(f"LOGS: Found {len(log_files)} logs. Deleting {num_to_delete} old log(s) to keep {max_files}.")
            for file_to_delete in logs_to_delete:
                os.remove(os.path.join(log_directory, file_to_delete))
    except Exception as e:
        log(f"LOGS: An error occurred during log rotation: {e}")

# Clean up old logs at startup.
rotate_logs(LOG_DIR, MAX_LOG_FILES)

# --- LED Controller ---
BLUE = 0x0000FF         # Standard hex for blue.
class LedController:
    """Manages the APA102 LEDs for status feedback."""
    def __init__(self, num_leds=3, brightness=20):
        try:
            self.strip = apa102.APA102(num_led=num_leds, global_brightness=brightness, mosi=10, sclk=11, order='rgb')
            self.enabled = True
        except Exception as e:
            log(f"WARN: Could not initialize LEDs. Running without LED feedback. Error: {e}")
            self.enabled = False
        self._pulse_thread = None
        self._stop_event = threading.Event()

    def startup_blink(self):
        """A single blue blink to indicate the script has started."""
        if not self.enabled: return
        log("LED: Performing startup blink.")
        for i in range(self.strip.num_led):
            self.strip.set_pixel_rgb(i, BLUE)
        self.strip.show()
        time.sleep(1)
        self.strip.clear_strip()

    def _pulse_loop(self):
        """The loop for pulsing blue, run in a thread."""
        while not self._stop_event.is_set():
            for i in range(self.strip.num_led):
                self.strip.set_pixel_rgb(i, BLUE)
            self.strip.show()
            if self._stop_event.wait(0.5): break
            self.strip.clear_strip()
            if self._stop_event.wait(0.5): break

    def start_pulse(self):
        """Starts the blue pulse in a background thread."""
        if not self.enabled: return
        if self._pulse_thread and self._pulse_thread.is_alive():
            return
        self._stop_event.clear()
        self._pulse_thread = threading.Thread(target=self._pulse_loop)
        self._pulse_thread.daemon = True
        self._pulse_thread.start()
        log("LED: Started blue pulse for hotspot mode.")

    def turn_off(self):
        """Stops any animation and turns all LEDs off."""
        if not self.enabled: return
        log("LED: Turning off.")
        if self._pulse_thread and self._pulse_thread.is_alive():
            self._stop_event.set()
            self._pulse_thread.join(timeout=1.5)
        self.strip.clear_strip()
        self.strip.cleanup()

# --- GPIO & System Functions ---
try:
    buttons = [Button(pin, pull_up=True) for pin in BUTTON_PINS]
    log(f"GPIO: Buttons initialized on pins: {BUTTON_PINS}")
except Exception as e:
    log(f"WARN: Could not initialize GPIO. Hotspot forcing will be disabled. Error: {e}")
    buttons = []

def is_force_hotspot_active():
    """Check if any of the designated buttons are pressed."""
    return any(button.is_pressed for button in buttons)

def run_cmd(command, check=True):
    """Helper to run shell commands safely and log results."""
    log(f"CMD: {' '.join(command)}")
    try:
        result = subprocess.run(command, check=check, capture_output=True, text=True, timeout=30)
        if result.stdout: log(f"  STDOUT: {result.stdout.strip()}")
        if result.stderr: log(f"  STDERR: {result.stderr.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        log(f"  ERROR: Command failed with exit code {e.returncode}")
        if e.stdout: log(f"  STDOUT: {e.stdout.strip()}")
        if e.stderr: log(f"  STDERR: {e.stderr.strip()}")
        return False
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as e:
        log(f"  ERROR: Command failed with system error: {e}")
        return False

def check_internet(host="8.8.8.8", port=53, timeout=3):
    """Check for a live internet connection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
        log("Internet connection detected.")
        return True
    except (socket.error, socket.timeout):
        log("No internet connection.")
        return False

# --- Network Functions (NetworkManager) ---
def start_hotspot():
    """Creates and activates a Wi-Fi hotspot."""
    log("Starting hotspot...")
    run_cmd(["nmcli", "device", "disconnect", "wlan0"], check=False)
    time.sleep(1)
    run_cmd(["nmcli", "connection", "delete", HOTSPOT_SSID], check=False)
    time.sleep(1)

    add_cmd = ["nmcli", "connection", "add", "type", "wifi", "ifname", "wlan0", "con-name", HOTSPOT_SSID, "autoconnect", "no", "ssid", HOTSPOT_SSID]
    if not run_cmd(add_cmd):
        log("FATAL: Failed to create base hotspot profile.")
        return False

    modify_cmd = [
        "nmcli", "connection", "modify", HOTSPOT_SSID,
        "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
        "802-11-wireless-security.key-mgmt", "wpa-psk",
        "802-11-wireless-security.psk", HOTSPOT_PASSWORD,
        "ipv4.method", "shared", "ipv4.addresses", f"{HOTSPOT_IP}/24",
    ]
    if not run_cmd(modify_cmd):
        log("FATAL: Failed to configure hotspot settings.")
        return False

    return run_cmd(["nmcli", "connection", "up", HOTSPOT_SSID])

def stop_hotspot():
    """Deactivates and removes the hotspot connection."""
    log("Stopping hotspot...")
    run_cmd(["nmcli", "connection", "down", HOTSPOT_SSID], check=False)
    run_cmd(["nmcli", "connection", "delete", HOTSPOT_SSID], check=False)

def add_wifi_network(ssid, password):
    """
    Connects to a new Wi-Fi network.
    
    If a profile for the SSID already exists, it is deleted first to ensure
    a clean connection attempt with the new credentials.
    """
    log(f"Configuring connection for SSID: {ssid}")

    # Check if a connection profile with this name already exists.
    # We run this silently (without our logging helper) to avoid cluttering the log.
    if subprocess.run(['nmcli', 'connection', 'show', ssid], capture_output=True).returncode == 0:
        log(f"An existing profile for '{ssid}' was found. Deleting it for a clean setup.")
        run_cmd(["nmcli", "connection", "delete", ssid], check=False)
        time.sleep(1)
    
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd.extend(["password", password])

    return run_cmd(cmd)

def scan_wifi_networks():
    """Scans for Wi-Fi networks and returns a list of unique SSIDs."""
    log("Scanning for Wi-Fi networks...")
    try:
        # Rescan to get the freshest list
        run_cmd(["nmcli", "device", "wifi", "rescan"])
        time.sleep(3) # Give rescan time to complete
        result = subprocess.check_output(['nmcli', '-t', '-f', 'SSID', 'dev', 'wifi', 'list']).decode('utf-8')
        all_ssids = set(line.strip() for line in result.splitlines() if line.strip())
        return sorted([s for s in all_ssids if s != HOTSPOT_SSID])
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log(f"Error scanning for Wi-Fi networks: {e}")
        return []

# --- Web Server Logic ---
class ConfigHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handles web requests to serve the config page and receive credentials."""
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            # Construct an absolute path to index.html relative to this script's location
            # to ensure it's found regardless of the script's working directory.
            script_dir = os.path.dirname(os.path.abspath(__file__))
            html_path = os.path.join(script_dir, "index.html")
            try:
                with open(html_path, "r") as f:
                    html = f.read()
                
                ssids = scan_wifi_networks()
                options_html = "".join(f'<option value="{ssid}">{ssid}</option>' for ssid in ssids)
                html = html.replace("<!--WIFI_OPTIONS-->", options_html)
                self.wfile.write(html.encode("utf-8"))
            except FileNotFoundError:
                log(f"FATAL: index.html not found. Looked for it at: {html_path}")
                self.wfile.write(b"Error: index.html not found. Cannot configure device.")
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == '/configure':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = parse_qs(post_data)
            
            ssid = params.get('ssid', [None])[0]
            password = params.get('password', [''])[0]

            if ssid:
                CREDENTIALS['ssid'] = ssid
                CREDENTIALS['password'] = password
                log(f"Credentials received for SSID: {ssid}")
                # Serve a dedicated, well-formatted success page.
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                script_dir = os.path.dirname(os.path.abspath(__file__))
                success_html_path = os.path.join(script_dir, "success.html")
                try:
                    with open(success_html_path, "rb") as f:
                        self.wfile.write(f.read())
                except FileNotFoundError:
                    log(f"FATAL: success.html not found at {success_html_path}")
                    self.wfile.write(b"Configuration received. Rebooting.") # Fallback message
            else:
                self.send_error(400, "SSID not provided")
        else:
            self.send_error(404, "Not Found")

# --- Main Execution Block ---
def main():
    """Main script logic."""
    led_controller = LedController()
    atexit.register(led_controller.turn_off)

    led_controller.startup_blink()

    if not is_force_hotspot_active() and check_internet():
        log("Exiting: Internet connection is active and hotspot is not forced.")
        return

    log("Starting configuration portal...")
    atexit.register(stop_hotspot)
    
    if not start_hotspot():
        log("FATAL: Could not start hotspot. Please check logs. Exiting.")
        return
        
    led_controller.start_pulse()
    httpd = HTTPServer(('', 80), ConfigHTTPRequestHandler)
    httpd.timeout = 1 # Set a timeout for handle_request() to be non-blocking
    
    log(f"Web server started at http://{HOTSPOT_IP}. Waiting for configuration...")
    start_time = time.time()
    while (time.time() - start_time) < PORTAL_TIMEOUT_SECONDS:
        httpd.handle_request()
        if CREDENTIALS:
            break
    
    httpd.server_close()

    if CREDENTIALS:
        log("Web server stopped. Credentials received.")
    else:
        log(f"Web server timed out after {PORTAL_TIMEOUT_SECONDS} seconds. No credentials received.")
    
    stop_hotspot()
    atexit.unregister(stop_hotspot)

    new_ssid = CREDENTIALS.get('ssid')
    new_password = CREDENTIALS.get('password')

    if new_ssid:
        if add_wifi_network(new_ssid, new_password):
            log("Connection command sent. Verifying internet access for up to 30 seconds...")
            
            connection_verified = False
            # Try to verify the connection for 30 seconds (15 attempts * 2s sleep)
            for i in range(15):
                if check_internet():
                    log("SUCCESS: New network connection verified.")
                    connection_verified = True
                    break
                log(f"Verification attempt {i+1}/15 failed. Retrying...")
                time.sleep(2)

            if connection_verified:
                log("Rebooting to make the new connection permanent.")
            else:
                log("FAILED: Could not verify internet on the new network.")
                log(f"Deleting failed profile '{new_ssid}' to prevent connection loops.")
                run_cmd(["nmcli", "connection", "delete", new_ssid], check=False)
                log("Rebooting. The portal will restart on boot.")
        else:
            log(f"FAILED: The 'nmcli connect' command for '{new_ssid}' failed.")
            log("Rebooting. The portal will restart on boot.")
        
        time.sleep(3)
        run_cmd(["reboot"], check=False)
    else:
        log(f"Portal timed out or was closed without submission. Shutting down the device.")
        time.sleep(3) # A small delay to ensure the log is written to disk.
        run_cmd(["poweroff"], check=False)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"FATAL: An unhandled exception occurred: {e}")
        # Attempt a safe shutdown
        stop_hotspot()
