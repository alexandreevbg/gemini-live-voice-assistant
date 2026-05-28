## Optional Tools
This part guides through installation of three optional, but recommended tools:
1. System backup tool - a fast and efficient backup tool for IoT project
2. Headless Wi-Fi captive portal - if you plan to travel with your device
3. Raspotify - Spotify Connect client for Raspberry Pi - if you plan to play music on your device  
---

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
   After running the command, enter the name of the target image to /mnt/image_name.img, then answer with [OK] and 'y' to the subsequent questions. The resulting image is typically less or about than 4 GB. You may compress it using 7-Zip to a *.img.xz file with a size of less than 1 GB. 
   Then, you can flash the image by Raspberry Pi Imager from the resulting or compressed image. 

---

## 2. Python Virtual Environment
We use a shared virtual environment (`~/.venv`) to manage Python dependencies efficiently and consistently across different project components.

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv --system-site-packages ~/.venv
```

### 3. Headless Wi-Fi captive portal
The ReSpeaker 2-mic HAT has on-board button connected to GPIO17. Holding the button during system boot activates the Wi-Fi captive portal having:
- SSID: "Chochko-WiFi-Setup" 
- password: "chochko123"
- the portal is available on the standard address 192.168.4.1

You can open the portal with your phone or computer, select a new SSID from the list, enter the password, and press Connect. The Respeaker will try to connect and if successful then reboot. If after the next reboot the new SSID is unavailable, then the device will attempt to connect to the any previous SSID.

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
3. Test the Wi-Fi configuration manually
   ```bash
   sudo ~/.venv/bin/python ~/wifi-config/wifi_portal.py
   ```
   When run, the device should blink once with blue light
4. Create a one-shot service for the portal
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
The device should blink once with blue light when it's ready. Of course, you can change the SSID name/password and/or the portal address in the file `wifi-config/wifi_portal.py`.   
```bash

```
---

### 3. Raspberry-Pi - Spotify Connect client
```bash

```
---
[Return to Main README](../README.md)
