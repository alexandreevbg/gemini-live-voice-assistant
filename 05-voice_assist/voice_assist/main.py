# main.py
#
# Voice Assistant project
#
import logging

# ── Logging configuration ──────────────────────────────────────────
DEBUG = False   # Set to True for full debug output with timestamps

class LevelFormatter(logging.Formatter):
    """
    DEBUG=False: INFO → message only, WARNING/ERROR → with timestamp
    DEBUG=True:  all messages → full format with timestamp
    """
    _simple = logging.Formatter('%(message)s')
    _full   = logging.Formatter(
        '%(asctime)s %(levelname)-8s %(name)s: %(message)s'
    )

    def format(self, record):
        if not DEBUG and record.levelno == logging.INFO:
            return self._simple.format(record)
        return self._full.format(record)

_handler = logging.StreamHandler()
_handler.setFormatter(LevelFormatter())
logging.getLogger().setLevel(logging.DEBUG if DEBUG else logging.INFO)
logging.getLogger().addHandler(logging.NullHandler())  # suppress default
logging.getLogger().addHandler(_handler)

log = logging.getLogger(__name__)

import asyncio
import signal
import subprocess
import numpy as np

import config
import leds
import chimes
from capture import MicCapture
from playback import Speaker
from wakeword import WakeWordDetector
from gemini import GeminiLiveClient
from spotify import SpotifyController
from smarthome import SmartHome
from button import Button

