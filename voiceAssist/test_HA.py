import logging
import os
import sys
import re

# Configure logging to display debug info from the client
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from ha_client import HomeAssistantClient
except ImportError:
    print("Error: Could not import HomeAssistantClient. Make sure you are running this script from the voiceAssist directory.")
    sys.exit(1)

def main():
    print("--- Home Assistant Command Test ---")
    
    # Check for Token
    if not os.environ.get("HA_TOKEN"):
        print("WARNING: HA_TOKEN not found in environment variables.")
        token = input("Enter HA_TOKEN manually (or press Enter to skip if set elsewhere): ")
        if token:
            os.environ["HA_TOKEN"] = token
    
    print(f"Using HA_URL: {os.environ.get('HA_URL', 'http://homeassistant.local:8123')}")

    # Initialize Client
    try:
        client = HomeAssistantClient()
    except Exception as e:
        print(f"Initialization failed: {e}")
        return

    # Check for command line arguments
    if len(sys.argv) > 1:
        command = " ".join(sys.argv[1:])
        print(f"Executing command from arguments: '{command}'")
        result = client.send_command(command)
        print(f"Output: {result}")
        return

    # Interactive Loop
    while True:
        print("\n--- New Command ---")
        command = input("Enter Command (e.g., 'turn on kitchen light', 'включи лампата') or 'q' to quit: ").strip()
        if command.lower() == 'q':
            break
        
        # Visual confirmation of language detection (logic matches HomeAssistantClient)
        lang_preview = "bg-BG" if re.search('[а-яА-Я]', command) else "en-US"   
        print(f"Executing '{command}' (Client should detect: {lang_preview})...")
        result = client.send_command(command)
        print(f"Output: {result}")

if __name__ == "__main__":
    main()