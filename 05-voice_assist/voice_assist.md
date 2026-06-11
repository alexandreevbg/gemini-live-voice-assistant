# Voice Assistant: Installation & Testing Guide

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

3. Move Source Files to Home Directory
```bash
mv ~/gemini-live-voice-assistant/05-voice_assist/voice_assist ~/voice_assist
```

## 3. Setup Spotify Connect device (optional)

Playing music needs two things, and both require **Spotify Premium** (Connect / librespot does not work on free accounts):

- **A playback device** named `Chochko` on your network — provided by librespot / raspotify.
- **Web API authorization** so the assistant can see that device and control it (play / pause / volume / transfer).

If you already installed raspotify and can control it from the Spotify phone app, the device half is essentially working. The steps below move it into your user's PipeWire session (so audio routes to the ReSpeaker) and then authorize the Web API.

### 3.1 Run raspotify in your user session
The packaged service runs as its own system user and can't reach your PipeWire audio session — when it tries to open ALSA directly it crash-loops with `snd_pcm_open ... Host is down (112)`. So disable and **mask** it (masking matters; it auto-restarts otherwise), then run the same `librespot` binary as a **user** service that shares your PipeWire session.
```bash
sudo systemctl disable --now raspotify
sudo systemctl mask raspotify
systemctl is-active raspotify        # expect: inactive
```

Confirm the librespot binary path (installed by the raspotify package — masking the service does not remove the binary):
```bash
which librespot                      # expect /usr/bin/librespot
```

Create the user service, replacing `YOUR_USERNAME` with your login (e.g. `chochko`). If `which librespot` returned a different path, fix the `ExecStart` line to match:
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
systemctl --user enable --now raspotify
sleep 8
systemctl --user status raspotify | grep Active
```

Then **log the device in once**: open Spotify on your phone, tap the devices icon, select **Chochko**, and play something. librespot authenticates over zeroconf (the same way your phone already discovers it) and caches the session in `--cache`, so it reconnects automatically on every boot afterwards.

> No credential script is needed. An earlier version of this guide piped a remote `…/run.sh | sh` to pre-seed `credentials.json`. That is both unnecessary (zeroconf + `--cache` already persists the login) and risky — it runs unreviewed remote code as your user. Skip it.

### 3.2 Authorize the Web API (one-time)
Do this **after** 3.1 is running — the verification at the end lists Spotify devices, which only shows **Chochko** if the user service is up.

The app and credentials are already set up in Section 1 (redirect URI `http://127.0.0.1:8888/callback`, Client ID / Secret in `~/.env`). Mint the token cache that the assistant reads:
```bash
cd ~/voice_assist
python spotify_auth.py
```
1. Open the printed URL in a browser on your **phone or laptop** (the Pi has no browser).
2. Log in and approve. The browser then tries to load `http://127.0.0.1:8888/callback?code=…` and **fails to load — that is expected** (nothing listens on the Pi; only the `?code=…` in the address bar matters).
3. Copy the **entire** address-bar URL and paste it back at the prompt.

`spotify_auth.py` exchanges the code, writes `~/.spotify_cache`, then verifies that your account shows `premium` and that **Chochko** appears in your device list. After this the assistant uses the cached token automatically and refreshes it as needed.

> The account you authorize here must be the **same Premium account** raspotify is logged into — Connect only lists devices on your own account. Run this as the **same user** that runs the assistant, so the cache lands in the right home directory.

## 4. Test Individual Components
These checks verify each piece of hardware and each integration in isolation, so that if something fails later you already know which part is healthy. Run them on the Pi (most need the real hardware), one at a time, with the `.venv` active. Each test prints an `... OK` line on success — if you see a Python traceback or a `FAILED` message instead, fix that component before moving on.
```bash
cd ~/voice_assist
source .venv/bin/activate
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
> **Watch the 3 LEDs.** They should light **blue → magenta → red** (1 second each), then switch **off**, and print `LEDs OK`. If the colours look wrong (e.g. red/blue swapped) the byte order is off; if nothing lights, check the HAT seating and that SPI is enabled.

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
> Prints the device list, then captures audio for ~2 seconds. You should see a non-zero chunk count and `Mic OK`. Confirm the ReSpeaker 2-Mic array appears in the device list; if `Received 0 chunks` or it errors, the mic isn't being picked up — recheck the PipeWire/ALSA setup and the HAT.

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
> **Listen.** You should hear a clear 1-second 440 Hz tone (musical note A) from the speaker, then `Speaker OK`. No sound usually means the wrong output device or a muted/low volume — check the speaker connection and the PipeWire default sink.

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
> When you see `Press button (GPIO17)...`, **physically press the button** on the HAT within 10 seconds. Success prints `Button pressed - GPIO OK`. If it exits after 10 s with no message, the press wasn't registered — check the wiring/pin (GPIO17).

5. Test Wake Word Detection
To test wake word detection, run the following script:
```bash
python3 -c "
import logging, time
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
from capture import MicCapture
from wakeword import create_detector
import config

