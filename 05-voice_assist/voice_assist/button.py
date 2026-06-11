"""
ReSpeaker 2-mic button handler.
Button press triggers wake word detection manually.
GPIO17, active LOW with internal pull-up.

Reads the button by POLLING gpiozero's `is_pressed` in a background thread —
the same approach wifi_portal.py uses, and the one that actually works on
Raspberry Pi OS Bookworm. Edge-driven callbacks (RPi.GPIO add_event_detect, and
even gpiozero's when_pressed via lgpio) are unreliable on this kernel: RPi.GPIO
raises "Failed to add edge detection", and gpiozero's edge callback can silently
never fire while level reads still work. Polling sidesteps both.
"""
import logging
import asyncio
import threading

log = logging.getLogger(__name__)
BUTTON_PIN = 17

try:
    from gpiozero import Button as _GZButton
    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False
    log.warning("gpiozero not available — button disabled")

class Button:
    def __init__(self):
        self._on_press = None
        self._loop     = None
        self._button   = None
        self._stop     = None
        self._thread   = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_on_press(self, fn):
        self._on_press = fn

    def start(self):
        if not _HAS_GPIO:
            log.warning("Button disabled — no GPIO")
            return
        # pull_up=True → pressed pulls the line LOW (active LOW).
        self._button = _GZButton(BUTTON_PIN, pull_up=True)
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info(f"Button ready on GPIO{BUTTON_PIN} (polling)")

    def _poll_loop(self):
        """Fire on the release→press edge; debounce 300ms after each press."""
        was_pressed = False
        while not self._stop.is_set():
            pressed = self._button.is_pressed
            if pressed and not was_pressed:
                self._fire()
                self._stop.wait(0.3)      # debounce
            was_pressed = pressed
            self._stop.wait(0.02)         # ~50 Hz poll

    def _fire(self):
        log.info(f"Button pressed on GPIO{BUTTON_PIN}")
        if self._on_press and self._loop:
            self._loop.call_soon_threadsafe(self._on_press)

    def stop(self):
        if self._stop:
            self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        if self._button:
            try:
                self._button.close()
            except Exception as e:
                log.warning(f"Button close: {e}")
            self._button = None
        log.info("Button stopped")
