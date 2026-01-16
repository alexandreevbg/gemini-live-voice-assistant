# config_manager.py

import json
import logging
from pathlib import Path
from typing import Any, Dict

_LOGGER = logging.getLogger(__name__)
_CONFIG_DIR = Path(__file__).parent
CONFIG_FILE_PATH = _CONFIG_DIR / "config.json"
DEFAULT_VOICE_NAME = "Ollie"
DEFAULT_SPEAKER_VOLUME = 75

class ConfigManager:
    """Handles loading and saving of a JSON configuration file."""

    def __init__(self, config_path: Path = CONFIG_FILE_PATH):
        self._config_path = config_path
        self._config: Dict[str, Any] = {}

    def load(self):
        """Loads the configuration from the file, or creates a default one."""
        try:
            if self._config_path.exists():
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                
                config_updated = False
                if "voice_name" not in self._config:
                    self._config["voice_name"] = DEFAULT_VOICE_NAME
                    config_updated = True
                if "speaker_volume" not in self._config:
                    self._config["speaker_volume"] = DEFAULT_SPEAKER_VOLUME
                    config_updated = True

                if config_updated:
                    self.save()
            else:
                self._create_default_config()
                self.save()
        except (json.JSONDecodeError, IOError) as e:
            _LOGGER.error(f"Error loading or creating config, creating default: {e}")
            self._create_default_config()
            self.save()

    def _create_default_config(self):
        """Sets the internal config dictionary to default values."""
        self._config = {
            "voice_name": DEFAULT_VOICE_NAME,
            "speaker_volume": DEFAULT_SPEAKER_VOLUME
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a value from the configuration."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Sets a value in the configuration."""
        self._config[key] = value

    def save(self):
        """Saves the current configuration to the file."""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            _LOGGER.debug(f"Configuration saved to {self._config_path}")
        except IOError as e:
            _LOGGER.error(f"Failed to save configuration file: {e}")

# Create a single, shared instance to be used across the application
config_manager = ConfigManager()