# Tools: Python Environment, WiFi Captive Portal, Backup, Raspotify

This part guides through the setup of the Python virtual environment and installation of three optional, but recommended tools:
1. System backup tool - a fast and efficient backup tool for IoT project
2. Headless Wi-Fi captive portal - if you plan to travel with your device
3. Raspotify - Spotify Connect client for Raspberry Pi - if you plan to play music on your device  

You can install the optional tools later.

---

## 1. Python Virtual Environment
We use a shared virtual environment (`~/.venv`) to manage Python dependencies efficiently and consistently across different project components.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv --system-site-packages ~/.venv
```

Download the project locally
```bash
cd ~
git clone https://github.com/alexandreevbg/gemini-live-voice-assistant.git
```

## 2. Install the optional tools

### 1. System backup tool
For a backup solution, use **RonR-RPi-image-utils**, which quickly and efficiently creates a complete backup of a Raspberry Pi in the form of an image file.

Install NFS and the backup application
   ```bash
   sudo apt update
   sudo apt install nfs-common git -y
   git clone https://github.com/seamusdemora/RonR-RPi-image-utils
   sudo install --mode=755 ./RonR-RPi-image-utils/image-* /usr/local/sbin
   ```
Mount an external drive to store the image and run backup
   ```bash
   sudo mount -t nfs -o proto=tcp,port=2049 <NAS IP address>/<target directory> /mnt
   sudo image-backup -o -v
   ```
   After running the command, enter the name of the target image to /mnt/image_name.img, then answer with [OK] and 'y' to the subsequent questions. The resulting image is typically less than or about 4 GB. You may compress it using 7-Zip to a *.img.xz file with a size of less than 1 GB. Then, you can flash the image by Raspberry Pi Imager from the resulting or compressed image. 

---

### 2. Headless Wi-Fi captive portal
#### Reading the lights
| Light | What it means | What to do |
|-------|---------------|------------|
| 💙 **Blue flash** (once) | Starting up | Nothing — just booting |
| ❤️ **Red blinking** | Can't reach the internet | Wait, or press the button to set up Wi-Fi |
| 💙 **Blue pulsing** | Setup mode is on | Connect your phone (see below) |
| ⚫ **Off** | Connected and working | Nothing — you're good |

After power-on, the device flashes blue once, then tries to connect to a previously used Wi-Fi network. If it gets online, the light stays off and the device is ready. 
If it can't connect, the device blinks red 10 times, then tries again. This cycle repeats until a connection is established — or until you press the button to open the captive portal.
- **SSID**: Chochko-WiFi-Setup
- **Password**: chochko123
- **Portal address**: 192.168.4.1

Connect with your phone or computer, select a network from the list, enter the password, and press Connect. The device tries to connect and then reboots (whether or not it succeeded — if it failed, you'll see red blinking again and can retry).

If you don't finish within 300 seconds, the portal closes and the device returns to red blinking. Press the button to reopen the portal, or disconnect the power to reboot.

You can also open the captive portal at any time by pressing and holding the button during boot until the light starts pulsing blue.

1. Install the LED driver library into the shared environment:
   ```bash
   ~/.venv/bin/pip install --upgrade pip setuptools
   ~/.venv/bin/pip install apa102-pi
   ```
2. Enable SPI interface in the Raspberry Pi configuration:
   ```bash
   sudo raspi-config
   ```
   Select "Interfacing Options" -> "SPI" -> "Yes".
3. Get the source scripts
   ```bash
   mv gemini-live-voice-assistant/02-tools/wifi-portal ~/wifi-config
   ```
4. Test the Wi-Fi configuration manually
   ```bash
   sudo ~/.venv/bin/python ~/wifi-config/wifi_portal.py
   ```
   When run, the device should blink once with blue light
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
   sudo reboot
   ```
You can change the captive portal parameters as SSID name/password and/or the portal address in the file `wifi-config/wifi_portal.py`.   

---

### 3. Raspotify - Spotify Connect client
To integrate with Spotify, we need to install **raspotify**. It creates a network player compatible with Spotify and Home Assistant.

1. install raspotify:

   ```bash
   sudo apt update
   curl -sL https://dtcooper.github.io/raspotify/install.sh | sh
   sudo systemctl status raspotify
   ```

2. Test the installation:
Run Spotify on your phone connected to the same WiFi SSID. Play some music, open devices menu, and select raspotify(chochko).
  
---
[Return to Main README](../README.md)
