# Voice Assistant — Installation & Testing Guide

This guide covers installation of the voice assistant and integrations with Home Assistant and Spotify.

## 1. Set API keys for integrations
Move the .env template from the repository to your home directory and open it to populate with your actual credentials.
```bash
cp ~/gemini-live-voice-assistant/03-environment/.env ~
chmod 600 ~/.env
nano .env
```
You should obtain at least a GEMINI API key and OPENWEATHER API key. Other integrations are optional.

### To Obtain YOUR_GEMINI_API_KEY
Visit [Google AI Studio](https://aistudio.google.com/), sign in, and click **"Get API key"** to generate your credential. Copy the key and paste it into the placeholder in the .env file.

### To Obtain YOUR_OPENWEATHER_API_KEY
Sign up at [OpenWeatherMap](https://openweathermap.org/api), select the tab **API Keys** and generate a new key by the button "Generate". Copy the key and paste it into the .env file.

### To Obtain YOUR_HOME_ASSISTANT_TOKEN
In your Home Assistant UI, click your **User Profile** (bottom-left icon) → scroll to the bottom → **"Long-Lived Access Tokens"** → **"Create Token"**. Copy the token and paste it into the .env file.

### To Obtain YOUR_SPOTIFY_CLIENT_ID and YOUR_SPOTIFY_CLIENT_SECRET
Login or Signin to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) → Home → Dashboard → Create App. Ensure you set the **Redirect URI** to `http://127.0.0.1:8888/callback. After app is created, copy the Client ID and Client Secret and paste them into the .env file.

You should replace at least YOUR_GEMINI_API_KEY and YOUR_OPENWEATHER_API_KEY with real API_KEYs. Other variables are optional. While they are commented, the voice assistant will consider the related integrations as "not available". Once you obtain the Home Assistant and/or Spotify keys, you can uncomment the corresponding variables and populate them with your tokens and keys.

Add those two lines to your `~/.bashrc` file to automatically load your environment variables and activate your Python virtual environment when you start a new shell session.
```bash
echo 'set -a; source ~/.env; set +a' >> ~/.bashrc
echo 'source ~/.venv/bin/activate' >> ~/.bashrc
``` 

## 2. Install Voice Assistant Package

1. Install System Dependencies
```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev alsa-utils
```

2. Install Python Packages
```bash
pip install sounddevice websockets requests spotipy
```

3. Move Source Files
```bash
mv ~/gemini-live-voice-assistant/05-voice_assist/voice_assist ~/voice_assist
```

## 4. Setup Spotify Connect device (optional)
1. Stop the raspotify system service
```bash
sudo systemctl disable raspotify
sudo systemctl stop raspotify
sudo systemctl mask raspotify
```

2. Get Spotify credentials
```bash
curl -sSL https://xevion.github.io/spotify-quickauth/run.sh | sh
# Creates: ~/.cache/raspotify/credentials.json
```

3. Setup and re-run user service
```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/raspotify.service << 'EOF'
[Unit]
Description=Raspotify (Spotify Connect)
After=pipewire.service wireplumber.service pipewire-pulse.service
Wants=pipewire.service pipewire-pulse.service

[Service]
ExecStartPre=/bin/sleep 5
ExecStart=/usr/bin/librespot \
    --name "Chochko" \
    --bitrate 320 \
    --format S32 \
    --backend pulseaudio \
    --device default \
    --device-type speaker \
    --initial-volume 100 \
    --cache "/home/YOUR_USERNAME/.cache/raspotify"
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable raspotify
systemctl --user start raspotify
sleep 8
systemctl --user status raspotify | grep Active
```

4. Authorize Spotify Web API
Create Spotify app at https://developer.spotify.com/dashboard
- Set redirect URI: `http://127.0.0.1:8888/callback`
- Copy Client ID and Secret to `~/.env` if not yet

Run one-time authorization:
```bash
source ~/.venv/bin/activate
python ~/voiceAssist/spotify_auth.py
# Open URL in browser → authorize → paste redirect URL back
```

5. Allow Python to bind port 80:
```bash
sudo setcap 'cap_net_bind_service=+ep' $(readlink -f ~/.venv/bin/python)
```

## 5. Test Individual Components
Run all tests from with .venv active.
```bash
cd ~/voice_assist
```

1. Test SPI / LEDs
```bash
python3 -c "
import spidev, time
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000
def write(r, g, b):
    buf = [0]*4
    for _ in range(3):
        buf += [0xFF, b, g, r]
    buf += [0xFF]*4
    spi.xfer2(buf)
write(0, 0, 80);  time.sleep(1)   # blue
write(80, 0, 80); time.sleep(1)   # magenta
write(80, 0, 0);  time.sleep(1)   # red
write(0, 0, 0)                    # off
spi.close()
print('LEDs OK')
"
```

2. Test Microphone
```bash
python3 -c "
import sounddevice as sd, numpy as np
print('Devices:')
print(sd.query_devices())
print()

chunks = []
def cb(indata, frames, t, status):
    chunks.append(indata.copy())
    if len(chunks) == 1:
        print(f'dtype={indata.dtype} shape={indata.shape}')

with sd.InputStream(samplerate=48000, channels=2, dtype='int32',
                    blocksize=3840, callback=cb):
    sd.sleep(2000)
print(f'Received {len(chunks)} chunks - Mic OK')
"
```

3. Test Playback / Speaker
```bash
python3 -c "
import sounddevice as sd, numpy as np
t    = np.linspace(0, 1, 48000, False)
tone = (np.sin(440 * 2 * np.pi * t) * 0.3 * 32767).astype(np.int16)
stereo = np.column_stack([tone, tone])
sd.play(stereo, samplerate=48000)
sd.wait()
print('Speaker OK')
"
```

4. Test Button
```bash
python3 -c "
from gpiozero import Button
import time
btn = Button(17, pull_up=True)
print('Press button (GPIO17)...')
btn.wait_for_press(timeout=10)
print('Button pressed - GPIO OK')
"
```

5. Test Wake Word Detection

```bash
python3 -c "
import sys, time, numpy as np
from capture import MicCapture
from wakeword import create_detector
import config

detector = create_detector(
    config.WAKEWORD_BACKEND,
    config.WAKEWORD_MODEL,
    config.WAKEWORD_THRESH
)

detected = [False]

def on_detect():
    print('WAKE WORD DETECTED!')
    detected[0] = True

import asyncio
loop = asyncio.new_event_loop()
detector.set_loop(loop)
detector.set_on_detect(on_detect)

mic = MicCapture()
mic.add_consumer(detector.process)
mic.start()

print(f'Listening for wake word ({config.WAKEWORD_BACKEND})...')
print('Say your wake word now (10 seconds)')

start = time.time()
while not detected[0] and time.time() - start < 10:
    time.sleep(0.1)

mic.stop()
if not detected[0]:
    print('Wake word not detected in 10s')
"
```

6. Test Gemini Connection
```bash
python3 -c "
import asyncio, os, sys
sys.path.insert(0, '.')
import config

async def test():
    import websockets, json
    url = (
        'wss://generativelanguage.googleapis.com/ws/'
        'google.ai.generativelanguage.v1beta.'
        f'GenerativeService.BidiGenerateContent?key={config.GEMINI_API_KEY}'
    )
    try:
        ws = await asyncio.wait_for(websockets.connect(url), timeout=10)
        setup = json.dumps({
            'setup': {
                'model': config.GEMINI_MODEL,
                'generation_config': {'response_modalities': ['AUDIO']}
            }
        })
        await ws.send(setup)
        msg = json.loads(await ws.recv())
        print('Gemini response:', list(msg.keys()))
        await ws.close()
        print('Gemini Live connection OK')
    except Exception as e:
        print(f'Gemini connection FAILED: {e}')

asyncio.run(test())
"
```

7. Test Spotify
```bash
python3 -c "
import sys, os, time
sys.path.insert(0, '.')
from spotify import SpotifyController
import logging
logging.basicConfig(level=logging.INFO)

sp = SpotifyController()
ok = sp.connect()
print('Connected:', ok)
if ok:
    devices = sp._sp.devices()
    print('Devices:')
    for d in devices['devices']:
        print(f'  {d[\"name\"]} active={d[\"is_active\"]}')
    current = sp.get_current()
    print('Now playing:', current)
    print()
    print('Testing volume...')
    sp.set_volume(50)
    time.sleep(1)
    sp.set_volume(100)
    print('Spotify OK')
"
```

8. Test Weather
```bash
python3 -c "
import sys
sys.path.insert(0, '.')
import weather, location

loc = location.get_current()
print('Location:', loc)
w = weather.get_weather(loc['town'], loc['country'])
print('Weather:', w)
print('Formatted:', weather.format_for_gemini(w))
"
```

9. Test Home Assistant
```bash
python3 ha_test.py
```

The interactive test script:
1. Lists all loaded entities and aliases
2. Tests entity search by name/alias
3. Shows device status
4. Interactive control prompt

10. Test Location
```bash
python3 -c "
import sys
sys.path.insert(0, '.')
import location
loc = location.get_current()
print('Location:', loc)
print('Prompt string:', location.format_for_prompt(loc))
"
```

## 6. Run Voice Assistant From Command Line
```bash
python main.py
```

Run with log saved to file
```bash
python main.py 2>&1 | tee ~/voiceAssist/session.log
```

Run with debug logging
In `config.py` set `DEBUG = True`, then:
```bash
python main.py 2>&1 | tee ~/voiceAssist/debug.log
```

Check for false wake word detections
```bash
grep "score" ~/voiceAssist/session.log
grep "Wake word" ~/voiceAssist/session.log
```

## 7. Systemd Autostart Services
1. Create voice assistant service
```bash
cat > ~/.config/systemd/user/voiceassist.service << 'EOF'
[Unit]
Description=Chochko Voice Assistant
After=pipewire.service wireplumber.service pipewire-pulse.service raspotify.service
Wants=pipewire.service pipewire-pulse.service raspotify.service

[Service]
WorkingDirectory=/home/YOUR_USERNAME/voiceAssist
EnvironmentFile=/home/YOUR_USERNAME/.env
ExecStartPre=/bin/sleep 10
ExecStart=/home/YOUR_USERNAME/.venv/bin/python main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal+console
StandardError=journal+console
SyslogIdentifier=voiceassist

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable voiceassist
```

2. Enable linger (start services at boot without login)
```bash
sudo loginctl enable-linger YOUR_USERNAME
loginctl show-user YOUR_USERNAME | grep Linger
# Expected: Linger=yes
```

3. Start and verify all services
```bash
systemctl --user start voiceassist
sleep 12

systemctl --user status \
    pipewire wireplumber pipewire-pulse \
    raspotify voiceassist \
    | grep -E "Active|Main PID"
```

All 5 should show `active (running)`.

4. View logs

```bash
# Follow live logs
journalctl --user -u voiceassist -f

# Last 50 lines
journalctl --user -u voiceassist -n 50

# Filter for errors only
journalctl --user -u voiceassist -n 100 | grep -E "ERROR|WARNING"
```

5. Quick Verification Checklist
```
Hardware:
[ ] SPI enabled (ls /dev/spidev*)
[ ] LEDs blink blue on test
[ ] Mic records audio (non-zero samples)
[ ] Speaker plays tone
[ ] Button detected on GPIO17

Software:
[ ] Wake word detected within 10s
[ ] Gemini WebSocket connects
[ ] Spotify device visible
[ ] Weather returns data
[ ] Home Assistant loads entities

Services (after reboot):
[ ] pipewire active
[ ] wireplumber active
[ ] pipewire-pulse active
[ ] raspotify active
[ ] voiceassist active
```

## Common Issues

### SPI permission denied
```bash
# Verify SPI enabled
ls /dev/spidev*
# If missing: sudo raspi-config nonint do_spi 0 && sudo reboot
```

### No audio devices found
```bash
systemctl --user status pipewire
systemctl --user restart pipewire wireplumber
```

### Spotify token expired
```bash
rm -f ~/.spotify_cache
python ~/voiceAssist/spotify_auth.py
```

### Home Assistant not connecting
```bash
# Test connectivity
curl -H "Authorization: Bearer $HA_TOKEN" \
     http://homeassistant.local:8123/api/ | python3 -m json.tool
```

### Wake word not detecting
```bash
# Check audio levels
alsamixer -c 0
# Adjust PGA level (target: speech clearly audible)
```

### Environment variables not loaded in service
```bash
# Verify .env has no 'export' prefix
grep "^export" ~/.env   # should return nothing
# Fix if needed:
sed -i 's/^export //' ~/.env
```