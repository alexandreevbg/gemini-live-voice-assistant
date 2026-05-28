"""
ReSpeaker 2-mic button handler.
Button press triggers wake word detection manually.
GPIO17, active LOW with internal pull-up.
"""
import logging
import asyncio

log = logging.getLogger(__name__)
BUTTON_PIN = 17

try:
    import RPi.GPIO as GPIO
    _HAS_GPIO = True
except ImportError:
    _HAS_GPIO = False
    log.warning("RPi.GPIO not available — button disabled")

class Button:
    def __init__(self):
        self._on_press = None
        self._loop     = None
        self._active   = False

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_on_press(self, fn):
        self._on_press = fn

    def start(self):
        if not _HAS_GPIO:
            log.warning("Button disabled — no GPIO")
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(
            BUTTON_PIN,
            GPIO.FALLING,
            callback=self._pressed,
            bouncetime=300
        )
        self._active = True
        log.info(f"Button ready on GPIO{BUTTON_PIN}")

    def stop(self):
        if not _HAS_GPIO or not self._active:
            return
        try:
            GPIO.remove_event_detect(BUTTON_PIN)
        except Exception as e:
            log.warning(f"remove_event_detect: {e}")
        try:
            GPIO.cleanup()
        except Exception as e:
            log.warning(f"GPIO.cleanup: {e}")
        self._active = False
        log.info("Button stopped")

    def _pressed(self, channel):
        log.debug(f"Button pressed on GPIO{channel}")
        if self._on_press and self._loop:
            self._loop.call_soon_threadsafe(self._on_press)