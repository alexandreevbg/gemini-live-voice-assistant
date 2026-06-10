import json
import os
import asyncio
import logging
import requests
import websockets

log = logging.getLogger(__name__)

HA_URL_DEFAULT = 'http://homeassistant.local:8123'

class SmartHome:
    def __init__(self):
        self.connected = False
        self._token    = None
        self._url      = None
        self._headers  = None
        self._entities = {}

    def connect(self) -> bool:
        token = os.environ.get('HA_TOKEN')
        if not token:
            log.info('HA_TOKEN not set — Home Assistant disabled')
            return False

        self._url     = os.environ.get('HA_URL', HA_URL_DEFAULT)
        self._token   = token
        self._headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json'
        }

        try:
            r = requests.get(
                f'{self._url}/api/',
                headers=self._headers,
                timeout=5
            )
            if r.status_code == 200:
                self.connected = True
                log.info(f'Home Assistant connected: {self._url}')
                self._load_entities()
                return True
            else:
                log.warning(f'HA returned {r.status_code} — disabled')
                return False
        except Exception as e:
            log.warning(f'Home Assistant not reachable: {e} — disabled')
            return False

    def _load_entities(self):
        """Load entities via REST + aliases via WebSocket."""
        try:
            self._entities = {}

            # Load friendly names from REST API
            r = requests.get(
                f'{self._url}/api/states',
                headers=self._headers, timeout=10
            )
            entity_ids = []
            for entity in r.json():
                entity_id = entity['entity_id']
                if not entity_id.startswith((
                    'light.', 'switch.', 'cover.',
                    'climate.', 'fan.', 'media_player.'
                )):
                    continue
                friendly = entity.get('attributes', {}).get(
                    'friendly_name', ''
                ).lower()
                if friendly:
                    self._entities[friendly] = entity_id
                entity_ids.append(entity_id)

            # Load aliases in a separate thread with its own event loop
            import threading
            aliases  = {}
            error    = []

            def run_ws():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self._load_aliases_ws(entity_ids)
                    )
                    aliases.update(result)
                except Exception as e:
                    error.append(e)
                finally:
                    loop.close()

            t = threading.Thread(target=run_ws)
            t.start()
            t.join(timeout=30)  # max 30s for all entities

            if error:
                log.warning(f'HA aliases error: {error[0]}')

            for alias, entity_id in aliases.items():
                self._entities[alias.lower()] = entity_id

            log.info(f'HA: loaded {len(self._entities)} entities/aliases '
                     f'({len(aliases)} aliases)')

        except Exception as e:
            log.error(f'HA load entities error: {e}')

    async def _load_aliases_ws(self, entity_ids: list) -> dict:
        """Load aliases for each entity via WebSocket get command."""
        aliases  = {}
        ws_url   = self._url.replace('http', 'ws') + '/api/websocket'
        try:
            async with websockets.connect(ws_url, open_timeout=5) as ws:
                # Auth
                await ws.recv()
                await ws.send(json.dumps({
                    'type': 'auth',
                    'access_token': self._token
                }))
                msg = json.loads(await ws.recv())
                if msg.get('type') != 'auth_ok':
                    log.warning('HA WebSocket auth failed')
                    return {}

                # Fetch each entity individually
                for i, entity_id in enumerate(entity_ids, start=1):
                    await ws.send(json.dumps({
                        'id': i,
                        'type': 'config/entity_registry/get',
                        'entity_id': entity_id
                    }))
                    msg = json.loads(await ws.recv())
                    if msg.get('success'):
                        result = msg.get('result', {})
                        for alias in result.get('aliases', []):
                            if alias:  # skip None values
                                aliases[alias] = entity_id
                                log.debug(f'HA alias: {alias!r} → {entity_id}')

        except Exception as e:
            log.warning(f'HA WebSocket aliases error: {e}')

        return aliases

    def _find_entity(self, name: str) -> str | None:
        """Find entity_id by friendly name — exact then partial match."""
        name_lower = name.lower().strip()

        # Exact match
        if name_lower in self._entities:
            return self._entities[name_lower]

        # Partial match
        for friendly, entity_id in self._entities.items():
            if name_lower in friendly or friendly in name_lower:
                log.info(f'HA partial match: "{name_lower}" → {friendly}')
                return entity_id

        log.warning(f'HA entity not found: {name}')
        return None

    def _call_service(self, domain: str, service: str,
                      entity_id: str, extra: dict = None) -> bool:
        data = {'entity_id': entity_id}
        if extra:
            data.update(extra)
        try:
            r = requests.post(
                f'{self._url}/api/services/{domain}/{service}',
                headers=self._headers,
                json=data,
                timeout=5
            )
            ok = r.status_code in (200, 201)
            if ok:
                log.info(f'HA: {domain}.{service} → {entity_id}')
            else:
                log.warning(f'HA: {domain}.{service} failed: {r.status_code}')
            return ok
        except Exception as e:
            log.error(f'HA service call error: {e}')
            return False

    def get_state(self, entity_id: str) -> dict | None:
        try:
            r = requests.get(
                f'{self._url}/api/states/{entity_id}',
                headers=self._headers,
                timeout=5
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            log.error(f'HA get state error: {e}')
        return None

    def control(self, action: str, entity_name: str,
                brightness: int = None, color: str = None,
                temperature: float = None) -> str:
        if not self.connected:
            return 'Home Assistant не е свързан.'

        entity_id = self._find_entity(entity_name)
        if not entity_id:
            self._load_entities()
            entity_id = self._find_entity(entity_name)
            if not entity_id:
                return f'Устройството "{entity_name}" не е намерено.'

        domain = entity_id.split('.')[0]

        if action == 'on':
            ok = self._call_service(domain, 'turn_on', entity_id)
            return f'{entity_name} е включено.' if ok else 'Грешка.'

        elif action == 'off':
            ok = self._call_service(domain, 'turn_off', entity_id)
            return f'{entity_name} е изключено.' if ok else 'Грешка.'

        elif action == 'toggle':
            ok = self._call_service(domain, 'toggle', entity_id)
            return f'{entity_name} е превключено.' if ok else 'Грешка.'

        elif action == 'set_brightness' and brightness is not None:
            pct = max(0, min(100, brightness))
            val = int(pct * 255 / 100)
            ok  = self._call_service(
                'light', 'turn_on', entity_id,
                {'brightness': val}
            )
            return f'Яркостта на {entity_name} е {pct}%.' if ok else 'Грешка.'

        elif action == 'set_color' and color:
            color_map = {
                'red':    [255, 0, 0],     'червено':   [255, 0, 0],
                'green':  [0, 255, 0],     'зелено':    [0, 255, 0],
                'blue':   [0, 0, 255],     'синьо':     [0, 0, 255],
                'white':  [255, 255, 255], 'бяло':      [255, 255, 255],
                'yellow': [255, 255, 0],   'жълто':     [255, 255, 0],
                'orange': [255, 165, 0],   'оранжево':  [255, 165, 0],
                'purple': [128, 0, 128],   'лилаво':    [128, 0, 128],
                'pink':   [255, 105, 180], 'розово':    [255, 105, 180],
                'warm':   [255, 200, 100], 'топло':     [255, 200, 100],
                'cool':   [200, 220, 255], 'студено':   [200, 220, 255],
            }
            rgb = color_map.get(color.lower())
            if not rgb:
                return f'Непознат цвят: {color}'
            ok = self._call_service(
                'light', 'turn_on', entity_id,
                {'rgb_color': rgb}
            )
            return f'{entity_name} е {color}.' if ok else 'Грешка.'

        elif action == 'set_temperature' and temperature is not None:
            ok = self._call_service(
                'climate', 'set_temperature', entity_id,
                {'temperature': temperature}
            )
            return f'Температурата е {temperature}°.' if ok else 'Грешка.'

        elif action == 'status':
            state = self.get_state(entity_id)
            if state:
                s     = state.get('state', 'unknown')
                attrs = state.get('attributes', {})
                result = f'{entity_name}: {s}'
                if 'brightness' in attrs and attrs['brightness']:
                    pct = round(attrs['brightness'] / 255 * 100)
                    result += f', яркост {pct}%'
                if 'temperature' in attrs:
                    result += f', {attrs["temperature"]}°'
                if 'current_temperature' in attrs:
                    result += f', текуща {attrs["current_temperature"]}°'
                return result
            return f'Не мога да получа статуса на {entity_name}.'

        return f'Непозната команда: {action}'

    def list_devices(self, domain: str = None) -> list:
        if domain:
            return sorted([
                name for name, eid in self._entities.items()
                if eid.startswith(domain + '.')
            ])
        return sorted(self._entities.keys())