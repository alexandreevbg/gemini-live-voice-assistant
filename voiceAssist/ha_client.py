import logging
import json
import urllib.request
import os
import re

_LOGGER = logging.getLogger(__name__)

class HomeAssistantClient:
    def __init__(self, url=None, token=None):
        self.url = url or os.getenv("HA_URL", "http://homeassistant.local:8123")
        self.token = token or os.getenv("HA_TOKEN", "YOUR_LONG_LIVED_ACCESS_TOKEN")
        self.connected = False
        
        if self.url and "YOUR_" not in self.token:
            self.connected = True
        else:
            _LOGGER.warning("Home Assistant URL or Token not configured. Integration disabled.")

    def send_command(self, command):
        """Sends a natural language command to Home Assistant's conversation agent."""
        _LOGGER.info("HA CALL: send_command(command='%s')", command)
        
        endpoint = f"{self.url}/api/conversation/process"
        # Detect language: if Cyrillic characters are present, use Bulgarian, else English
        language = "bg" if re.search('[а-яА-Я]', command) else "en"
        payload = {"text": command, "language": language}
        
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    resp_data = json.loads(response.read().decode())
                    _LOGGER.debug("Full HA Response: %s", json.dumps(resp_data, ensure_ascii=False))

                    # The response is typically wrapped in a "response" object in newer HA versions
                    response_obj = resp_data.get("response", resp_data)

                    # Extract the speech response from Home Assistant
                    speech = response_obj.get("speech", {}).get("plain", {}).get("speech")
                    
                    if not speech:
                        response_type = response_obj.get("response_type")
                        if response_type == "error":
                            code = response_obj.get("data", {}).get("code", "unknown")
                            speech = f"Home Assistant Error: {code}"
                        else:
                            # Check if there are specific failures in the data
                            data_content = response_obj.get("data", {})
                            failed = data_content.get("failed", [])
                            if failed:
                                names = [item.get("name", "unknown device") for item in failed]
                                speech = f"Could not control: {', '.join(names)}"
                            else:
                                speech = "Command processed."

                    _LOGGER.info("Home Assistant response: %s", speech)
                    return {"result": speech}
                else:
                    return {"error": f"HTTP {response.status}"}
        except Exception as e:
            _LOGGER.error("Home Assistant API Error: %s", e)
            return {"error": str(e)}