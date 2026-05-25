# Platform: Hardware, OS, and Drivers

This guide covers the base layer of the assistant, including hardware specifications, OS installation, and driver setup for the ReSpeaker 2-mic HAT v2.0.

----

## Hardware Requirements
| Component | Specification |
|-----------|---------------|
| **SBC** | Raspberry Pi Zero 2W |
| **Audio** | Seeed Studio ReSpeaker 2-Mic HAT v2.0 |
| **SD Card** | 16GB+ Class 10 |

## 1. Install Raspberry Pi OS (64-bit) Lite

Use **Raspberry Pi Imager** to flash your SD card:
- **Device:** Raspberry Pi Zero 2W
- **OS:** Raspberry Pi OS Lite (64-bit). This project is tested on **Debian 13 (Trixie)** / Testing branch for Python 3.13 support.
- **Settings:** Enable SSH, set your username (e.g., `chochko`), and configure your Wi-Fi credentials.

## 2. Install Drivers for ReSpeaker 2-mic HAT

### Preliminary System Configuration
Optimize the system for headless use and speed up SSH login:

   ```bash
   # Enable passwordless sudo for the current user
   echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/010_nopasswd

   # Disable dynamic MOTD scripts to fix long login delays on Pi Zero 2W
   sudo chmod -x /etc/update-motd.d/*
   ```

Disable onboard audio and Bluetooth to prevent conflicts and save resources:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Change the following lines:
   ```bash
   dtparam=audio=off
   dtoverlay=vc4-kms-v3d,noaudio # Ensure this line is present and uncommented
   ```
   And add the following line to the end of the file:
   ```bash
   dtoverlay=disable-bt             # disable bluetooth if not used
   ```

### ReSpeaker 2-mic HAT v2.0 Driver Setup
Since newer kernels require manual building of the TLV320AIC3104 codec driver:

#### Build the Driver
   ```bash
   ## Install kernel
   sudo apt update
   sudo apt install flex bison libssl-dev bc build-essential libncurses-dev git device-tree-compiler -y
   git clone --depth=1 --branch rpi-6.12.y https://github.com/raspberrypi/linux.git

   ## Copy code and a Makefile
   mkdir ~/tlv320aic3x_i2c_driver
   cd ~/tlv320aic3x_i2c_driver
   cp ~/linux/sound/soc/codecs/tlv320aic3x.c .
   cp ~/linux/sound/soc/codecs/tlv320aic3x.h .
   cp ~/linux/sound/soc/codecs/tlv320aic3x-i2c.c .

   # Use the Makefile provided in the 01-platform directory of this repo
   wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/01-platform/Makefile

   ## Build the driver 
   make
   sudo make install
   sudo modprobe snd-soc-tlv320aic3x-i2c
   ```

#### Install the Overlay
   ```bash
   curl -L https://raw.githubusercontent.com/Seeed-Studio/seeed-linux-dtoverlays/master/overlays/rpi/respeaker-2mic-v2_0-overlay.dts -o respeaker-2mic-v2_0-overlay.dts
   dtc -I dts respeaker-2mic-v2_0-overlay.dts -o respeaker-2mic-v2_0-overlay.dtbo
   sudo cp respeaker-2mic-v2_0-overlay.dtbo /boot/firmware/overlays/
   ```

Add the overlay to `config.txt`:
   ```bash
echo "dtoverlay=respeaker-2mic-v2_0-overlay" | sudo tee -a /boot/firmware/config.txt
sudo reboot
   ```

## 3. Audio Testing & ALSA Calibration

Check if the card is detected:
   ```bash
   aplay -l
   arecord -l
   ```
It should appear as `card 0: seeed2micvoicec`.

### Set Gains via Alsamixer
   Run `alsamixer` and configure the following important sliders:
   - **PCM**: Master output volume - set to 100%
   - **Line DAC**: Max output voulme limit - set to 66
   - **PGA / Capture**: microphone Analog Gain - set to ~34%
   - **AGC**: Automatic Gain Control - recommended to turn it **OFF**

Save levels with:
   ```bash
   sudo alsactl store
   ```   

Test recording:
   ```bash
   arecord -r 16000 -c 1 -f S16_LE -t wav -d 5 test.wav
   aplay test.wav
   ```

Cleanup source fles:
   ```bash
   cd ~ 
   rm -rf ~/linux
   ```

---
[Return to Main README](../README.md)
