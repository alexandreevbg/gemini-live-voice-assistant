#!/usr/bin/env python3
"""Standalone microWakeWord test — validates model + library BEFORE
integrating into the voice assistant.

No sounddevice and no dependency on the app's config.py / capture.py.
Audio is captured by `arecord` and piped in as raw 16 kHz / 16-bit / mono PCM.

Examples:
    arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - \
      | python3 mww_test.py --config /home/chochko/voice_assist/models/chochko_micro.json

    arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - \
      | python3 mww_test.py --builtin alexa

Requires only: pymicro-wakeword  (and arecord from alsa-utils, already present)
"""
import argparse
import sys

import numpy as np
from pymicro_wakeword import MicroWakeWord, MicroWakeWordFeatures, Model

RATE  = 16000   # microWakeWord requires 16 kHz mono 16-bit
BLOCK = 1280    # 80 ms; features rebuffer to 10 ms frames internally
BYTES = BLOCK * 2  # int16 = 2 bytes/sample


def main():
    ap = argparse.ArgumentParser(
        description='microWakeWord test (reads raw 16k mono PCM from stdin)')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--config', help='Path to the model JSON manifest')
    src.add_argument('--builtin', choices=[m.value for m in Model],
                     help='Use a bundled model instead of a file')
    args = ap.parse_args()

    if args.config:
        mww = MicroWakeWord.from_config(args.config)
    else:
        mww = MicroWakeWord.from_builtin(Model(args.builtin))
    feats = MicroWakeWordFeatures()

    # API drift: >=2.3.0 exposes process_streaming_prob (gives a score);
    # 2.0-2.2 only has process_streaming (bool decision).
    has_prob = hasattr(mww, 'process_streaming_prob')
    cutoff   = mww.probability_cutoff

    print(f'Model: "{mww.wake_word}"  cutoff={cutoff}  '
          f'window={mww.sliding_window_size}  score_api={has_prob}',
          file=sys.stderr)
    print('Listening on stdin — say the wake word.  Ctrl-C to stop.\n',
          file=sys.stderr)

    detections = 0
    try:
        while True:
            chunk = sys.stdin.buffer.read(BYTES)
            if not chunk:
                break  # EOF (arecord stopped)
            pcm = np.frombuffer(chunk, dtype=np.int16)

            for feat in feats.process_streaming(pcm.tobytes()):
                if has_prob:
                    p = mww.process_streaming_prob(feat)
                    if p is None:
                        continue
                    if p > 0.3:
                        bar = '#' * int(p * 40)
                        print(f'\r  score {p:0.3f} |{bar:<40}|',
                              end='', flush=True, file=sys.stderr)
                    hit = p > cutoff
                else:
                    hit = bool(mww.process_streaming(feat))

                if hit:
                    detections += 1
                    print(f'\n  *** DETECTED ***  (#{detections})',
                          file=sys.stderr)
                    mww.reset()
                    feats = MicroWakeWordFeatures()
    except KeyboardInterrupt:
        pass

    print(f'\nDone. {detections} detection(s).', file=sys.stderr)


if __name__ == '__main__':
    main()
