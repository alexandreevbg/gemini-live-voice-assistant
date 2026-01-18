# Gemini Live
import asyncio
import logging
import time
import threading
from google import genai
from google.genai import types
from .ha_client import HomeAssistantClient

_LOGGER = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self, location, spotify_client=None):
        self.client = genai.Client()
        self.location = location
        self.model = "gemini-2.5-flash-native-audio-preview-12-2025"
        
        # Home Assistant Configuration
        self.ha_client = HomeAssistantClient()
        self.spotify_client = spotify_client

        self.base_config = {
            "response_modalities": ["AUDIO"],
            "system_instruction": "You are a helpful and friendly AI assistant. Your name is Чочко. When telling the time in Bulgarian, always use the format 'HH часа и MM минути' (e.g. '17 часа и 23 минути').",
            "tools": []
        }

        # --- 1. Volume Control Tool (Always Available) ---
        self.base_config["tools"].append({
            "function_declarations": [{
                "name": "adjust_volume",
                "description": "Adjust the volume of the voice assistant. Use this to make it louder, quieter, or set a specific volume level.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "action": {"type": "STRING", "enum": ["increase", "decrease", "set"], "description": "The action to perform: 'increase' (louder), 'decrease' (quieter), or 'set'."},
                        "level": {"type": "INTEGER", "description": "The target volume percentage (0-100). Required only if action is 'set'."}
                    },
                    "required": ["action"]
                }
            }]
        })
        
        # Only add tools if Home Assistant is connected
        if self.ha_client.connected:
            self.base_config["tools"].append({
                "function_declarations": [{
                    "name": "control_smart_device",
                    "description": "Control smart home devices by sending a natural language command.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "command": {"type": "STRING", "description": "The full natural language command to execute (e.g., 'turn on the kitchen light')."}
                        },
                        "required": ["command"]
                    }
                }]
            })
        
        # Add Spotify tool if connected
        if self.spotify_client and self.spotify_client.connected:
            spotify_tool = {
                "function_declarations": [{
                    "name": "play_music",
                    "description": "Play music on Spotify. Can play specific songs, albums, playlists or resume playback.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "query": {"type": "STRING", "description": "The song, album, or artist to play. If empty, resumes playback."}
                        },
                    }
                }, {
                    "name": "next_track",
                    "description": "Skip to the next song on Spotify.",
                    "parameters": {"type": "OBJECT", "properties": {}}
                }, {
                    "name": "previous_track",
                    "description": "Go back to the previous song on Spotify.",
                    "parameters": {"type": "OBJECT", "properties": {}}
                }]
            }
            self.base_config["tools"].append(spotify_tool)
        
        self.audio_queue_in = asyncio.Queue()
        
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="GeminiLoop")
        self.thread.start()
        
        self.session = None
        self.connected = False
        self.last_audio_time = time.time()
        self.audio_callback = None
        self.tool_start_callback = None
        self.tool_end_callback = None
        self.volume_callback = None
        self.receive_task = None

    def set_audio_callback(self, callback):
        """Sets the callback to handle received audio chunks."""
        self.audio_callback = callback

    def set_volume_callback(self, callback):
        """Sets the callback to handle volume adjustments."""
        self.volume_callback = callback

    def set_tool_start_callback(self, callback):
        """Sets the callback to notify when a tool call starts."""
        self.tool_start_callback = callback

    def set_tool_end_callback(self, callback):
        """Sets the callback to notify when a tool call ends."""
        self.tool_end_callback = callback

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect_session(self):
        try:
            _LOGGER.info("Gemini: Using location: %s", self.location)
            
            config = self.base_config.copy()
            config["system_instruction"] += f". You are located in {self.location}."
            
            async with self.client.aio.live.connect(model=self.model, config=config) as session:
                self.session = session
                self.connected = True
                _LOGGER.info("Gemini: Connected")
                
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self._send_loop())
                    self.receive_task = tg.create_task(self._receive_loop())
                
        except Exception as e:
            _LOGGER.error("Gemini Connection Error: %s", e)
            self.connected = False
            self.session = None

    async def _send_loop(self):
        while self.connected:
            try:
                chunk = await self.audio_queue_in.get()
                if chunk is None:
                    break
                await self.session.send_realtime_input(audio={"data": chunk, "mime_type": "audio/pcm"})
            except Exception as e:
                _LOGGER.error("Gemini Send Error: %s", e)
                break

    async def _receive_loop(self):
        while self.connected:
            try:
                async for response in self.session.receive():
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data and isinstance(part.inline_data.data, bytes):
                                self.last_audio_time = time.time()
                                if self.audio_callback:
                                    self.audio_callback(part.inline_data.data)
                    if response.tool_call:
                        await self._handle_tool_call(response.tool_call)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if "1011" in str(e) or "Deadline expired" in str(e):
                    _LOGGER.info("Gemini connection closed (timeout).")
                else:
                    _LOGGER.error("Gemini Receive Error: %s", e)
                self.connected = False
                break

    async def _handle_tool_call(self, tool_call):
        if self.tool_start_callback:
            self.tool_start_callback()
            
        function_responses = []
        for call in tool_call.function_calls:
            if call.name == "control_smart_device":
                try:
                    args = call.args
                    command = args.get("command")
                    
                    # Run blocking HA call in a separate thread
                    result = await asyncio.to_thread(self.ha_client.send_command, command)
                    
                    function_responses.append({
                        "name": call.name,
                        "response": result,
                        "id": call.id
                    })
                except Exception as e:
                    _LOGGER.error("Tool Execution Error: %s", e)
                    function_responses.append({
                        "name": call.name,
                        "response": {"error": str(e)},
                        "id": call.id
                    })
            elif call.name == "adjust_volume":
                try:
                    args = call.args
                    action = args.get("action")
                    level = args.get("level")
                    if self.volume_callback:
                        result = await asyncio.to_thread(self.volume_callback, action, level)
                        function_responses.append({"name": call.name, "response": result, "id": call.id})
                    else:
                        function_responses.append({"name": call.name, "response": {"error": "Volume control unavailable"}, "id": call.id})
                except Exception as e:
                    _LOGGER.error("Volume Tool Error: %s", e)
                    function_responses.append({"name": call.name, "response": {"error": str(e)}, "id": call.id})
            elif call.name == "play_music":
                try:
                    args = call.args
                    query = args.get("query")
                    result = await asyncio.to_thread(self.spotify_client.play_music, query)
                    function_responses.append({
                        "name": call.name,
                        "response": result,
                        "id": call.id
                    })
                except Exception as e:
                    _LOGGER.error("Spotify Tool Error: %s", e)
                    function_responses.append({
                        "name": call.name,
                        "response": {"error": str(e)},
                        "id": call.id
                    })
            elif call.name == "next_track":
                try:
                    result = await asyncio.to_thread(self.spotify_client.next_track)
                    function_responses.append({"name": call.name, "response": result, "id": call.id})
                except Exception as e:
                    _LOGGER.error("Spotify Tool Error: %s", e)
                    function_responses.append({"name": call.name, "response": {"error": str(e)}, "id": call.id})
            elif call.name == "previous_track":
                try:
                    result = await asyncio.to_thread(self.spotify_client.previous_track)
                    function_responses.append({"name": call.name, "response": result, "id": call.id})
                except Exception as e:
                    _LOGGER.error("Spotify Tool Error: %s", e)
                    function_responses.append({"name": call.name, "response": {"error": str(e)}, "id": call.id})
        
        if self.tool_end_callback:
            self.tool_end_callback()
        
        if function_responses:
            tool_response = types.LiveClientToolResponse(function_responses=function_responses)
            await self.session.send(input=tool_response)

    def start_session(self):
        """Starts a new session if not connected."""
        if not self.connected:
            asyncio.run_coroutine_threadsafe(self._connect_session(), self.loop)

    def stop_session(self):
        """Closes the current session."""
        self.connected = False
        if self.receive_task:
            self.loop.call_soon_threadsafe(self.receive_task.cancel)
        # We don't explicitly close self.session here as it's a context manager in _connect_session
        # but setting connected=False breaks the loops. We send None to unblock the queue.
        self.loop.call_soon_threadsafe(self.audio_queue_in.put_nowait, None)

    def feed_audio(self, chunk):
        """Feeds audio from microphone (main.py) to Gemini."""
        if self.connected:
            self.loop.call_soon_threadsafe(self.audio_queue_in.put_nowait, chunk)