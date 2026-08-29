import json
import logging
import os
import requests

log = logging.getLogger(__name__)

LOCATION_FILE = os.path.join(os.path.dirname(__file__), 'location.json')

def _load_file() -> dict:
    try:
        with open(LOCATION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'current': {}, 'addresses': {}}
    except Exception as e:
        log.warning(f'Load location failed: {e}')
        return {'current': {}, 'addresses': {}}

def _save_file(data: dict):
    try:
        with open(LOCATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f'Save location failed: {e}')

def get_ip_location() -> dict:
    """Get country and town from public IP using ipinfo.io."""
    try:
        r = requests.get('https://ipinfo.io/json', timeout=5)
        data = r.json()
        return {
            'country': data.get('country', ''),
            'town':    data.get('city', ''),
        }
    except Exception as e:
        log.warning(f'IP location failed: {e}')
        return {'country': '', 'town': ''}

def _make_key(country: str, town: str) -> str:
    return f'{country}|{town}'

def save_address(address: str, country: str, town: str):
    """Save address for specific country+town combination."""
    data = _load_file()
    key  = _make_key(country, town)
    data['addresses'][key] = address
    _save_file(data)
    log.info(f'Address saved: {key} → {address}')

def get_current() -> dict:
    """
    Get current location with address if previously saved for this town.
    Updates current location in file.
    """
    ip_loc  = get_ip_location()
    country = ip_loc.get('country', '')
    town    = ip_loc.get('town', '')
    key     = _make_key(country, town)

    data = _load_file()

    # Update current location
    data['current'] = {'country': country, 'town': town}
    _save_file(data)

    # Look up saved address for this town
    address = data['addresses'].get(key)

    result = {
        'country': country,
        'town':    town,
        'address': address
    }

    if address:
        log.debug(f'Location: {town}, {country} — address: {address}')
    else:
        log.debug(f'Location: {town}, {country} — no saved address')

    return result

def format_for_prompt(loc: dict) -> str:
    """Format location for Gemini system prompt."""
    parts = []
    if loc.get('town'):
        parts.append(loc['town'])
    if loc.get('country'):
        parts.append(loc['country'])
    if loc.get('address'):
        parts.append(loc['address'])
    if parts:
        return 'Местоположение: ' + ', '.join(parts) + '.'
    return ''