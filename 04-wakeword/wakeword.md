# WakeWord: Install and Test microWakeWord. Obtain Wake Word Model.

## Install MicroWakeWord

### 1. System Dependencies
```bash
pip install -U pymicro-wakeword     # 2.3.0 or newer recommended
```

Version 2.3.0+ exposes `process_streaming_prob()`, which returns the raw
probability for logging/tuning. Versions 2.0–2.2 only expose
`process_streaming()` (returns a bool decision). The detector below works with
either; 2.3.0 just adds the live score logging.

`pymicro-wakeword` bundles its own `tensorflowlite_c` shared library and drives
it via ctypes, so **`ai_edge_litert`/`tflite_runtime` are not needed**.

### 2. Run Detection Script
Test the installed library with one of the builtin wakewords: alexa, hey_jarvis, hey_mycroft, or ok_nabu. To test with wake word Alexa, run the following command and say "Alexa":
```bash
arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - | python3 gemini-live-voice-assistant/04-wakeword/microWW/test_mww.py --builtin alexa
```

To test with your own trained model instead, point `--config` at its JSON manifest:
```bash
arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - | python3 gemini-live-voice-assistant/04-wakeword/microWW/test_mww.py --config gemini-live-voice-assistant/04-wakeword/microWW/chochko.json
```

