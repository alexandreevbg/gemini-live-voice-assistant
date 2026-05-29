# WakeWord: Obtain Wake Word Model, Install openWakeWord

## Obtain Wake Word Model
There are three options: use a pre-trained model, train your own in English or in non-English language.

### 1. Use a pre-trained model
A large collection of community-trained models (mostly in English) is available in the following [repository](https://github.com/fwartner/home-assistant-wakewords-collection/blob/main/en).

### 2. Train a custom wake word in English
To train a custom wake word model in English, use the following Google Colab [notebook](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing).

### 3. Train a custom wake word in other languages
To train a custom wake word model in other languages supported by Piper, use the same notebook with a minor modification and a patch that replaces the English voice with another one. In the **04-wakeword/** directory you will find the modified notebook, as well as three Python scripts for generating the samples:
- **generate_samples_pt.py** - the original script included in the piper-sample-generator package, working with PyTorch models
- **generate_samples_onnx.py** - the modified script working with ONNX models
- **generate_samples.py** - the final script to be downloaded by the modified notebook

Once you find a piper voice model for your language, use the appropriate Python script as follows:
- make a local copy of the appropriate script on your computer
- rename it to "generate_samples.py"
- replace the model name in the script with the name of your desired model
- store the script at a URL accessible from the Google Colab environment (e.g. Github Gist)
- run the notebook stored in the same directory

The current notebook and generate_samples.py in the **02-wakeword** directory are prepared for Bulgarian (bg-BG) language. To use it with another language, run the same notebook and then:
- click on [Show code](#2-train-a-custom-wake-word-model) at the end of the first cell
- find the line starting with "!wget "https://raw.githubusercontent.com/..."
- replace the link on this line with the link to your URL containing your generate_samples.py script
- run the cell to create and listen to a test example
- run all cells and download the generated tflite model
- save a copy of the modified notebook and rename it as you want

To run the Bulgarian training notebook directly in Google Colab: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alexandreevbg/gemini-live-voice-assistant/blob/main/training/OpenWakeWord_model_BG.ipynb)

In addition to the `target_word` field, the notebook includes a `target_model_name` field to prevent the automatic conversion of the target word in non-English into the model filename.

## Install openWakeWord

### 1. System Dependencies
Install required system libraries before any Python packages:

```bash
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-dev libasound2-dev \
    libspeexdsp-dev swig build-essential alsa-utils
```

> `portaudio19-dev` is required to build PyAudio from source.  
> `libspeexdsp-dev` is required to build speexdsp-ns from source.

### 2. Install PyAudio
```bash
pip install pyaudio
```

### 3. Install speexdsp-ns (from source)
Prebuilt wheels remain unavailable for Python 3.13 + aarch64 on PyPI. Building from source is required.
```bash
wget https://github.com/TeaPoly/speexdsp-ns-python/archive/refs/heads/main.zip -O speexdsp-ns-python-main.zip
cd ~
unzip speexdsp-ns-python-main.zip
cd speexdsp-ns-python-main
pip install .
```

### 4. Install ai-edge-litert
While `tflite-runtime` is deprecated for newer Python versions. `ai-edge-litert` is now the stable and official Google's successor for Python 3.13:
```bash
pip install ai-edge-litert
```
> You may see unrelated warnings about `types-seaborn` dependencies — these are harmless and can be ignored.

### 5. Install openwakeword (from source)
First, you can check if a newer version of `openwakeword` has been released on PyPI:
```bash
pip index versions openwakeword
```
Download the source
```bash
cd ~
wget https://github.com/dscripka/openWakeWord/archive/refs/tags/v0.6.0.zip -O openWakeWord-0.6.0.zip
unzip openWakeWord-0.6.0.zip
cd openWakeWord-0.6.0
```
Open `setup.py`
```bash
nano setup.py
```
```python
# Replace:
'tflite-runtime>=2.8.0,<3; platform_system == "Linux"',
# with:
'ai-edge-litert; platform_system == "Linux"',
```

Then install
```bash
pip install .
```

### 6. Patch openwakeword Source Files
The `ai-edge-litert` API differs slightly from `tflite-runtime`. The import used is:

```python
from ai_edge_litert.interpreter import Interpreter as tflite
```

This makes `tflite` the `Interpreter` class itself — so calling `tflite.Interpreter(...)` means `Interpreter.Interpreter(...)`, which doesn't exist. Three calls need fixing:

### model.py (~line 165)
```bash
nano ~/.venv/lib/python3.13/site-packages/openwakeword/model.py
```
```python
# Change:
self.models[mdl_name] = tflite.Interpreter(model_path=mdl_path, num_threads=1)
# To:
self.models[mdl_name] = tflite(model_path=mdl_path, num_threads=1)
```

### utils.py (~lines 113 and 139)
```bash
nano ~/.venv/lib/python3.13/site-packages/openwakeword/utils.py
```
```python
# Change (~line 113):
self.melspec_model = tflite.Interpreter(model_path=melspec_model_path, num_threads=ncpu)
# To:
self.melspec_model = tflite(model_path=melspec_model_path, num_threads=ncpu)

# Change (~line 139):
self.embedding_model = tflite.Interpreter(model_path=embedding_model_path, num_threads=ncpu)
# To:
self.embedding_model = tflite(model_path=embedding_model_path, num_threads=ncpu)
```

### 7. Download Pretrained Models

```bash
cd ~
python -c "from openwakeword.utils import download_models; download_models()"
```

Models are saved to:
```
~/.venv/lib/python3.13/site-packages/openwakeword/resources/models/
```

Required base models:
- `melspectrogram.tflite` — audio feature extraction
- `embedding_model.tflite` — audio embedding
- Your custom model, e.g. `chochko.tflite`

---

### 8. Fix Audio Buffer Overflow

On resource-constrained hardware, PyAudio may throw `OSError: [Errno -9981] Input overflowed`. To prevent this:
```bash
nano ~/openWakeWord-0.6.0/examples/detect_from_microphone.py
```
```python
# Change(~line 74):
audio = np.frombuffer(mic_stream.read(CHUNK), dtype=np.int16)

# To:
audio = np.frombuffer(mic_stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
```

Optionally increase the buffer size:
```python
CHUNK = 4096
mic_stream = p.open(..., frames_per_buffer=CHUNK * 4)
```

### 9. Run Detection Script
```bash
python openWakeWord-0.6.0/examples/detect_from_microphone.py
    --model_path /home/pi/voiceAssist/models/chochko.tflite \
    --inference_framework tflite
```
For detection test use the standard wake words 'Hey Mycroft', 'Hey Jarvis', and 'Hey Rhasspy'. 

---
