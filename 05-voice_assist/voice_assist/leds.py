"""
APA102 LED control for ReSpeaker 2-mic v2.0.
3 LEDs on SPI0.
IDLE: dim blue, DIALOG: magenta.
"""
import logging

log = logging.getLogger(__name__)
N_LEDS = 3

try:
    import spidev
    _spi = spidev.SpiDev()
    _spi.open(0, 0)
    _spi.max_speed_hz = 1000000
    _HAS_SPI = True
    log.info("APA102 LEDs initialized")
except Exception as e:
    _HAS_SPI = False
    log.warning(f"LEDs not available: {e}")

def _write(pixels: list):
    if not _HAS_SPI:
        return
    buf = [0]*4
    for r,g,b in pixels:
        buf += [0xFF, b, g, r]   # APA102: BGR
    buf += [0xFF]*4
    _spi.xfer2(buf)

def _all(r: int, g: int, b: int):
    _write([(r,g,b)] * N_LEDS)

def off():
    _all(0, 0, 0)

def idle():
    """Dim blue — waiting for wake word."""
    _all(0, 0, 20)

def dialog():
    """Magenta — dialog active."""
    _all(80, 0, 80)

def error():
    """Magenta fast blink — error/timeout."""
    import time
    for _ in range(3):
        _all(80, 0, 80)
        time.sleep(0.15)
        off()
        time.sleep(0.1)
    idle()