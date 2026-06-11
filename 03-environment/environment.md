# Environment & Audio Stack
This section details the setup of the PipeWire audio server with Acoustic Echo Cancellation (AEC), and essential configuration files.

## 1. Install PipeWire + AEC
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

## 2. Set AEC config
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
      webrtc.noise_suppression = true
      webrtc.voice_detection = false
      webrtc.gain_control = true
      webrtc.experimental_agc = true
      webrtc.limiter = true
      webrtc.extended_filter = true
      webrtc.delay_agnostic = true
      webrtc.experimental_ns = true
      webrtc.transient_suppression = true

      capture.props = {
        node.name = "aec_capture"
        # Use the platform-soc name for better stability across kernel updates
        target.object = "alsa_input.platform-soc_sound.analog-stereo"
        
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
        target.object = "alsa_output.platform-soc_sound.analog-stereo"
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

## 3. Wipe the cached state and start fresh

Wipe any cached PipeWire state and restart the services to apply the new configuration.
```bash
systemctl --user stop pipewire wireplumber pipewire-pulse
rm -rf ~/.local/state/pipewire/*
systemctl --user start pipewire wireplumber pipewire-pulse
```

## 4. Force the metadata (Optional, but recommended)
```bash
pw-metadata -n settings 0 clock.force-rate 48000
pw-metadata -n settings 0 clock.force-quantum 480
```

## 5. Check and set the default audio nodes
Identify the IDs for `aec_input` and `aec_output` and set them as default.
> **Note**: This step is critical. WirePlumber may default back to the hardware nodes until you manually "lock" the defaults. This setting is saved persistently in `~/.local/state/wireplumber/`.

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

And check the default audio devices again
```bash
wpctl status # Look for aec_input and aec_output IDs
```
## 6. Force PCM slider to max volume
When start, PipeWire often set the PCM volume to 35% (80, 80). The simplest way to make it 100% is to run a single shoot service. For this:
1. Create new service file in the local systemd user directory:
```bash
mkdir -p ~/.config/systemd/user/
nano ~/.config/systemd/user/fix-pcm.service
```  

2. Paste the following configuration:
```text
[Unit]
Description=Force ReSpeaker PCM Volume to 100% after PipeWire starts
After=pipewire.service wireplumber.service

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/amixer -c 0 sset PCM 100%
RemainAfterExit=yes

[Install]
WantedBy=default.target
```

3. Save it and enable the service
```bash
systemctl --user daemon-reload
systemctl --user enable fix-pcm.service
```

4. reboot
```bash
sudo reboot
```

## 7. Test AEC
Play music and record speech at the same time for 10 sec
```bash
pw-play gemini-live-voice-assistant/03-environment/music_48k.wav &
pw-record test.wav &
sleep 10
killall pw-play pw-record
sleep 2
pw-play test.wav
```
Run als0amixer in terminal 2, select card 0 "seeed2mic..." and find the max volume of Line DAC slider, while when the above test is working well.

---
[Return to Main README](../README.md)
