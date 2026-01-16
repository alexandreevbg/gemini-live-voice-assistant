# Gemini Live Voice Assistant

> **⚠️ WORK IN PROGRESS**
> This repository is currently under construction. The code and models provided here are in active development.

## Project Overview
This project contains instructions, tools and source code for creating a Multilingual Voice Assistant and includes:
- Direct integration with **Gemini Live API**
- On-device wake word detection using **OpenWakeWord** algorithms
- Optional integration with **Spotify**
- Optional integration with **Home Assistant**
- Optional integration with **other services**

The assistant is designed to run on a **Raspberry Pi Zero 2W** accompanied by a **Seeed Studio ReSpeaker 2-mic HAT**.

## Repository Structure
- **`training/`**: Contains a colab notebook and a patch for training OpenWakeWord models in non-English languages
- **`wifi_config/`**: Contains a script for a captive portal to configure the WiFi connection
- **`voice_assist/`**: Contains the main Python scripts for running the Voice Assistant
- **`patches/`**: System patches
---
# Instructions
The instructions below are arranged in the following sections:
- **Obtaining a wake word model** - get a pre-trained model or create your own
- **Prepare the system** - install required packages and apply patches
- **Install and run the assistant** - install the Python code and run the assistant
- **Create 3D-printed enclosure** - 3D printed models and interconnections

## 🛠️ Obtaining a wake word model
There are two options: use a pre-trained model or train your own.

### 1. Use a pre-trained model
A large collection of community-trained models (mostly in English) is available in the following repository:
https://github.com/fwartner/home-assistant-wakewords-collection

### 2. Train a custom wake word in English
To train a custom wake word model in English, use the following Google Colab notebook:
https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

