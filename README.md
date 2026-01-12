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

The assistant is designed to be run on a **Raspberry Pi Zero 2W** accompanied with a **Seeed Studio ReSpeaker 2-mic HAT**.

## Repository Structure
- **`training/`**: Contains a colab notebook and a patch for training OpenWakeWord model in non-English languages
- **`wifi_config/`**: Contains a script for a captive portal to configure the WiFi connection
- **`voice_assist/`**: Contains the main Python scripts for running the Voice Assistant
- **`patches/`**: System patches

## Instructions
The instructions below are provided in the following order:
- **Obtaining a wake word model** - get already trained model or create your own
- **Prepare the system** - install required packages and apply patches
- **Install and run the assistant** - install the python code and run the assistant
- **Create 3D-printed enclosure** - 3D printed models and interconnections

## 🛠️ Obtaining a wake word model
There are two options: use an already trained model or train your own.

### 1. Use an already trained model
You can find a large collection of community-trained models (mostly in English) in the following repository:
https://github.com/fwartner/home-assistant-wakewords-collection

### 2. Train a custom wake word model
To train a custom wake word model in English language, you can use the following Google Colab notebook:
https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

To train a custom wake word model in other languages supported by Piper, you can use the same notebook with a simple patch that replace the English voice with another one. In the **training/** directory you will find two python scripts for generating the samples:
- **generate_samples_pt.py** - the original script included in the piper-sample-generator package, working with PyTorch models
- **generate_samples_onnx.py** - the modified script working with ONNX models

Once you find a piper voice model for your language, you can use the appropriated python script as follows:
- make a local copy of this script on your computer
- replace the model name in the script with the name of your desired model
- store the script in some url accessible from Google colab environment (e.g. github gist)
- run the notebook stored in the same directory

The current notebook and generate_samples.py in the **training/** directory are prepared for Bulgarian (bg-BG) language. If you want to use another language, then you can run the same notebook and then:
- click on [Show code](#2-train-a-custom-wake-word-model) at the end of the first cell
- find the line starting with "!wget "https://raw.githubusercontent.com/..."
- replace the link with the link to you url containing your generate_samples.py script
- run the cell to create and listen a test example
- run all cells and download the generated tflite model
- you can save a copy of the modified notebook and rename it as you want

To run the Bulgarian training notebook directly in Google Colab: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alexandreevbg/gemini-live-voice-assistant/blob/main/training/OpenWakeWord_model_BG.ipynb)

Besides the field for target_word, my notebook has a field for target_model_name, to avoid automatic conversion of the target_word to the model file name.

---
## ⚙️ Prepare the system
Preparations include the following installations:
- Raspberry Pi OS Lite (64-bit)
- Drivers for ReSpeaker 2-mic
- Shared virtual environment for Python apps
- Wi-Fi captive portal for wifi configuration

If you intend to improve or expand the capabilities of this device beyond the scope of this instruction, I recommend that you also install a backup solution.

## 1. Install Raspberry Pi OS Lite (64-bit)
I followed this procedure:
- Install and run **Raspberry Pi Imager** on your Windows, macOS, or Linux computer
- For device select **Raspberry Pi Zero 2W**
- For OS select Raspberry Pi OS (other) and then **Raspberry Pi OS Lite (64-bit)**
- For storage select your SD-Card connected to USB port
- Decide the hostname of the device (I used "chocko")
- Populate Localization and credentials parameters
- Enter the initial connection parameters for your Wi-Fi
- Enable the SSH connection

At the time of writing this instruction, the latest version of Raspberry Pi OS Lite (64-bit) was **6.12.47+rpt-rpi-v8** with preinstalled **Python 3.13.5**

## 2. Install Drivers for ReSpeaker 2-mic HAT
First check the version of your Respeaker 2-mic HAT: https://wiki.seeedstudio.com/how-to-distinguish-respeaker_2-mics_pi_hat-hardware-revisions/

For **Respeker 2-mic HAT V2.0** (still supported by Seeed Studio) follow the instructions provided by Seeed Studio: 
https://wiki.seeedstudio.com/respeaker_2_mics_pi_hat_raspberry_v2/#2-setup-the-driver-on-raspberry-pi

For **Respeker 2-mic HAT V1.0** (not supported by Seeed Studio anymore) follow the instructions below: 
1. Mount/connect the Respeaker 2-mic HAT to the Raspberry Pi Zero 2W
2. Get the updated driver sources from HinTak: 
   ```bash
   cd ~
   git clone -b v6.14 --single-branch https://github.com/HinTak/seeed-voicecard
   ```
3. Patch the file seeed-voicecard.c there
   ```bash
   wget https://raw.githubusercontent.com/alexandreevbg/gemini-live-voice-assistant/main/patches/seeed-voicecard.c
   mv ~/seeed-voicecard/seeed-voicecard.c ~/seeed-voicecard/
   ```
4. Run drivers installation
   ```bash
   cd ~/seeed-voicecard
   sudo ./install.sh
   ```
**For both versions:** To simplify Voice Assistant's audio configuration, we decided to disable HDMI audio available in Raspberry Pi and make ReSpeaker the only one audio device in the system. Also, since we do not intend to use Bluetooth, we disabled it as well. For this:
1. Edit the syste config.txt file:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
   Change the following lines:
   ```bash
   dtparam=audio=off
   dtoverlay=vc4-kms-v3d,noaudio
   ```
   Add the following lines to the end of the file:
   ```bash
   dtoverlay=disable-bt             # suspend bluetooth if not used
   dtoverlay=seeed-2mic-voicecard
   ```
   Save changes and reboot: 
   ```bash
   sudo reboot
   ```
2. Final test for ReSpeaker with ALSA
   ```bash
   alsamixer   # set Speaker = 75% and Capture = 75%
   sudo alsactl store
   arecord -r 16000 -c 1 -fS16_LE -t wav -d 5 test.wav
   aplay test.wav
   ```
## 3. Install a Shared Virtual Environment for Python Apps
To optimize performance on the Raspberry Pi Zero 2W, we use a "hybrid" environment strategy. We install heavy libraries (like numpy and gpiozero) globally via `apt` to save installation time and disk space, and then create a shared virtual environment that can access them.

1. Install system dependencies:
   ```bash
   sudo apt update
   sudo apt install git build-essential python3-dev python3-pip python3-venv python3-gpiozero python3-spidev python3-numpy -y
   ```
2. Create the shared virtual environment:
   ```bash
   python3 -m venv --system-site-packages ~/env
   ```
   This environment (`~/env`) will be used by both the Wi-Fi portal and the Voice Assistant.

## 4. Install Wi-Fi Captive Portal for WiFi Configuration
The Voice Assistant has two buttons connected to GPIO12 and GPIO13 available in the Groove port on Respeaker 2-mic. Pressing both buttons together during the system boot activates the Wi-Fi captive portal having:
- SSID: "Chochko-WiFi-Setup" 
- password: "chochko123"
- the portal is available on standard address 192.168.4.1
You can open the portal with your phone or computer, select new SSID from a list, and populate the password, all to be used after automatic reboot. If the new SSID disappeared, then after next reboot Voice Assistant will try to connect to the previous SSID.

1. Install the Wi-Fi config application
   ```bash
   cd ~
   git clone --depth=1 https://github.com/alexandreevbg/gemini-live-voice-assistant.git temp-repo
   mv temp-repo/wifi-config ~/
   rm -rf temp-repo
   ```
2. Install the LED driver library into the shared environment:
   ```bash
   ~/env/bin/pip install apa102-pi
   ```
3. Run and test the wifi-config manually
   ```bash
   sudo python ~/wifi-config/wifi_portal.py
   ```
4. Create a oneshot service for the portal
   ```bash
   sudo cp wifi-config/wifi-config.service /etc/systemd/system/
   sudo systemctl enable wifi-config.service
   sudo systemctl start wifi-config.service
   ```
   
## 5. Install a Backup Solution (optional)
For a backup solution we decided to use **RonR-RPi-image-utils** that creates a complete backup of a Raspberry Pi quickly and efficiently; these backups are rendered in the form of an "image file". 

1. Install NFS and the backup application
   ```bash
   sudo apt update
   sudo apt install nfs-common install git -y
   git clone https://github.com/seamusdemora/RonR-RPi-image-utils
   sudo install --mode=755 ./RonR-RPi-image-utils/image-* /usr/local/sbin
   ```
2. Mount an external drive where to store the image and run backup
   ```bash
   sudo mount -t nfs -o proto=tcp,port=2049 192.168.1.5:/nfs/<target directory> /mnt
   sudo RonR-RPi-image-utils/image-backup -o -v
   ```
   After running the command, enter the name of the target image, then answer 'y' on the next questions and that's it. The result image is less than 4 GB. You may compress it by 7-Zip to *.img.xy file with less than 1 GB size.
   You can restore from the initial or compressed image by Rasbperri Pi Imager. 

## 🎙️ Install and run Voice Assistant

### Prerequisites
- Python 3.9+
- A working microphone

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YourUsername/YourRepositoryName.git
   cd YourRepositoryName
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/Mac:
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Usage

Run the assistant from the source directory:
```bash
python voice_assist/main.py
```