det = create_detector(config.WAKEWORD_BACKEND, config.WAKEWORD_MODEL, config.WAKEWORD_THRESH)
mic = MicCapture(); mic.add_consumer(det.process); mic.start()

print('Say the wake word (10s)...')
start = time.time()
while time.time() - start < 10:
    time.sleep(0.05)
    if det._detected:              # set synchronously inside process()
        print('>>> WAKE WORD DETECTED <<<')
        break
mic.stop()
print('Detected' if det._detected else 'Not detected')
"
```
> After `Say your wake word now`, **speak your wake word** clearly within 10 seconds. Success prints `WAKE WORD DETECTED!`. If it reports `Wake word not detected in 10s`, try speaking louder/closer, or lower `WAKEWORD_THRESH` in `config.py` (a lower threshold is more sensitive but risks false triggers).

> You can also test microWakeWord detection. For this in config.py find and change:
```text
 USE_MICROWAKEWORD = True  
```
Then run the same test script.

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
> Needs working internet and a valid `GEMINI_API_KEY` in your environment. Success prints the response keys and `Gemini Live connection OK`. A `Gemini connection FAILED:` message points at the cause — usually a bad/missing API key, no internet, or a wrong `GEMINI_MODEL` name in `config.py`.

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
    sp.set_volume(75)
    time.sleep(1)
    sp.set_volume(100)
    print('Spotify OK')
"
```
> Requires Sections 3.1 and 3.2 done (raspotify running and the Web API authorized). It lists your Spotify devices — **Chochko** should be among them — shows what's playing, and steps the volume 50 → 100 (if something is playing you'll hear it change). Success prints `Spotify OK`. `Connected: False` means the token cache is missing or the account isn't Premium — rerun `spotify_auth.py`.

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
> Resolves your location, then fetches the current weather for it. You should see a plausible town/country and a weather summary — no traceback. If the location looks wrong, check the Location test (#10); if the weather call fails, verify internet and any weather API settings.

9. Test Home Assistant
```bash
python test_ha.py
```

The interactive test script:
1. Lists all loaded entities and aliases
2. Tests entity search by name/alias
3. Shows device status
4. Interactive control prompt

> This one is **interactive** — it waits for your input. Confirm your Home Assistant entities and aliases appear in the list, then use the control prompt to toggle a device (e.g. a light) and check it actually responds. An empty entity list or connection error means the HA URL/token in your config is wrong or HA is unreachable. Press `Ctrl+C` to exit when done.

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
> Prints your detected location and the formatted string the assistant feeds to the model. Check the town/country are correct — this drives both the weather lookup (#8) and any location-aware answers. If it's wrong or empty, verify internet access and the location source (e.g. IP-based geolocation can be off; set an override in config if needed).

## 5. Run Voice Assistant From Command Line
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

## 6. Systemd Autostart Services
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

systemctl --user status pipewire wireplumber pipewire-pulse \
    raspotify voiceassist | grep -E "Active|Main PID"
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
python ~/voice_assist/spotify_auth.py
```

### Raspotify visible on phone but won't play (`snd_pcm_open ... Host is down`)
The **system** raspotify package is running and trying to open ALSA directly, which fails under PipeWire. Mask it and use the user service from 4.1 instead:
```bash
systemctl is-active raspotify          # system service (should be inactive/masked)
sudo systemctl disable --now raspotify
sudo systemctl mask raspotify
systemctl --user restart raspotify
journalctl --user -u raspotify -n 20 --no-pager
```
The user service uses `--backend pulseaudio`, so it reaches the output through `pipewire-pulse` inside your session. If the user unit is missing (`Unit raspotify.service does not exist`), create it per 4.1 first.

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