### 3. Train a custom wake word in other languages
To train a custom wake word model in other languages supported by Piper, use the same notebook with a minor modification and a patch that replaces the English voice with another one. In the **training/** directory you will find the modified notebook, as well as three Python scripts for generating the samples:
- **generate_samples_pt.py** - the original script included in the piper-sample-generator package, working with PyTorch models
- **generate_samples_onnx.py** - the modified script working with ONNX models
- **generate_samples.py** - the final script to be downloaded by the modified notebook

Once you find a piper voice model for your language, use the appropriate Python script as follows:
- make a local copy of the appropriate script on your computer
- rename it to "generate_samples.py"
- replace the model name in the script with the name of your desired model
- store the script at a URL accessible from the Google Colab environment (e.g. Github Gist)
- run the notebook stored in the same directory

The current notebook and generate_samples.py in the **training/** directory are prepared for Bulgarian (bg-BG) language. To use it with another language, run the same notebook and then:
- click on [Show code](#2-train-a-custom-wake-word-model) at the end of the first cell
- find the line starting with "!wget "https://raw.githubusercontent.com/..."
- replace the link on this line with the link to your URL containing your generate_samples.py script
- run the cell to create and listen to a test example
- run all cells and download the generated tflite model
- save a copy of the modified notebook and rename it as you want

To run the Bulgarian training notebook directly in Google Colab: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alexandreevbg/gemini-live-voice-assistant/blob/main/training/OpenWakeWord_model_BG.ipynb)

In addition to the `target_word` field, the notebook includes a `target_model_name` field to prevent the automatic conversion of the target word into the model filename.

---
## ⚙️ Prepare the system
Preparations include the following installations:
- Raspberry Pi OS Lite (64-bit)
- Drivers for ReSpeaker 2-mic
- Shared virtual environment for Python apps
- Wi-Fi captive portal for Wi-Fi configuration

If you intend to improve or expand the capabilities of this device beyond the scope of this guide, then I would recommend also to install a backup solution.

## 1. Install Raspberry Pi OS (64-bit) Lite
Follow this procedure to install the latest Raspberry Pi OS:
- Install and run **Raspberry Pi Imager** on your Windows, macOS, or Linux computer
- For the device, select **Raspberry Pi Zero 2W**
- For the OS, select **Raspberry Pi OS (other)** and then **Raspberry Pi OS (Legacy, 64-bit) Lite**.
  > [IMPORTANT]: As of mid-2024, the standard "Raspberry Pi OS Lite" points to an unstable testing version (Debian Trixie). The "Legacy" version points to the required **stable** version (Debian Bookworm), which is necessary for driver compatibility.
- For the storage, select your SD-Card connected to USB port
- Decide the hostname of the device (I used "chocko")
- Configure Localization and credentials parameters
- Enter the initial connection parameters for your Wi-Fi
- Enable the SSH connection and write OS on SD-Card
- Connect the SD-Card and ReSpeaker to the Raspberry Pi Zero 2W and power it on

At the time of writing, the stable Raspberry Pi OS (Legacy, 64-bit) Lite is based on **Debian 12 (Bookworm)**, running Kernel **6.12.47+rpt-rpi-v8** with preinstalled **Python 3.11.2**.

## 2. Install Drivers for ReSpeaker 2-mic HAT
First, identify the version of your Respeaker 2-mic HAT: https://wiki.seeedstudio.com/how-to-distinguish-respeaker_2-mics_pi_hat-hardware-revisions/

For **ReSpeaker 2-mic HAT V2.0** there is an original instruction provided by Seeed Studio, and you can follow it if you can make some minor changes on the fly: https://wiki.seeedstudio.com/respeaker_2_mics_pi_hat_raspberry_v2/#2-setup-the-driver-on-raspberry-pi <br>
**or**
- follow the compact version of the same, aligned to the latest Raspberry Pi OS:
1. Build the driver for audio codec TLV320AIC3104:
   ```bash
   ## Install kernel
   sudo apt update
   sudo apt install raspberrypi-kernel-headers -y
   sudo apt install flex bison libssl-dev bc build-essential libncurses5-dev libncursesw5-dev git device-tree-compiler -y
   git clone --depth=1 --branch rpi-6.12.y https://github.com/raspberrypi/linux.git

   ## Copy code and a Makefile
   mkdir ~/tlv320aic3x_i2c_driver
   cd ~/tlv320aic3x_i2c_driver
   cp ~/linux/sound/soc/codecs/tlv320aic3x.c ~/tlv320aic3x_i2c_driver/
   cp ~/linux/sound/soc/codecs/tlv320aic3x.h ~/tlv320aic3x_i2c_driver/
   cp ~/linux/sound/soc/codecs/tlv320aic3x-i2c.c ~/tlv320aic3x_i2c_driver/
   wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/patches/Makefile

   ## Build the driver 
   make
   sudo make install
   sudo modprobe snd-soc-tlv320aic3x-i2c

   ## Check logs
   lsmod | grep tlv320
   dmesg | grep tlv320
   ```
2. Install the overlay
   ```bash
   curl https://raw.githubusercontent.com/Seeed-Studio/seeed-linux-dtoverlays/refs/heads/master/overlays/rpi/respeaker-2mic-v2_0-overlay.dts -o respeaker-2mic-v2_0-overlay.dts
   dtc -I dts respeaker-2mic-v2_0-overlay.dts -o respeaker-2mic-v2_0-overlay.dtbo
   sudo dtoverlay respeaker-2mic-v2_0-overlay.dtbo
   sudo cp respeaker-2mic-v2_0-overlay.dtbo /boot/firmware/overlays
   ```

3. Add overlay configuration to config.txt:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Add the following line to the end of the file:
   ```bash
   dtoverlay=respeaker-2mic-v2_0-overlay
   ```

For **ReSpeaker 2-mic HAT V1.0** (deprecated) follow the instructions below: 
1. Get the updated driver sources from HinTak: 
   ```bash
   cd ~
   git clone -b v6.14 --single-branch https://github.com/HinTak/seeed-voicecard
   ```
2. Patch the file seeed-voicecard.c file
   ```bash
   wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/patches/seeed-voicecard.c
   mv ~/seeed-voicecard/seeed-voicecard.c ~/seeed-voicecard/
   ```
3. Build and install the driver
   ```bash
   cd ~/seeed-voicecard
   sudo ./install.sh
   ```
4. Add overlay configuration to config.txt:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Add the following line to the end of the file:
   ```bash
   dtoverlay=seeed-2mic-voicecard
   ```

**For both versions:** To simplify the Voice Assistant's audio configuration, disable the Raspberry Pi's onboard HDMI audio, making the ReSpeaker the sole audio device. Also, since Bluetooth is not used, disable it as well. For this:
1. Edit the system config.txt file:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Change the following lines:
   ```bash
   dtparam=audio=off
   dtoverlay=vc4-kms-v3d,noaudio
   ```
   And add the following line to the end of the file:
   ```bash
   dtoverlay=disable-bt             # disable bluetooth if not used
   ```
   Save changes and reboot: 
   ```bash
   sudo reboot
   ```
2. Final test for ReSpeaker with ALSA
   ```bash
   aplay -l          # you should see only the seeed2mic... device
   arecord -l        # as card 0
   alsamixer         # set Speaker and Capture = 75%
   arecord -r 16000 -c 1 -fS16_LE -t wav -d 5 test.wav
   aplay test.wav
   ```
## 3. Install a Shared Virtual Environment for Python Apps
To optimize performance on the Raspberry Pi Zero 2W, use a "hybrid" environment strategy: install heavy libraries (like numpy and gpiozero) globally via `apt` to save installation time and disk space, and then create a shared virtual environment that can access them.

1. Install system dependencies:
   ```bash
   sudo apt update
   sudo apt install git build-essential python3-dev python3-pip python3-venv python3-gpiozero python3-spidev python3-numpy -y
   ```
2. Create the shared virtual environment:
   ```bash
   python3 -m venv --system-site-packages ~/.venv
   ```
   This environment (`~/.venv`) will be used by both the Wi-Fi portal and the Voice Assistant.

## 4. Install Wi-Fi Captive Portal for WiFi Configuration
The Voice Assistant has two buttons connected to GPIO12 and GPIO13 available in the Grove port on ReSpeaker 2-mic. Pressing and holding both buttons during system boot activates the Wi-Fi captive portal having:
- SSID: "Chochko-WiFi-Setup" 
- password: "chochko123"
- the portal is available on the standard address 192.168.4.1
You can open the portal with your phone or computer, select a new SSID from the list, and enter the password. These settings will be used after an automatic reboot. If the new SSID is unavailable, the Voice Assistant will attempt to connect to the previous SSID after the next reboot.

1. Install the Wi-Fi config application
   ```bash
   cd ~
   git clone --depth=1 https://github.com/alexandreevbg/gemini-live-voice-assistant.git temp-repo
   mv temp-repo/wifi-config ~/
   rm -rf temp-repo
   ```
2. Install the LED driver library into the shared environment:
   ```bash
   ~/.venv/bin/pip install --upgrade pip setuptools
   ~/.venv/bin/pip install apa102-pi
   ```
3. Enable SPI interface in the Raspberry Pi configuration:
   ```bash
   sudo raspi-config
   ```
   Select "Interfacing Options" -> "SPI" -> "Yes".
4. Run and test the Wi-Fi configuration manually
   ```bash
   sudo ~/.venv/bin/python ~/wifi-config/wifi_portal.py
   ```
5. Create a one-shot service for the portal
   ```bash
   sudo nano /etc/systemd/system/wifi-config.service
   ```
   Add the following content to the file. This service runs as `root` after the network comes online, executing the portal script from the correct directory and using the Python virtual environment.
   > **Note**: Replace `chochko` with your actual username if it's different.
   ```ini
   [Unit]
   Description=Wi-Fi Configuration Portal
   Wants=network-online.target
   After=network-online.target

   [Service]
   Type=oneshot
   User=root
   WorkingDirectory=/home/chochko/wifi-config
   ExecStart=/home/chochko/.venv/bin/python /home/chochko/wifi-config/wifi_portal.py

   [Install]
   WantedBy=multi-user.target
   ```
   Then, enable the service to run on boot:
   ```bash
   sudo systemctl enable wifi-config.service
   ```
Of course, you can change the SSID name/password and/or the portal address in the file `wifi-config/wifi_portal.py`.   
   
## 5. Install a Backup Solution (optional)
For a backup solution, use **RonR-RPi-image-utils**, which quickly and efficiently creates a complete backup of a Raspberry Pi in the form of an image file.

1. Install NFS and the backup application
   ```bash
   sudo apt update
   sudo apt install nfs-common git -y
   git clone https://github.com/seamusdemora/RonR-RPi-image-utils
   sudo install --mode=755 ./RonR-RPi-image-utils/image-* /usr/local/sbin
   ```
2. Mount an external drive to store the image and run backup
   ```bash
   sudo mount -t nfs -o proto=tcp,port=2049 <NAS IP address>/<target directory> /mnt
   sudo image-backup -o -v
   ```
   After running the command, enter the name of the target image to /mnt/<target directory>, then answer with [OK] and 'y' to the subsequent questions. The resulting image is typically less than 4 GB. You may compress it using 7-Zip to a *.img.xz file with a size of less than 1 GB. 
   You can restore from the initial or compressed image using Raspberry Pi Imager. 

## 🎙️ Install and run Voice Assistant
 ## 1. Install libraries
 Install the required Python libraries
   ```bash
   sudo apt update
   sudo apt install -y python3-pip python3-dev
   sudo apt install -y libasound2-dev portaudio19-dev libportaudio2 libportaudiocpp0   
   sudo apt install -y libasound2-dev portaudio19-dev libportaudio2 libportaudiocpp0 libopenblas-dev
   ```
Install the required math libraries and Gemini API
   ```bash
   ~/.venv/bin/pip install --upgrade pip setuptools wheel
   ~/.venv/bin/pip install "numpy<2" tflite-runtime
   ~/.venv/bin/pip install pyaudio
   ~/.venv/bin/pip cache purge
   ~/.venv/bin/pip install -q -U google-genai
   ```