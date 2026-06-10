# Adding microWakeWord to the Voice Assistant

A guide for adding [microWakeWord](https://github.com/kahrendt/microWakeWord) as a
selectable wake-word backend alongside openWakeWord, switchable with a single flag.

## Target setup

- Raspberry Pi Zero 2W, ReSpeaker 2-Mic HAT
- 64-bit Raspberry Pi OS / Debian 13 (Trixie), headless, kernel 6.12.x
- Wake-word inference via the [`pymicro-wakeword`](https://pypi.org/project/pymicro-wakeword/) Python package
- Audio reaching the detector as **16 kHz, 16-bit mono** (`int16`) PCM

> **64-bit is required.** `pymicro-wakeword` ships only `manylinux_2_35` wheels
> (`aarch64` + `x86_64`) — there is no 32-bit `armv7l`/`armv6` wheel. The
> `manylinux_2_35` tag also needs **glibc ≥ 2.35**, which Trixie (glibc 2.41)
> satisfies. On 32-bit Pi OS or older Debian, the install will not resolve a wheel.

## Install

In the project's virtualenv:

```bash
pip install -U pymicro-wakeword     # 2.3.0 or newer recommended
```

Version 2.3.0+ exposes `process_streaming_prob()`, which returns the raw
probability for logging/tuning. Versions 2.0–2.2 only expose
`process_streaming()` (returns a bool decision). The detector below works with
either; 2.3.0 just adds the live score logging.

`pymicro-wakeword` bundles its own `tensorflowlite_c` shared library and drives
it via ctypes, so **`ai_edge_litert`/`tflite_runtime` are not needed** for this path.

## Config flag

Add a boolean switch in `config.py` so the backend can be flipped without code
changes:

```python
# ── Wake Word ──────────────────────────────────────────────
USE_MICROWAKEWORD = True   # True = microWakeWord, False = openWakeWord

WAKEWORD_MODEL_OWW = '/home/chochko/voiceAssist/models/chochko.tflite'
WAKEWORD_MODEL_MWW = '/home/chochko/voiceAssist/models/chochko_micro.tflite'
WAKEWORD_THRESH    = 0.5

# Resolved automatically — don't change these
WAKEWORD_BACKEND = 'microwakeword' if USE_MICROWAKEWORD else 'openwakeword'
WAKEWORD_MODEL   = WAKEWORD_MODEL_MWW if USE_MICROWAKEWORD else WAKEWORD_MODEL_OWW
```

## The microWakeWord detector

Drop this class into `wakeword.py` next to the existing `OpenWakeWordDetector`.
Both share a `WakeWordDetector` base that defines `process()`, `reset()`,
`set_loop()`, `set_on_detect()`, and `_fire()`.

```python
class MicroWakeWordDetector(WakeWordDetector):
    """microWakeWord backend via pymicro_wakeword.

    pymicro_wakeword handles the parts that are easy to get wrong:
      * int8 input/output quantization (reads scale/zero_point from the model)
      * the streaming input shape [1, stride, 40] and internal model state
      * 10 ms (160-sample) feature framing
      * sliding-window probability averaging vs. the model's probability_cutoff
    So we just feed it 16 kHz / 16-bit mono audio and read a probability back.
    """

    def __init__(self, model_path: str, threshold: float = 0.5):
        super().__init__(model_path, threshold)
        from pathlib import Path
        from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures

        # from_config() expects the JSON manifest, not the .tflite.
        p = Path(model_path)
        config_path = p if p.suffix == '.json' else p.with_suffix('.json')
        if not config_path.exists():
            raise FileNotFoundError(
                f'microWakeWord JSON manifest not found: {config_path}. '
                f'Point WAKEWORD_MODEL_MWW at the .json manifest (and make sure '
                f'its "model" field names the .tflite sitting next to it).'
            )

        self._mww  = MicroWakeWord.from_config(config_path)
        self._feat = MicroWakeWordFeatures()
        # The model author calibrates this; honour it over the generic threshold.
        self._cutoff = self._mww.probability_cutoff

        # API drift across pymicro_wakeword versions:
        #   >= 2.3.0 : process_streaming_prob(feat) -> Optional[float]  (gives score)
        #   2.0-2.2  : process_streaming(feat)      -> bool             (decision only)
        self._has_prob = hasattr(self._mww, 'process_streaming_prob')

        log.info(
            f'microWakeWord ready: "{self._mww.wake_word}" '
            f'cutoff={self._cutoff} window={self._mww.sliding_window_size} '
            f'stride={getattr(self._mww, "stride", "?")} '
            f'score_api={self._has_prob}'
        )

    def process(self, pcm_16k_i16: np.ndarray):
        if self._detected or time.time() < self._ready_at:
            return

        audio_bytes = pcm_16k_i16.astype('int16').tobytes()

        for feat in self._feat.process_streaming(audio_bytes):
            if self._has_prob:
                prob = self._mww.process_streaming_prob(feat)
                if prob is None:
                    continue
                if prob > 0.3:
                    log.info(f'microWakeWord score: {prob:.3f}')
                detected = prob > self._cutoff
            else:
                # Older API: returns the decision directly (cutoff applied inside).
                detected = bool(self._mww.process_streaming(feat))

            if detected:
                log.info('microWakeWord detected!')
                self._fire()
                return

    def _reset_model(self):
        # Reload the model to clear streaming state, and reset the feature buffer.
        from pymicro_wakeword import MicroWakeWordFeatures
        self._mww.reset()
        self._feat = MicroWakeWordFeatures()
```

Wire it into the factory so `config.WAKEWORD_BACKEND` selects the implementation:

```python
def create_detector(backend: str, model_path: str,
                    threshold: float = 0.5) -> WakeWordDetector:
    if backend == 'microwakeword':
        return MicroWakeWordDetector(model_path, threshold)
    elif backend == 'openwakeword':
        return OpenWakeWordDetector(model_path, threshold)
    else:
        raise ValueError(f'Unknown backend: {backend}')
```

## How the model actually works (and what NOT to do)

microWakeWord `.tflite` models are **streaming, int8-quantized** networks. This
trips up hand-rolled inference in three ways:

1. **Quantization.** The input tensor is `int8`, not `float32`. Feeding floats
   raises `Cannot set tensor: Got value of type FLOAT32 but expected type INT8`.
   The values must be quantized with the model's own `scale`/`zero_point`.
2. **Input shape.** Input is `[1, stride, 40]` with `stride = 3` (read from the
   model). It is **not** `[1, 128, 40, 1]` — that is a different, non-streaming
   architecture.
3. **Internal state.** The model keeps a ring buffer across invocations; you
   feed 3 feature frames per step and detection is the **sliding-window mean** of
   the last `sliding_window_size` probabilities vs. `probability_cutoff`.

`pymicro_wakeword`'s high-level `MicroWakeWord` class does all three correctly,
which is why the detector above delegates to it instead of calling the TFLite
interpreter directly. `MicroWakeWordFeatures.process_streaming(audio_bytes)`
rebuffers arbitrary chunk sizes into 10 ms (160-sample) frames internally, so
feeding it 1280-sample chunks is fine.

## The model files

`from_config()` loads the JSON **manifest**, then loads the `.tflite` named in the
manifest's `"model"` field, relative to the JSON's folder:

```json
{
  "type": "micro",
  "wake_word": "Alexa",
  "model": "chochko_micro.tflite",
  "trained_languages": ["en"],
  "version": 2,
  "micro": {
    "probability_cutoff": 0.9,
    "sliding_window_size": 5,
    "feature_step_size": 10
  }
}
```

- Keep the `.json` and `.tflite` **side by side**.
- If you rename the `.tflite`, update the manifest's `"model"` field to match.
- `"wake_word"` is only a display label — **renaming a model does not change what
  it detects.** The stock `alexa` model still triggers on *"Alexa"* regardless of
  the filename or label. Use it to validate the pipeline end-to-end, then swap in
  a model trained on your actual phrase.

## Tuning

`probability_cutoff` in the manifest is the knob:

- Missing real utterances → lower it (e.g. toward 0.7).
- False triggers on background speech → raise it (e.g. toward 0.95).

On 2.3.0+ the `microWakeWord score: 0.xxx` log lines show how high the
probability climbs on a genuine utterance vs. noise, which makes setting the
cutoff a measurement rather than a guess.

## Smoke test

1. Set `USE_MICROWAKEWORD = True`, point `WAKEWORD_MODEL_MWW` at the model.
2. Restart. The startup log should show `microWakeWord ready: "..."` and
   `score_api=True` (on 2.3.0+).
3. With the stock `alexa` model, say **"Alexa"** → expect `microWakeWord detected!`.
4. Switch back any time by setting `USE_MICROWAKEWORD = False`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `expected type INT8 ... got FLOAT32` | Feeding float features to a quantized model | Use the high-level `MicroWakeWord` class (handles quantization) |
| `'MicroWakeWord' object has no attribute 'process_streaming_prob'` | `pymicro-wakeword` 2.0–2.2 | Upgrade to 2.3.0, or rely on the `_has_prob` fallback above |
| `JSON manifest not found` | `WAKEWORD_MODEL_MWW` points at a `.tflite` with no sibling `.json` | Place the `.json` next to the `.tflite` (or point the flag at the `.json`) |
| Model loads but never fires | Saying the wrong phrase, or cutoff too high | Say the phrase the model was trained on; lower `probability_cutoff` |
| No wheel found on install | 32-bit OS or glibc < 2.35 | Use 64-bit OS with glibc ≥ 2.35 (e.g. Debian 12/13) |