# Chochko: Multilingual Gemini Voice Assistant

A high-performance, private voice assistant for Raspberry Pi Zero 2W, featuring multilingual wake word detection and Google Gemini Live integration.

> **⚠️ WORK IN PROGRESS**
> This repository is currently under construction. The code and models provided here are in active development.

## ✨ Project Preview

Chochko is a cutting-edge voice assistant designed for the **Raspberry Pi Zero 2W**, leveraging the **Seeed Studio ReSpeaker 2-mic HAT v2.0** for robust audio input. Key highlights include:

- **Gemini Live Integration:** Seamless conversational AI powered by Google's **Gemini Live API**.
- **On-Device Wake Word Detection:** Efficient and private wake word recognition directly on the device.
- **Advanced Audio Processing:** Utilizes Pipewire with Acoustic Echo Cancellation (AEC) for clear voice capture even during audio playback.
- **Smart Home Connectivity:** Optional integrations with **Home Assistant** for smart device control and **Spotify** for music streaming.
---

## 🚀 Implementation Roadmap

Follow these steps in order to build your assistant:

----
### 1. [Platform Setup](./01-platform/platform.md)
Hardware specifications, flashing Raspberry Pi OS (Trixie), and compiling ReSpeaker 2-mic v2.0 drivers.

### 2. [Environment & Audio Stack](./02-environment/environment.md)
Setting up Pipewire with AEC (Acoustic Echo Cancellation), Python `venv`, ALSA configurations, and system `.env`/`json` files.

### 3. [Tools](./03-tools/tools.md)
Instructions for the system backup tool, headless Wi-Fi captive portal, and Raspotify integration.

### 4. [Wake Word Training](./04-training/training.md)
Using the Google Colab notebook to train custom models for English and non-English wake words.

### 5. [Voice Assistant Core](./05-voice_assist/voice_assistant.md)
Installing the main Python package, dependencies, and Gemini API integration.

### 6. [Enclosure & Assembly](./06-enclosure/enclosure.md)
3D printing files (STL), exploded component views, and final hardware wiring diagrams.

---

----
-----
## 📜 License
This project is licensed under the MIT License - see the LICENSE file for details.
----
