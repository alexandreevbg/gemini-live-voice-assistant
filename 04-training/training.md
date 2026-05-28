# Training: Obtaining a custom wake word model

A large collection of community-trained models (mostly in English) is available in the following repository:
https://github.com/fwartner/home-assistant-wakewords-collection

If you prefer to train your own model, then follow the instructions below.

## 1. Train a custom wake word in English
To train a custom wake word model in English, use the following Google Colab notebook: https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing

## 2. Train a custom wake word in other languages
To train a custom wake word model in other languages supported by Piper, use the same notebook with a minor modification and a patch that replaces the English voice with another one. In the **04-training/** directory you will find the modified notebook, as well as three Python scripts for generating the samples:
- **generate_samples_pt.py** - the original script included in the piper-sample-generator package, working with PyTorch models
- **generate_samples_onnx.py** - the modified script working with ONNX models
- **generate_samples.py** - the final script to be downloaded by the modified notebook

Once you find a piper voice model for your language, use the appropriate Python script as follows:
- make a local copy of the appropriate script on your computer
- rename it to "generate_samples.py"
- replace the model name in the script with the name of your desired model
- store the script at a URL accessible from the Google Colab environment (e.g. Github Gist)
- run the notebook stored in the same directory

The current notebook and generate_samples.py in the **02-training** directory are prepared for Bulgarian (bg-BG) language. To use it with another language, run the same notebook and then:
- click on [Show code](#2-train-a-custom-wake-word-model) at the end of the first cell
- find the line starting with "!wget "https://raw.githubusercontent.com/..."
- replace the link on this line with the link to your URL containing your generate_samples.py script
- run the cell to create and listen to a test example
- run all cells and download the generated tflite model
- save a copy of the modified notebook and rename it as you want

To run the Bulgarian training notebook directly in Google Colab: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/alexandreevbg/gemini-live-voice-assistant/blob/main/training/OpenWakeWord_model_BG.ipynb)

In addition to the `target_word` field, the notebook includes a `target_model_name` field to prevent the automatic conversion of the target word into the model filename.
