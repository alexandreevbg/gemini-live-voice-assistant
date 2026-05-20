# Environment & Audio Stack
This section details the setup of the Python virtual environment, the PipeWire audio server with Acoustic Echo Cancellation (AEC), and essential configuration files.

## 1. Python Virtual Environment
We use a shared virtual environment (`~/.venv`) to manage Python dependencies efficiently and consistently across different project components.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv --system-site-packages ~/.venv
```

## 2. Configure Environment Variables
Download the .env template from the repository to your home directory
```bash
wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/02-environment/.env -O ~/.env
nano ~/.env
```
This file stores sensitive environment variables, such as API keys and tokens. You should replace at least "YOUR_GEMINI_API_KEY" with your actual API_KEY. You can obtain your API_KEY from the [Google AI Studio](https://aistudio.google.com/). Other variables are optional. You can keep them commented out for now. If you have smart home (HA) or Spotify set up, you can uncomment the corresponding variables and add your tokens and keys.   

Add those two lines to your `~/.bashrc` file to automatically load your environment variables and activate your Python virtual environment when you start a new shell session.
```bash
echo 'set -a; source ~/.env; set +a' >> ~/.bashrc
echo 'source ~/.venv/bin/activate' >> ~/.bashrc
``` 

## 3. Audio Stack: PipeWire + AEC
PipeWire is used to manage audio streams and enable Acoustic Echo Cancellation (AEC), allowing the microphone to effectively filter out audio being played by the speaker.

Install PipeWire and its related components.
```bash
sudo apt install -y \
    pipewire \
    pipewire-alsa \
    pipewire-audio \
    wireplumber \
    libspa-0.2-modules
```    
Validate installation
```bash
pipewire --version
```
The expected version is 1.4.2 or newer.

## 4. Set AEC config
Create the necessary configuration directories and files for PipeWire and WirePlumber.
```bash
mkdir -p ~/.config/pipewire/pipewire.conf.d ~/.config/wireplumber/wireplumber.conf.d
```

Set Clock Configuration
```bash
nano ~/.config/pipewire/pipewire.conf.d/10-clock.conf
```
Copy/paste the following text into the file:
```text
context.properties = {
    default.clock.rate = 48000
    default.clock.allowed-rates = [ 48000 ]
    default.clock.quantum = 480
    default.clock.min-quantum = 480
    default.clock.max-quantum = 480
}
```

Set Echo Cancellation Configuration
```bash
nano ~/.config/pipewire/pipewire.conf.d/99-echo-cancel.conf
```
Copy/paste the following text into the file:
```text
context.modules = [
  {
    name = libpipewire-module-echo-cancel
    args = {
      library.name = "aec/libspa-aec-webrtc"

      # The AEC engine now runs in MONO
      audio.rate = 48000
      audio.channels = 1
      audio.position = [ MONO ]

      webrtc.high_pass_filter = true
      webrtc.noise_suppression = true # You can likely turn this on now with the saved CPU
      webrtc.voice_detection = false
      webrtc.gain_control = false
      webrtc.extended_filter = false

      capture.props = {
        node.name = "aec_capture"
        target.object = "alsa:acp:seeed2micvoicec:2:capture"
        # Hardware stays Stereo to keep driver happy
        audio.channels = 2
        audio.position = [ FL FR ]
        node.force-rate = 48000
        node.force-quantum = 480
      }
      source.props = {
        node.name = "aec_input"
        node.description = "Echo-Cancelled Mono Mic"
        media.class = "Audio/Source"
        audio.channels = 1
        audio.position = [ MONO ]
        priority.driver = 1500
        priority.session = 1500      
	  }
      sink.props = {
        node.name = "aec_output"
        node.description = "Echo-Cancel Mono Reference"
        media.class = "Audio/Sink"
        audio.channels = 1
        audio.position = [ MONO ]
        priority.driver = 1500
        priority.session = 1500      
	  }
      playback.props = {
        node.name = "aec_playback"
        target.object = "alsa_output.platform-soc_sound.stereo-fallback"
        # Playback remains Mono (PipeWire will mix it to the single speaker)
        audio.channels = 1
        audio.position = [ MONO ]
        node.force-rate = 48000
        node.force-quantum = 480
      }
    }
  }
]
```

Force Quantum Rate for ALSA
```bash
nano ~/.config/wireplumber/wireplumber.conf.d/50-force-480.conf
```
Copy/paste the following text into the file:
```text
monitor.alsa.rules = [
  {
    matches = [ { node.name = "~alsa_input.*" } ]
    actions = { update-props = { node.force-quantum = 480 } }
  },
  {
    matches = [ { node.name = "~alsa_output.*" } ]
    actions = { update-props = { node.force-quantum = 480 } }
  }
]
```

## 5. Wipe the cached state and start fresh

Wipe any cached PipeWire state and restart the services to apply the new configuration.
```bash
systemctl --user stop pipewire wireplumber pipewire-pulse
rm -rf ~/.local/state/pipewire/*
systemctl --user start pipewire wireplumber pipewire-pulse
```

## 6. Force the metadata (Optional, but recommended)
```bash
pw-metadata -n settings 0 clock.force-rate 48000
pw-metadata -n settings 0 clock.force-quantum 480
```

## 7. Check and set the default audio nodes
Identify the IDs for `aec_input` and `aec_output` and set them as default.
```bash
wpctl status # Look for aec_input and aec_output IDs
```
Expected results
```text
# ├─ Filters:
# │    - echo-cancel-XXXX-30
# │      XX. aec_capture    [Stream/Input/Audio]
# │  *   XX. aec_input      [Audio/Source]
# │  *   XX. aec_output     [Audio/Sink]
# │      XX. aec_playback   [Stream/Output/Audio]
```
If the '*' are missing, manually set the default nodes (replace 38 and 39 with actual IDs):
```bash 
wpctl set-default 38	# aec_input
wpctl set-default 39	# aec_output
```

Reboot the system to ensure all changes are applied correctly.
```bash
sudo reboot
```

Verify pipewire is working as expected
```bash
systemctl --user status pipewire wireplumber pipewire-pulse
```

# Test AEC
Get music clip
```bash
wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/02-environment/music_48k.wav
```

Play music and record speech at the same time for 10 sec
```bash
pw-play music_48k.wav &
pw-record test.wav &
sleep 10
killall pw-play pw-record
sleep 2
pw-play test.wav
```
Run alsamixer in terminal 2 and find the max volume when the above test is working well.

---
[Return to Main README](../README.md)
