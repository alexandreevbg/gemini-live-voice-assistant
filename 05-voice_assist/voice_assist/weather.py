import requests
import os
import logging

log = logging.getLogger(__name__)

def get_weather(town: str, country: str) -> dict:
    """
    Get current weather from OpenWeatherMap.
    Returns dict with temperature, description, humidity, wind.
    """
    api_key = os.environ.get('OPENWEATHER_API_KEY')
    if not api_key:
        log.warning('OPENWEATHER_API_KEY not set')
        return {'error': 'No API key'}

    try:
        url = 'http://api.openweathermap.org/data/2.5/weather'
        params = {
            'q':     f'{town},{country}',
            'appid': api_key,
            'units': 'metric',
            'lang':  'bg'          # Bulgarian descriptions
        }
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()
        data = r.json()

        result = {
            'town':        data['name'],
            'temp':        round(data['main']['temp']),
            'feels_like':  round(data['main']['feels_like']),
            'humidity':    data['main']['humidity'],
            'description': data['weather'][0]['description'],
            'wind_speed':  round(data['wind']['speed']),
        }
        log.info(f'Weather: {result}')
        return result

    except requests.exceptions.RequestException as e:
        log.error(f'Weather request error: {e}')
        return {'error': str(e)}
    except Exception as e:
        log.error(f'Weather error: {e}')
        return {'error': str(e)}

def format_for_gemini(w: dict) -> str:
    """Format weather dict as readable string for Gemini tool response."""
    if 'error' in w:
        return f'Грешка при получаване на времето: {w["error"]}'
    return (
        f'Времето в {w["town"]}: '
        f'{w["temp"]}°C, усеща се като {w["feels_like"]}°C, '
        f'{w["description"]}, '
        f'влажност {w["humidity"]}%, '
        f'вятър {w["wind_speed"]} м/с.'
    )