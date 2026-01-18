import logging
from gpiozero import Button, GPIOZeroError
from apa102_pi.driver import apa102
from typing import TYPE_CHECKING
import time
from .audio import AudioMode

# --- LED colors ---
RED = 0xFF0000
BLUE = 0x0000FF
GREEN = 0x00FF00
YELLOW = 0xFFFF00
VIOLET = 0xFF00FF

# This is to avoid circular imports, but still get type hints
if TYPE_CHECKING:
    from .audio import AudioProcessor
    from .gemini_live import GeminiClient

_LOGGER = logging.getLogger(__name__)

# --- Global button objects to be managed ---
_button_left: Button | None = None
_button_right: Button | None = None
_led_strip = None
NUM_LEDS = 3

def init_leds():
    """Sets up the RGB LED."""
    global _led_strip
    try:
        _led_strip = apa102.APA102(num_led=NUM_LEDS)
        _led_strip.clear_strip()
        _LOGGER.info(f"APA102 LEDs initialized ({NUM_LEDS} LEDs)")
    except Exception as e:
        _LOGGER.error(f"Failed to setup LED: {e}")

def set_led_mode(mode: AudioMode):
    """Sets the LED color/behavior based on the AudioMode."""
    _LOGGER.info(f"Switching to {mode}.")

    if mode == AudioMode.WAKE_WORD:
        # Blink RED once
        for i in range(NUM_LEDS):
            _led_strip.set_pixel_rgb(i, RED)
        _led_strip.show()
        time.sleep(0.2)
        _led_strip.clear_strip()
        _led_strip.show()
    elif mode == AudioMode.LISTENING:
        for i in range(NUM_LEDS):
            _led_strip.set_pixel_rgb(i, GREEN)
        _led_strip.show()
    elif mode == AudioMode.RESPONSE:
        for i in range(NUM_LEDS):
            _led_strip.set_pixel_rgb(i, BLUE)
        _led_strip.show()
    elif mode == AudioMode.EXECUTE:
        for i in range(NUM_LEDS):
            _led_strip.set_pixel_rgb(i, YELLOW)
        _led_strip.show()

def init_buttons(audio_processor: 'AudioProcessor', gemini_client: 'GeminiClient'):
    """
    Sets up GPIO pins for button presses using gpiozero and assigns callbacks.
    """
    global _button_left, _button_right

    def on_left_press():
        """Callback for the left button press (GPIO 12)."""
        # A small delay to allow the other button's state to be reliably read
        time.sleep(0.05)
        
        if _button_right and _button_right.is_pressed:
            _LOGGER.info("Both buttons pressed: Stopping Gemini and switching to WAKE_WORD.")
            gemini_client.stop_session()
            audio_processor.switch_to_wake_word()
        else:
            _LOGGER.debug("Left button pressed.")
            current_mode = audio_processor.get_mode()
            _LOGGER.debug(f"Current audio mode is {current_mode.name}")

            if current_mode == AudioMode.WAKE_WORD:
                _LOGGER.info("Left button: Manually activating Gemini.")
                audio_processor.switch_to_listening()
                gemini_client.start_session()
            elif current_mode == AudioMode.LISTENING or current_mode == AudioMode.RESPONSE:
                _LOGGER.info("Left button: Decreasing volume.")
                audio_processor.quieter()

    def on_right_press():
        """Callback for the right button press (GPIO 13)."""
        # A small delay to allow the other button's state to be reliably read
        time.sleep(0.05)
        
        # If the left button is also pressed, do nothing.
        # The 'on_left_press' handler is responsible for the "both pressed" action.
        if _button_left and _button_left.is_pressed:
            _LOGGER.debug("Right button pressed, but left is also pressed. Ignoring right press.")
            return
        else: # This is a single right press
            _LOGGER.debug("Right button pressed.")
            current_mode = audio_processor.get_mode()
            _LOGGER.debug(f"Current audio mode is {current_mode.name}")

            if current_mode == AudioMode.WAKE_WORD:
                _LOGGER.info("Right button: Manually activating Gemini.")
                audio_processor.switch_to_listening()
                gemini_client.start_session()
            elif current_mode == AudioMode.LISTENING or current_mode == AudioMode.RESPONSE:
                _LOGGER.info("Right button: Increasing volume.")
                audio_processor.louder()

    try:
        _button_left = Button(12, pull_up=True, bounce_time=0.1)
        _button_left.when_pressed = on_left_press
        _LOGGER.info("Button handler set up for GPIO 12 (Left)")

        _button_right = Button(13, pull_up=True, bounce_time=0.1)
        _button_right.when_pressed = on_right_press
        _LOGGER.info("Button handler set up for GPIO 13 (Right)")

    except GPIOZeroError as e:
        _LOGGER.error(f"gpiozero error during setup: {e}. Please ensure you are running on a Raspberry Pi with correct permissions.")
    except Exception as e:
        _LOGGER.exception(f"An unexpected error occurred during button setup: {e}")

def cleanup_gpio():
    """Cleans up GPIO resources by closing the button objects."""
    global _button_left, _button_right, _led_strip
    _LOGGER.debug("Cleaning up GPIO resources.")
    if _button_left:
        _button_left.close()
        _button_left = None
    if _button_right:
        _button_right.close()
        _button_right = None
    if _led_strip:
        _led_strip.clear_strip()
        _led_strip.cleanup()
        _led_strip = None
    _LOGGER.info("GPIO cleanup complete.")
