# Chochko: Multilingual Gemini Voice Assistant

A high-performance, private voice assistant, featuring multilingual wake word detection and Google Gemini Live integration.

## Project Overview
Project highlights:
- **Hardware:** Raspberry Pi + ReSpeaker 2-Mic v2.0
- **Platform:** Raspberry Pi OS Trixie (Debian 13) · Python 3.13 · aarch64
- **Advanced Audio Processing:** Utilizes PipeWire with Acoustic Echo Cancellation (AEC) for voice capture
- **On-Device Wake Word Detection:** Efficient and private wake word recognition based on MicroWakeWord models
- **Gemini Live Integration:** Seamless conversational AI powered by Google's **Gemini Live API**

Optional features:
- **Custom Wake Word:** Training a custom MicroWakeWord model, provided Bulgarian **"Чочко"** as an example
- **Home Assistant:** Optional integration for smart device control
- **Spotify:** for music streaming from Spotify or Home Assistant Media Player

More technical details:
- **Linux Kernel:** 6.18.39+rpt-rpi-v8 · aarch64
- **Python version:** 3.13.5
- **pymicro-wakeword:** bundles its own TFLite C library — no ai-edge-litert/tflite-runtime needed

## Repository structure
Besides a specific instruction file in each folder, you can find the related resources in:
- **01-platform** - Makefile to compile and setup ReSpeaker drivers and ReSpeaker schematic diagram
- **02-tools** - Python scripts for headless WiFi captive portal
- **03-environment** - Template for definition of environment variables and music clip for test AEC
- **04-wakeword** - Install/test MicroWakeWord, obtain or train a wake word model (pretrained, Colab, or local)
- **05-voice_assist** - The voice assistant package in Python
- **06-enclosure** - 3D printing files (STL), exploded component view, and hardware wiring diagrams

## Implementation Roadmap

Follow these steps to build your voice assistant:

----
### 1. [Platform Setup](./01-platform/platform.md)
Hardware specifications, flashing Raspberry Pi OS (Trixie), and compiling ReSpeaker 2-mic v2.0 drivers.

### 2. [Python and Tools](./02-tools/tools.md)
Create a common Python environment, and install the system backup tool, headless Wi-Fi captive portal, and Raspotify integration.

### 3. [Environment & Audio Stack](./03-environment/environment.md)
Install, setup, and test PipeWire with AEC (Acoustic Echo Cancellation).

### 4. [Wake Word & Training](./04-wakeword/wakeword.md)
Install and test the microWakeWord library. Obtain a keyword model, or create one via a pretrained model, Colab notebook (English), or local training (any language supported by Google and/or Edge TTS).

### 5. [Voice Assistant Core](./05-voice_assist/voice_assist.md)
Install, setup and test the main Python package, Gemini API integration, and optional Home Assistant and Spotify integrations.

### 6. [Enclosure & Assembly](./06-enclosure/enclosure.md)
An enclosure for the voice assistant in the form of 3D printing files (STL), exploded component view, and a wiring diagram.

---
---
---
## 📜 License
This project is licensed under the MIT License - see the [LICENSE](https://opensource.org/license/mit) file for details.

---