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

The assistant is designed to be run on a Raspberry Pi Zero 2W with a Seeed Studio ReSpeaker 2-mic HAT.

Instructions are provided below in the following order:
- **Obtaining a wake word model** - get already trained model or create your own
- **Prepare the system** - install required packages and apply patches
- **Install and run the assistant** - install the python code and run the assistant
- **Create 3D-printed enclosure** - 3D printed models and interconnections

## Repository Structure
- **`training/`**: Contains a colab notebook and a patch for training OpenWakeWord model in non-English languages
- **`wifi_config/`**: Contains a script for a captive portal to configure the WiFi connection
- **`voice_assist/`**: Contains the main Python scripts for running the Voice Assistant
- **`patches/`**: System patches

---

## 🛠️ Obtaining a wake word model
There are two options: use a pre-trained model or use your own.

### 1. Use a pre-trained model
You can find a large collection of community-trained models (mostly in English) in the following repository:
https://github.com/fwartner/home-assistant-wakewords-collection

### 2. Train a custom wake word model
To train a custom wake word model in English language, you can use the following Google Colab notebook:
https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

To train a custom wake word model in other languages supported by Piper, you can use the same notebook with a simple patch that replace the English voice with another one. In the **training/** you will find two python scripts for generating the samples:
- **generate_samples_pt.py** - the original script included in the piper-sample-generator package, working with PyTorch models
- **generate_samples_onnx.py** - the modified script working with ONNX models

Once you find a piper voice model for your language, you can use the appropriated python script as follows:
- make a local copy of this script on your computer
- replace the model name in the script with the name of your desired model
- store the script in some url accessible from Google colab environment (e.g. github gist)
- run the notebook stored in the same directory

### 3. Train a custom wake word model in Bulgarian

Based on the following Google Colab notebook:
https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

To train a custom wake word model in Bulgarian using the OpenWakeWord Colab notebook, you need to patch the sample generation script to use the Bulgarian voice (Dimitar).

### Instructions

1. Open the OpenWakeWord Colab Notebook.
2. Run the first cell to install dependencies (including `piper-sample-generator`).
3. **Apply the Patch**: Run the following command in a new cell to replace the default English generator with the Bulgarian one from this repository:

```python
# Download the patched script
!wget https://raw.githubusercontent.com/YourUsername/YourRepositoryName/main/training/generate_samples.py

# Move it to the piper_train library location (path may vary slightly based on Colab updates)
!mv generate_samples.py /usr/local/lib/python3.10/dist-packages/piper_train/

# Install ONNX Runtime (required for the Bulgarian model)
!pip install onnxruntime
```

4. Continue running the rest of the notebook cells (installing `openwakeword`, generating clips, and training). The script will automatically download the `bg_BG-dimitar-medium.onnx` voice model.

---

## 🎙️ Voice Assistant Setup

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