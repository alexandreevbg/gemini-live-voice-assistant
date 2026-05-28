import asyncio
import base64
import json
import logging
import os
import numpy as np
import websockets
import config

log = logging.getLogger(__name__)

GEMINI_WS = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1beta.'
    'GenerativeService.BidiGenerateContent'
)

class GeminiLiveClient:
    def __init__(self, on_audio, on_turn_complete,
                 on_interrupted=None, on_text=None, on_tool_call=None,
                 spotify_connected=False, ha_connected=False, ha_devices=None):
        self._on_audio          = on_audio
        self._on_turn_complete  = on_turn_complete
        self._on_interrupted    = on_interrupted
        self._on_text           = on_text
        self._on_tool_call      = on_tool_call
        self._spotify_connected = spotify_connected
        self._ha_connected      = ha_connected
        self._ha_devices = ha_devices or []
        self._ws                = None
        self._send_queue        = None
        self._running           = False

    def _build_setup(self) -> dict:
        tools = []

        # set_address — always, BLOCKING
        tools.append({
            'function_declarations': [{
                'name': 'set_address',
                'description': 'Запазва домашния адрес на потребителя за текущия град',
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'address': {
                            'type': 'STRING',
                            'description': 'Пълен адрес — улица и номер'
                        }
                    },
                    'required': ['address']
                }
            }]
        })

        # set_volume — always, BLOCKING (fast local call)
        tools.append({
            'function_declarations': [{
                'name': 'set_volume',
                'description': (
                    'Управлява силата на звука. '
                    'Използвай когато потребителят каже: '
                    'по-силно, по-тихо, увеличи звука, намали звука, '
                    'максимален звук, без звук, заглуши.'
                ),
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {
                        'action': {
                            'type': 'STRING',
                            'description': 'louder, quieter, max, mute, unmute'
                        }
                    },
                    'required': ['action']
                }
            }]
        })

        # end_dialog — always, BLOCKING
        tools.append({
            'function_declarations': [{
                'name': 'end_dialog',
                'description': (
                    'Приключва разговора и се връща в режим на изчакване. '
                    'Използвай когато потребителят каже: '
                    'чао, това е, дочуване, край, стоп, спри, благодаря, довиждане.'
                ),
                'parameters': {
                    'type': 'OBJECT',
                    'properties': {}
                }
            }]
        })

        # Spotify — NON_BLOCKING + INTERRUPT (only if connected)
        if self._spotify_connected:
            tools.append({
                'function_declarations': [{
                    'name': 'play_music',
                    'description': 'Пусни музика в Spotify',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'query': {
                                'type': 'STRING',
                                'description': 'Изпълнител, песен или плейлист. Ако е празно — продължи.'
                            }
                        }
                    },
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'next_track',
                    'description': 'Следваща песен в Spotify',
                    'parameters': {'type': 'OBJECT', 'properties': {}},
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'previous_track',
                    'description': 'Предишна песен в Spotify',
                    'parameters': {'type': 'OBJECT', 'properties': {}},
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'pause_music',
                    'description': 'Паузирай музиката в Spotify',
                    'parameters': {'type': 'OBJECT', 'properties': {}},
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'resume_music',
                    'description': 'Продължи музиката в Spotify',
                    'parameters': {'type': 'OBJECT', 'properties': {}},
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'transfer_music',
                    'description': (
                        'Прехвърля музиката към друго Spotify устройство. '
                        'Използвай когато потребителят каже: '
                        'пусни на телевизора, прехвърли на Marantz, '
                        'пусни на телефона, смени устройството.'
                    ),
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'device_name': {
                                'type': 'STRING',
                                'description': 'Name of target Spotify device e.g. Marantz, TV, phone'
                            }
                        },
                        'required': ['device_name']
                    },
                    'behavior': 'NON_BLOCKING'
                }, {
                    'name': 'list_devices',
                    'description': 'Показва наличните Spotify устройства.',
                    'parameters': {'type': 'OBJECT', 'properties': {}},
                    'behavior': 'NON_BLOCKING'
                }]
            })
            log.info('Spotify tools enabled')
        else:
            log.info('Spotify tools disabled')

        # Weather — BLOCKING (user waits for answer)
        if os.environ.get('OPENWEATHER_API_KEY'):
            tools.append({
                'function_declarations': [{
                    'name': 'get_weather',
                    'description': 'Получава текущото време за даден град',
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'town': {
                                'type': 'STRING',
                                'description': 'Град. Ако не е посочен — текущия.'
                            }
                        }
                    }
                }]
            })
            log.info('Weather tool enabled')
        else:
            log.info('Weather tool disabled')

        # Home Assistant — NON_BLOCKING + INTERRUPT (only if connected)
        if self._ha_connected:
            devices_str = ', '.join(self._ha_devices[:20]) if self._ha_devices else ''
            tools.append({
                'function_declarations': [{
                    'name': 'ha_control',
                    'description': (
                        'Управлява смарт устройства в Home Assistant. '
                        + (f'Available devices: {devices_str}. ' if devices_str else '')
                        + 'Можеш да използваш имена на английски или български, както са изброени.'
                    ),
                    'parameters': {
                        'type': 'OBJECT',
                        'properties': {
                            'action': {
                                'type': 'STRING',
                                'description': 'on, off, toggle, set_brightness, set_color, set_temperature, status'
                            },
                            'entity_name': {
                                'type': 'STRING',
                                'description': 'Friendly name of the device'
                            },
                            'brightness': {
                                'type': 'NUMBER',
                                'description': 'Brightness 0-100%'
                            },
                            'color': {
                                'type': 'STRING',
                                'description': 'Color name'
                            },
                            'temperature': {
                                'type': 'NUMBER',
                                'description': 'Temperature in Celsius'
                            }
                        },
                        'required': ['action', 'entity_name']
                    },
                    'behavior': 'NON_BLOCKING'
                }]
            })
            log.info('Home Assistant tool enabled')
        else:
            log.info('Home Assistant tool disabled')

        setup = {
            'setup': {
                'model': config.GEMINI_MODEL,
                'generation_config': {
                    'response_modalities': ['AUDIO'],
                },
                'system_instruction': {
                    'parts': [{'text': config.GEMINI_SYSTEM}]
                }
            }
        }

        if tools:
            setup['setup']['tools'] = tools

        return setup

    async def connect(self):
        url = f'{GEMINI_WS}?key={config.GEMINI_API_KEY}'
        self._ws         = await websockets.connect(url)
        self._send_queue = asyncio.Queue()
        self._running    = True

        setup = self._build_setup()
        await self._ws.send(json.dumps(setup))
        await self._ws.recv()   # wait for setupComplete
        log.debug('Gemini Live connected')

        asyncio.create_task(self._send_loop())
        asyncio.create_task(self._recv_loop())

    async def disconnect(self):
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        log.debug('Gemini Live disconnected')

    def send_audio(self, pcm_i16: np.ndarray):
        """Send mic audio — mono int16 @ 16kHz. Thread-safe."""
        if not self._running or self._send_queue is None:
            return
        b64 = base64.b64encode(pcm_i16.tobytes()).decode()
        msg = {
            'realtime_input': {
                'media_chunks': [{
                    'mime_type': 'audio/pcm;rate=16000',
                    'data': b64
                }]
            }
        }
        try:
            self._send_queue.put_nowait(msg)
        except asyncio.QueueFull:
            log.warning('Send queue full — dropping audio')

    def send_tool_responses(self, responses: list):
        """
        Send tool responses back to Gemini.
        """
        function_responses = [
            {
                'id':       r['id'],
                'name':     r['name'],
                'response': {'result': r['result']}
            }
            for r in responses
        ]

        msg = {'tool_response': {'function_responses': function_responses}}

        if self._send_queue:
            try:
                self._send_queue.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning('Send queue full — dropping tool responses')

    async def _send_loop(self):
        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self._send_queue.get(), timeout=1.0
                )
                # Ensure msg is a dict, not a coroutine
                if not isinstance(msg, dict):
                    log.error(f'Send loop: expected dict, got {type(msg)}')
                    continue
                await self._ws.send(json.dumps(msg))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error(f'Send error: {e}')
                break

    async def _recv_loop(self):
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                msg = json.loads(raw)
                self._handle(msg)
        except Exception as e:
            if self._running:
                log.error(f'Recv error: {e}')
        finally:
            # Only signal if still running — use call_soon_threadsafe
            if self._running:
                log.warning('Recv loop ended unexpectedly')
                # Call directly — _on_turn_complete is a regular function
                try:
                    self._on_turn_complete()
                except Exception as e:
                    log.error(f'Turn complete signal error: {e}')

    def _handle(self, msg: dict):
        sc = msg.get('serverContent', {})

        parts = sc.get('modelTurn', {}).get('parts', [])
        for part in parts:
            if 'inlineData' in part:
                mime = part['inlineData'].get('mimeType', '')
                if 'audio' in mime:
                    pcm_24k = base64.b64decode(part['inlineData']['data'])
                    self._on_audio(pcm_24k)
            if 'text' in part:
                log.debug(f'Gemini text: {part["text"]}')
                if self._on_text:
                    self._on_text(part['text'])

        if sc.get('turnComplete'):
            log.debug('Turn complete')
            self._on_turn_complete()

        if sc.get('interrupted'):
            log.debug('Interrupted')
            if self._on_interrupted:
                self._on_interrupted()

        # Parallel tool calls — pass full list
        calls = msg.get('toolCall', {}).get('functionCalls', [])
        if calls:
            log.info(f'Tool calls: {[c.get("name") for c in calls]}')
            if self._on_tool_call:
                self._on_tool_call(calls)