# Voice Assistant — Installation & Testing Guide

This guide covers installation of the voice assistant and integrations with Home Assistant and Spotify.

## 1. Install Voice Assistant Package

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

4. Configuration

Move the .env template from the repository to your home directory and populate with your actual credentials.
```bash
mv ~/gemini-live-voice-assistant/03-environment/.env ~
nano .env
```
You should replace at least YOUR_GEMINI_API_KEY and YOUR_OPENWEATHER_API_KEY with real API_KEYs. Other variables are optional. While they are commented, the voice assistant will consider the related integrations as "not available". Once you obtain the Home Assistant and/or Spotify keys, you can uncomment the corresponding variables and populate them with your tokens and keys.

#### To Obtain YOUR_GEMINI_API_KEY
Visit [Google AI Studio](https://aistudio.google.com/), sign in, and click **"Get API key"** to generate your credential.

#### To Obtain YOUR_OPENWEATHER_API_KEY
Sign up at [OpenWeatherMap](https://openweathermap.org/api) and generate a new key under the **"My API keys"** tab in your dashboard.

#### To Obtain YOUR_HOME_ASSISTANT_TOKEN
In your Home Assistant UI, click your **User Profile** (bottom-left icon) → scroll to the bottom → **"Long-Lived Access Tokens"** → **"Create Token"**.

#### To Obtain YOUR_SPOTIFY_CLIENT_ID and YOUR_SPOTIFY_CLIENT_SECRET
Create an application at the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). Ensure you set the **Redirect URI** to `http://127.0.0.1:8888/callback`.


Add those two lines to your `~/.bashrc` file to automatically load your environment variables and activate your Python virtual environment when you start a new shell session.
```bash
echo 'set -a; source ~/.env; set +a' >> ~/.bashrc
echo 'source ~/.venv/bin/activate' >> ~/.bashrc
``` 




 You can also change the `GEMINI_MODEL` to a different model if you prefer.

### 5.1 Edit config.py

```python
WAKEWORD_BACKEND = 'openwakeword'   # or 'microwakeword'
WAKEWORD_MODEL   = '/home/YOUR_USERNAME/voiceAssist/models/your_model.tflite'
WAKEWORD_THRESH  = 0.5

GEMINI_MODEL  = 'models/gemini-2.5-flash-native-audio-latest'
GEMINI_SYSTEM = 'You are a helpful home assistant named Chochko...'

DIALOG_TIMEOUT = 10     # seconds of silence before ending dialog
BUTTON_PIN     = 17     # GPIO pin (ReSpeaker button)
LINE_DAC       = 66     # speaker volume % (adjust for your hardware)

DEBUG = False           # True for full debug logging with timestamps
```

### 5.2 Create .env file

```bash
cat > ~/.env << 'EOF'
GEMINI_API_KEY=your-gemini-api-key
SPOTIFY_CLIENT_ID=your-spotify-client-id
SPOTIFY_CLIENT_SECRET=your-spotify-client-secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
OPENWEATHER_API_KEY=your-openweather-key
HA_TOKEN=your-home-assistant-token
HA_URL=http://homeassistant.local:8123
EOF
chmod 600 ~/.env
```

### 5.3 Load .env in terminal sessions

Add to `~/.bashrc`:
```bash
echo 'set -a; source ~/.env; set +a' >> ~/.bashrc
source ~/.bashrc
```

---

## Phase 6 — Spotify Setup

### 6.1 Install raspotify (Spotify Connect device)

```bash
curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
sudo systemctl disable raspotify   # disable system service
sudo systemctl stop raspotify
sudo systemctl mask raspotify      # prevent accidental start
```

Get Spotify credentials:
```bash
curl -sSL https://xevion.github.io/spotify-quickauth/run.sh | sh
# Creates: ~/.cache/raspotify/credentials.json
```

Create user service:
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

### 6.2 Authorize Spotify Web API

Create Spotify app at https://developer.spotify.com/dashboard
- Set redirect URI: `http://127.0.0.1:8888/callback`
- Copy Client ID and Secret to `~/.env`

Run one-time authorization:
```bash
source ~/.venv/bin/activate
python ~/voiceAssist/spotify_auth.py
# Open URL in browser → authorize → paste redirect URL back
```

---

## Phase 7 — sudo Permissions for WiFi Portal

```bash
echo "YOUR_USERNAME ALL=(ALL) NOPASSWD: /usr/bin/nmcli, /usr/sbin/reboot, /usr/sbin/poweroff" | \
    sudo tee /etc/sudoers.d/chochko-wifi
sudo chmod 440 /etc/sudoers.d/chochko-wifi
sudo visudo -c -f /etc/sudoers.d/chochko-wifi
```

Allow Python to bind port 80:
```bash
sudo setcap 'cap_net_bind_service=+ep' \
    $(readlink -f ~/.venv/bin/python)
```

---

## Phase 8 — Testing Individual Components

Run all tests from `~/voiceAssist/` with venv active.

### 8.1 Test SPI / LEDs

```bash
source ~/.venv/bin/activate
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

### 8.2 Test Microphone

```bash
source ~/.venv/bin/activate
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

### 8.3 Test Playback / Speaker

```bash
source ~/.venv/bin/activate
python3 -c "
import sounddevice as sd, numpy as np

# Play 1 second 440Hz tone
t    = np.linspace(0, 1, 48000, False)
tone = (np.sin(440 * 2 * np.pi * t) * 0.3 * 32767).astype(np.int16)
stereo = np.column_stack([tone, tone])
sd.play(stereo, samplerate=48000, dtype='int16')
sd.wait()
print('Speaker OK')
"
```

### 8.4 Test Button

```bash
source ~/.venv/bin/activate
python3 -c "
from gpiozero import Button
import time
btn = Button(17, pull_up=True)
print('Press button (GPIO17)...')
btn.wait_for_press(timeout=10)
print('Button pressed - GPIO OK')
"
```

### 8.5 Test Wake Word Detection

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
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

### 8.6 Test Gemini Connection

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
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

### 8.7 Test Spotify

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
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

### 8.8 Test Weather

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
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

### 8.9 Test Home Assistant

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
python3 ha_test.py
```

The interactive test script:
1. Lists all loaded entities and aliases
2. Tests entity search by name/alias
3. Shows device status
4. Interactive control prompt

### 8.10 Test Location

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
python3 -c "
import sys
sys.path.insert(0, '.')
import location
loc = location.get_current()
print('Location:', loc)
print('Prompt string:', location.format_for_prompt(loc))
"
```

---

## Phase 9 — Run Voice Assistant From Command Line

### Basic run

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
python main.py
```

### Run with log saved to file

```bash
source ~/.venv/bin/activate
cd ~/voiceAssist
python main.py 2>&1 | tee ~/voiceAssist/session.log
```

### Run with debug logging

In `config.py` set `DEBUG = True`, then:
```bash
python main.py 2>&1 | tee ~/voiceAssist/debug.log
```

### Check for false wake word detections

```bash
grep "score" ~/voiceAssist/session.log
grep "Wake word" ~/voiceAssist/session.log
```

---

## Phase 10 — Systemd Autostart Services

### Create voice assistant service

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

### Enable linger (start services at boot without login)

```bash
sudo loginctl enable-linger YOUR_USERNAME
loginctl show-user YOUR_USERNAME | grep Linger
# Expected: Linger=yes
```

### Start and verify all services

```bash
systemctl --user start voiceassist
sleep 12

systemctl --user status \
    pipewire wireplumber pipewire-pulse \
    raspotify voiceassist \
    | grep -E "Active|Main PID"
```

All 5 should show `active (running)`.

### View logs

```bash
# Follow live logs
journalctl --user -u voiceassist -f

# Last 50 lines
journalctl --user -u voiceassist -n 50

# Filter for errors only
journalctl --user -u voiceassist -n 100 | grep -E "ERROR|WARNING"
```

---

## Quick Verification Checklist

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

---

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