class VoiceAssistant:
    def __init__(self):
        self.state   = 'IDLE'
        self.loop    = None

        self.mic      = MicCapture()
        self.speaker  = Speaker()

        self.wakeword = WakeWordDetector(
            model_path=config.WAKEWORD_MODEL,
            threshold=config.WAKEWORD_THRESH
        )
        self.button   = Button()
        self.gemini   = None
        self.spotify  = SpotifyController()
        self.smarthome = SmartHome()

        self._dialog_task    = None
        self._end_event      = None
        self._last_activity  = 0.0
        self._gemini_speaking = False
        self._end_after_turn = False
        self._volume         = 100
        self._VOLUME_STEP    = 15

    def setup(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

        # Build system prompt with location — called once at startup
        try:
            import location as loc_module
            loc     = loc_module.get_current()
            loc_str = loc_module.format_for_prompt(loc)
            config.GEMINI_SYSTEM += loc_str
            log.info(f'Location: {loc_str}')
        except Exception as e:
            log.warning(f'Location unavailable: {e}')

        self.wakeword.set_loop(loop)
        self.wakeword.set_on_detect(self._on_wake)

        self.button.set_loop(loop)
        self.button.set_on_press(self._on_wake)

        self.speaker.start()
        chimes.set_speaker(self.speaker)

        self.mic.start()
        self.button.start()

        self.smarthome.connect()
        if self.smarthome.connected:
            log.info('Home Assistant ready')
        else:
            log.info('Home Assistant not available')

        self.spotify.connect()
        if self.spotify.connected:
            log.info('Spotify ready')
        else:
            log.info('Spotify not available')

        log.info('VoiceAssistant ready')

    def teardown(self):
        log.info('Shutting down...')
        self.mic.stop()
        self.speaker.stop()
        self.button.stop()
        leds.off()
        log.info('Shutdown complete')

    # ── IDLE ──────────────────────────────────────────────────────────

    def enter_idle(self):
        self.state = 'IDLE'
        log.info('State: IDLE')
        self.mic.clear_consumers()
        self.mic.add_consumer(self._wakeword_consumer)
        self.button.set_on_press(self._on_wake)
        leds.idle()

    def _wakeword_consumer(self, pcm_i16: np.ndarray):
        self.wakeword.process(pcm_i16)
        
    def _on_gemini_audio_consumer(self, pcm_i16: np.ndarray):
        """Mic consumer during dialog — resets timeout while user speaks."""
        if self.gemini is None:
            return
        self.gemini.send_audio(pcm_i16)

    def _on_wake(self):
        if self.state != 'IDLE':
            log.info('Wake ignored — already in DIALOG')
            return
        log.info('Wake word detected!')
        self._dialog_task = asyncio.create_task(self._run_dialog())

    # ── DIALOG ────────────────────────────────────────────────────────

    async def _run_dialog(self):
        self.state         = 'DIALOG'
        self._dialog_start = self.loop.time()
        self._end_event    = asyncio.Event()
        self._end_after_turn = False
        log.info('State: DIALOG')

        # Set button to end dialog IMMEDIATELY
        self.button.set_on_press(self._request_end_dialog)

        # Play chime first
        chimes.wake_detected()
        leds.dialog()

        # Duck Spotify — run in thread with timeout
        if self.spotify.connected:
            try:
                current = await asyncio.wait_for(
                    self.loop.run_in_executor(None, self.spotify.get_current),
                    timeout=3.0
                )
                if current and current.get('playing'):
                    await self.loop.run_in_executor(
                        None, self.spotify.set_volume, 75
                    )
            except asyncio.TimeoutError:
                log.warning('Spotify timeout — skipping duck')
            except Exception as e:
                log.warning(f'Spotify error — skipping duck: {e}')

        ha_devices = self.smarthome.list_devices() if self.smarthome.connected else []

        self.gemini = GeminiLiveClient(
            on_audio=self._on_gemini_audio,
            on_turn_complete=self._on_turn_complete,
            on_interrupted=self._on_interrupted,
            on_text=self._on_gemini_text,
            on_tool_call=self._on_tool_call,
            spotify_connected=self.spotify.connected,
            ha_connected=self.smarthome.connected,
            ha_devices=ha_devices,
        )

        try:
            await asyncio.wait_for(self.gemini.connect(), timeout=10.0)
            log.info('Gemini connected')
            self.mic.clear_consumers()
            self.mic.add_consumer(self._on_gemini_audio_consumer)
            await self._dialog_loop()

        except asyncio.TimeoutError:
            log.error('Gemini connect timeout')
            chimes.error()
            leds.error()
            await asyncio.sleep(1)

        except Exception as e:
            log.error(f'Dialog error: {e}')
            chimes.error()
            leds.error()
            await asyncio.sleep(1)

        finally:
            await self._end_dialog()

    async def _dialog_loop(self):
        """Keep dialog alive until button, timeout, or turnComplete signal."""
        WATCHDOG = 120  # absolute maximum 2 minutes
        
        self._last_activity   = self.loop.time()
        self._gemini_speaking = False

        while not self._end_event.is_set():
            await asyncio.sleep(0.5)
            now  = self.loop.time()
            idle = now - self._last_activity

            # Watchdog
            if now - self._dialog_start > WATCHDOG:
                log.warning('Dialog watchdog — forcing IDLE')
                break

            # Timeout only when Gemini not speaking
            if not self._gemini_speaking:
                if idle > config.DIALOG_TIMEOUT:
                    log.info(f'Dialog timeout after {config.DIALOG_TIMEOUT}s')
                    break

    def _request_end_dialog(self):
        log.info('Button pressed — ending dialog')
        if self._end_event:
            self._end_event.set()
        else:
            log.warning('_end_event is None — scheduling force idle')
            asyncio.create_task(self._force_idle())

    async def _force_idle(self):
        """Emergency recovery if _end_event missing."""
        log.warning('Force idle recovery')
        if self.gemini:
            await self.gemini.disconnect()
            self.gemini = None
        self.speaker.clear()
        self.mic.set_mute(False)
        chimes.dialog_ended()
        self.wakeword.reset(cooldown=1.0)
        await asyncio.sleep(1.0)
        self.enter_idle()

    def _on_gemini_audio(self, pcm_24k: bytes):
        self._gemini_speaking = True
        self._last_activity   = self.loop.time()
        self.speaker.play_gemini(pcm_24k)

    def _on_turn_complete(self):
        self._gemini_speaking = False
        self._last_activity   = self.loop.time()
        log.info('Gemini turn complete — listening...')
        if self._end_after_turn:
            self._end_after_turn = False
            if self._end_event:
                self._end_event.set()

    def _on_interrupted(self):
        self._gemini_speaking = False
        self.speaker.clear()
        self._last_activity = self.loop.time()
        log.info('Gemini interrupted by user')

    def _on_gemini_text(self, text: str):
        log.info(f'Gemini: {text}')

    def _on_tool_call(self, calls: list):
        responses  = []
        scheduling = None

        for call in calls:
            name    = call.get('name', '')
            args    = call.get('args', {})
            call_id = call.get('id', '')
            result  = 'OK'

            if name == 'set_address':
                import location
                loc     = location.get_current()
                address = args.get('address', '')
                location.save_address(address, loc['country'], loc['town'])
                log.info(f'Address saved: {address}')
                result = 'Адресът е запазен.'

            elif name == 'set_volume':
                action = args.get('action', '').lower()
                result = self._handle_volume(action)

            elif name == 'get_weather':
                import weather, location
                town = args.get('town', '')
                if not town:
                    loc     = location.get_current()
                    town    = loc.get('town', '')
                    country = loc.get('country', '')
                else:
                    country = ''
                w      = weather.get_weather(town, country)
                result = weather.format_for_gemini(w)
                log.info(f'Weather: {result}')

            elif name == 'play_music':
                query = args.get('query', '')
                self.loop.run_in_executor(None, self.spotify.play, query)
                result               = f'Пускам {query}' if query else 'Продължавам музиката.'
                self._end_after_turn = True

            elif name == 'next_track':      
                self.loop.run_in_executor(None, self.spotify.next_track)
                result               = 'Следваща песен.'
                self._end_after_turn = True   # end after Gemini confirms

            elif name == 'previous_track':
                self.loop.run_in_executor(None, self.spotify.previous_track)
                result               = 'Предишна песен.'
                self._end_after_turn = True

            elif name == 'pause_music':
                self.loop.run_in_executor(None, self.spotify.pause)
                result               = 'Музиката е на пауза.'
                self._end_after_turn = True

            elif name == 'resume_music':
                self.loop.run_in_executor(None, self.spotify.resume)
                result               = 'Продължавам музиката.'
                self._end_after_turn = True

            elif name == 'transfer_music':
                device_name          = args.get('device_name', '')
                result               = self.spotify.transfer(device_name)
                self._end_after_turn = True

            elif name == 'end_dialog':
                result               = 'Дочуване!'
                self._end_after_turn = True
                scheduling           = 'WHEN_IDLE'

            elif name == 'ha_control':
                result = self._handle_ha(args)
                scheduling = 'INTERRUPT'

            log.info(f'Tool {name}: {result}')
            responses.append({
                'id':     call_id,
                'name':   name,
                'result': result
            })

        if self.gemini and responses:
            self.gemini.send_tool_responses(responses)

    def _handle_volume(self, action: str) -> str:
        def set_master(pct: int) -> int:
            pct = max(0, min(100, pct))
            subprocess.run(
                ['amixer', 'sset', 'Master', f'{pct}%'],
                capture_output=True
            )
            self._volume = pct
            log.info(f'Volume: {pct}%')
            return pct

        if action == 'louder':
            v = set_master(self._volume + self._VOLUME_STEP)
            return f'Звукът е увеличен на {v}%.'
        elif action == 'quieter':
            v = set_master(self._volume - self._VOLUME_STEP)
            return f'Звукът е намален на {v}%.'
        elif action == 'max':
            set_master(100)
            return 'Максимален звук.'
        elif action == 'mute':
            subprocess.run(['amixer', 'sset', 'Master', '0%'],
                           capture_output=True)
            return 'Звукът е изключен.'
        elif action == 'unmute':
            v = set_master(self._volume)
            return f'Звукът е включен на {v}%.'
        return 'Непозната команда за звук.'

    def _handle_ha(self, args: dict) -> str:
        return self.smarthome.control(
            action      = args.get('action', ''),
            entity_name = args.get('entity_name', ''),
            brightness  = args.get('brightness'),
            color       = args.get('color'),
            temperature = args.get('temperature'),
        )

    async def _end_dialog(self):
        log.info('Ending dialog...')

        # Clear mic consumers FIRST — prevents further send_audio calls
        self.mic.clear_consumers()

        if self.gemini:
            await self.gemini.disconnect()
            self.gemini = None

        self.speaker.clear()

        # Restore Spotify volume
        if self.spotify.connected:
            try:
                await asyncio.wait_for(
                    self.loop.run_in_executor(None, self.spotify.set_volume, 100),
                    timeout=3.0
                )
            except Exception:
                pass

        chimes.dialog_ended()
        self.wakeword.reset(cooldown=1.0)
        await asyncio.sleep(1.0)

        log.info('Dialog ended')
        self.enter_idle()

    # ── MAIN ──────────────────────────────────────────────────────────

    async def run(self):
        self.enter_idle()
        log.info('Чочко ready — say the wake word or press the button')

        stop = asyncio.Event()
        self.loop.add_signal_handler(signal.SIGINT,  stop.set)
        self.loop.add_signal_handler(signal.SIGTERM, stop.set)
        await stop.wait()


async def main():
    assistant = VoiceAssistant()
    loop      = asyncio.get_event_loop()
    assistant.setup(loop)
    try:
        await assistant.run()
    finally:
        assistant.teardown()


if __name__ == '__main__':
    asyncio.run(main())