`test_mww.py` reads post-AEC audio (PipeWire's default source). To compare
against the raw pre-AEC signal instead — useful for judging how much AEC is
actually helping — use the companion `test_mww_preaec.sh` script in the same
directory (see its header comment for usage; it taps the raw hardware
capture node directly via `pw-record`).

## Obtain MicroWakeWord Model
There are three options: use a pre-trained model, train your own in English via Colab, or train locally on your own PC (needed for non-English wake words like Bulgarian — the Colab-notebook route for that hit memory problems and was dropped in favor of local training).

### 1. Use a pre-trained model
Besides the built-in wake words, a collection of community pre-trained models is available in the following [repository](https://github.com/TaterTotterson/microWakeWords). The official ESPHome models live in the [micro-wake-word-models repo](https://github.com/esphome/micro-wake-word-models/tree/main/models/v2).

### 2. Train a custom wake word in English
The official training notebook is available on [GitHub](https://github.com/OHF-Voice/micro-wake-word/blob/november-update/notebooks/basic_training_notebook.ipynb).

> Training is **very** slow on CPU — set the Colab runtime to a **GPU** (Runtime → Change runtime type). Note that the install cell asks you to **restart the session** before continuing.

The notebook produces a quantized streaming model at
`trained_models/wakeword/tflite_stream_state_internal_quant/stream_state_internal_quant.tflite`.
To use it in ESPHome you must also write a small JSON model manifest — see the [ESPHome documentation](https://esphome.io/components/micro_wake_word) and the [model repo examples](https://github.com/esphome/micro-wake-word-models/tree/main/models/v2).

### 3. Train locally on your PC (WSL2 / Linux, CPU)

Google Colab's free tier now runs **Python 3.12** with only ~12 GB RAM, which causes
two problems for this notebook: a cascade of version-drift errors (the notebook
targets Python 3.10) and an out-of-memory kill partway through training. Training
**locally** sidesteps both — any PC with **≥16 GB RAM** finishes comfortably. No GPU
is required: the model is tiny, so CPU-only training takes on the order of an hour.

Ready-to-run scripts live in **04-wakeword/local/**. They reproduce the notebook's
approach with the Colab-only bits removed, but sample generation has since moved
off Piper entirely onto Google Cloud TTS (+ Edge TTS), with dedicated hard-negative
generation added on top — see below.

**Prerequisites (Windows → WSL2):**
- Enable CPU virtualization (Intel VT-x) in BIOS/UEFI.
- In elevated PowerShell: `wsl.exe --install --no-distribution`, then reboot.
- Install Ubuntu 22.04 (ships Python 3.10): `wsl --install -d Ubuntu-22.04`.

> On native Linux, skip the WSL steps. On native **Windows** (no WSL) it is harder —
> `pymicro-features` needs MSVC C++ Build Tools and TensorFlow is CPU-only — so
> WSL2 or Linux is strongly recommended.

**Environment setup (inside Ubuntu):** there's no single scripted installer for
this anymore (it evolved past the original `setup.sh`, now archived under
`local/Archive/`) — assembled here from what the current scripts actually need:
```bash
sudo apt update
sudo apt install -y python3.10-venv python3.10-dev build-essential \
    git wget unzip sox espeak-ng tmux
python3 -m venv ~/mww && source ~/mww/bin/activate

pip install --upgrade pip wheel
git clone -b november-update https://github.com/kahrendt/microWakeWord
# TF >= 2.16 / Keras 3 patch: model.evaluate() returns NumPy arrays already,
# so drop the redundant .numpy() calls train.py still has:
sed -i -E 's/((result|ambient_predictions)\["[a-z_]+"\])\.numpy\(\)/\1/g' \
  microWakeWord/microwakeword/train.py
pip install -e ./microWakeWord
pip install 'datasets<4.0' pymicro-features==1.0.0 tensorboard \
  google-cloud-texttospeech edge-tts
```
Copy the scripts onto the Linux filesystem (do NOT run from `/mnt/c` / OneDrive —
slow under WSL2, and OneDrive would try to sync intermediate training data):
```bash
cp -r /mnt/c/path/to/gemini-live-voice-assistant/04-wakeword/local ~/mww-local
cd ~/mww-local
sed -i 's/\r$//' *.sh *.py    # strip Windows CRLF line endings
```
Everything below runs from `~/mww-local` — scripts and generated data are
colocated there (no separate working directory).

**Google Cloud TTS credentials**: Application Default Credentials or a
service-account key via `GOOGLE_APPLICATION_CREDENTIALS`. **Do not** put a
service-account JSON key inside the repo folder — it's both git-tracked and
OneDrive-synced. Keep it outside the repo (e.g. `~/.config/gcloud/`) and point
`GOOGLE_APPLICATION_CREDENTIALS` at that external path.
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/outside/the/repo/service-account.json"
```

**The pipeline** is organized into four stages. Run the first three in order
the first time; after that, only **Extend negative sample(s)** needs
repeating when you want to reinforce one more word.

#### Create baseline wakeword

Generates the positive wake-word clips and background/negative audio, then
trains a model with **no exposure to the curated hard-negative words yet**.
This baseline is what candidate negative words get scored against in the
next stage — a model that hasn't been taught to avoid a word shows you which
ones it confuses "naturally", instead of guessing from phonetic intuition.

1. `python create_samples.py <N>` — positive wake-word clips. Generates
   across 5 Google Cloud Chirp3-HD voices + 2 Edge TTS voices (7 total), each
   with randomized rate/pitch via SSML, then pitch-shifts every raw clip
   through 7 semitone offsets (`-4` to `+4`) via `sox` for further voice-timbre
   variety. Writes to `generated_samples/raw/` and `generated_samples/augmented/`.
   `python create_samples.py 1` plays back one test sample per voice instead
   of bulk-generating.
2. **(Recommended) Merge in real device recordings.** Synthetic TTS voices
   only get you so close to how the wake word actually sounds in your room,
   on your mic, in your voice. `04-wakeword/microWW/record_clips.py` records
   and auto-segments real utterances on the device:
   ```bash
   arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - \
     | python record_clips.py --stdin --out real_clips
   python record_clips.py --review real_clips   # play/keep/delete each clip
   ```
   Copy the reviewed clips into the positive pool — `build_features.py`
   scans every `*.wav` in `generated_samples/augmented/`, so no code change
   is needed:
   ```bash
   cp real_clips/*.wav generated_samples/augmented/
   ```
   A few dozen real clips mixed into thousands of synthetic ones won't
   dominate training, but they give the model at least some exposure to a
   real voice/room/mic instead of purely clean TTS.
3. `python load_noise_stuff.py` — downloads background/negative audio: MIT
   RIRs, AudioSet, FMA, and microWakeWord's own negative-speech datasets.
   Skips whatever's already populated, so safe to re-run.
4. In `training_parameters.yaml`, set the `generated_negative_features`
   entry's `sampling_weight` to `0.0` (leave everything else as-is) — this
   keeps the curated hard negatives out of training for this baseline run,
   even before any have been generated.
5. `python build_features.py` — turns the above into spectrogram features
   (`generated_augmented_features/`, `generated_negative_features/`).
6. `bash train_microWW.sh` — trains the baseline model (see the notes under
   **Train wakeword** below for why you always run this script rather than
   hand-typing the training command).

#### Add negative samples

Generates candidate hard-negative clips, then keeps only the ones the
baseline model actually confuses with the wake word. Training against a word
the model was never going to mistake wastes the hard-negative sampling
budget and measurably does nothing.

1. `python create_negative_samples.py <N>` — hard-negative clips: curated
   Bulgarian phonetic near-misses to the wake word (e.g. "Точко", "Чочо"),
   common command words, and short syllables, same multi-voice + pitch-shift
   approach as positives. Writes to `generated_negatives/raw/` and
   `generated_negatives/augmented/`.
2. Scoring needs `pymicro-wakeword`, which is **permanently incompatible**
   with this training venv — it requires `pymicro-features>=2`, while
   microWakeWord's training code needs the old `1.0.0` API (`ProcessSamples`
   was renamed `process_samples` in 2.x). Installing it here silently
   upgrades `pymicro-features` and breaks `build_features.py` with
   `AttributeError: 'MicroFrontend' object has no attribute 'ProcessSamples'`.
   Use a separate venv instead, created once:
   ```bash
   python3 -m venv ~/mww-score
   source ~/mww-score/bin/activate
   pip install pymicro-wakeword google-cloud-texttospeech edge-tts
   deactivate
   ```
3. Hand-write a small JSON manifest pointing at the baseline `.tflite` from
   the previous stage — same shape as `04-wakeword/microWW/chochko.json`
   (only `model` needs to name your baseline `.tflite`; the exact
   `probability_cutoff` doesn't matter here since scoring reads the raw
   probability, not a pass/fail decision).
4. From `~/mww-local`, switch to the scoring venv to run the scorer, then
   switch back for everything else:
   ```bash
   source ~/mww-score/bin/activate
   python score_negative_clips.py --config baseline.json --dir generated_negatives/raw \
       --csv scores.csv --move-rejected generated_negatives/rejected_raw
   deactivate && source ~/mww/bin/activate
   ```
   This scores every raw clip against the baseline and moves (never
   deletes) the low scorers out of `raw/`.
5. `python create_negative_samples.py --pitch-only` — re-derives
   `augmented/` from whatever survived in `raw/`, without calling any TTS
   API again. (Back in `~/mww`, like all the non-scoring steps.)

`score_negative_words.py` is a companion script for the same job when you
don't have existing clips to score yet — it generates a couple of small
labeled probe clips per candidate word instead of scoring an existing pool.
Prefer `score_negative_clips.py` whenever a generated pool already exists.

#### Train wakeword

Restore the `generated_negative_features` entry's `sampling_weight` in
`training_parameters.yaml` to its real value (e.g. `5.0`), then rebuild and
train for real — now with only the pruned, genuinely-confusable hard
negatives included.

1. `python build_features.py` — **re-run this whenever the sample
   directories changed.** `train_microWW.sh` does not call it for you
   (deliberately, so you can retrain without regenerating features).
2. `bash train_microWW.sh` — trains directly from `training_parameters.yaml`
   + the feature dirs, using the tested `mixednet` architecture
   (`--mixconv_kernel_sizes` uses single-kernel blocks per block — mixed
   multi-kernel blocks were found to cause a large accuracy gap between the
   non-streaming trained model and the streaming-quantized tflite actually
   deployed, likely due to the extra channel-split/trim/concat machinery
   mixed kernels require). Wipes `trained_models/` and starts fresh every run.
   **Run this script itself rather than hand-typing the
   `microwakeword.model_train_eval` command** — doing so once with a
   different architecture (`inception`) and without the four `--test_*_0`
   disable flags the script sets got OOM-killed, since microwakeword's
   default is to run non-streaming TF eval, non-streaming tflite export,
   *and* non-streaming quantized tflite export in addition to whatever
   streaming test you asked for — that stacks up fast under WSL2's memory
   ceiling.

#### Extend negative sample(s)

Ongoing maintenance once the model is otherwise working: add one more word
you're already confident is a hard negative, without repeating the scoring
stage.

1. Add the word to `NEGATIVE_WORDS` in `create_negative_samples.py`.
2. `python create_negative_samples.py <N> "new word"` — generates exactly
   `N` new clips per voice, restricted to that one word. Each voice picks up
   from its own actual last index (scanned from `raw/`, not a count you have
   to work out yourself), so this stays correct even after pruning left
   uneven, gappy survivor counts per voice — no manual index math needed.
   Pitch-shifts the new clips into `augmented/` in the same run.
3. `python build_features.py` → `bash train_microWW.sh`, same as **Train
   wakeword** above.

If you're not sure a candidate word is actually confusable, use (from the
separate `~/mww-score` venv — see **Add negative samples** above)
`score_negative_words.py --config model.json --words "new word"` instead of
skipping straight to step 1 — it generates a couple of labeled probe clips
and scores them so you don't add dead weight to the negative set.

**Output**: the model lands at (inside wherever you ran `train_microWW.sh` from):
```
trained_models/wakeword/tflite_stream_state_internal_quant/stream_state_internal_quant.tflite
```
Copy it back to Windows:
```bash
cp trained_models/wakeword/tflite_stream_state_internal_quant/stream_state_internal_quant.tflite \
   /mnt/c/Users/<you>/Downloads/
```
As with the Colab path, to use it in ESPHome (or with `test_mww.py`) you still
need a JSON model manifest — see the [ESPHome documentation](https://esphome.io/components/micro_wake_word) and the
[model repo examples](https://github.com/esphome/micro-wake-word-models/tree/main/models/v2).

**Notes / knobs:**
- **Memory**: WSL2 defaults to capping itself at ~50% of host RAM. If you hit
  an OOM `Killed` even with `train_microWW.sh`'s tested `mixednet` config,
  raise the cap in `%UserProfile%\.wslconfig` (`[wsl2]` / `memory=24GB`, then
  `wsl --shutdown` and restart), or lower `batch_size` in
  `training_parameters.yaml` (128 → 64), or drop a negative set from its
  `features` list.
- **Speed**: expect roughly an hour-ish-plus for training on CPU; it prints a
  metrics line every 500 steps, so you can watch progress. Sample generation
  time now depends on Cloud/Edge TTS API latency/quota rather than local
  compute.
- **No resume**: `train_microWW.sh` wipes `trained_models/` at the start of
  every run — each run trains from scratch, it doesn't continue a previous
  checkpoint.
- **`config.yaml` vs `training_parameters.yaml`**: if you see a `config.yaml`
  sitting in the working dir, it's not used by anything — its schema
  (`target_phrase`, `positive_data_paths`, `epochs`, ...) doesn't match what
  `microwakeword.model_train_eval` actually reads. `training_parameters.yaml`
  is the real config, and it's edited by hand now (not regenerated by a
  script) — check it directly if a run behaves unexpectedly.
- **No `ambient_noise/` directory**: this is expected, not missing anything.
  `load_noise_stuff.py` produces `mit_rirs/`, `audioset_16k/`, `fma_16k/`
  (plus a raw `fma/` intermediate), and `negative_datasets/` — that's the
  complete set.

---
[Return to Main README](../README.md)
