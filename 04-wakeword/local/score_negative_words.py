#!/usr/bin/env python3
"""Score each candidate hard-negative word against a trained microWakeWord model.

For hard-negative mining: generates one short, word-labeled TTS clip per
candidate word (a couple of voices each -- unlike create_negative_samples.py,
these filenames DO encode the word, since that's the whole point here), runs
each clip through the given model, and reports the peak streaming probability
per word. Words that never approach the model's decision boundary are safe to
drop from NEGATIVE_WORDS in create_negative_samples.py -- training against
them wastes the hard-negative sampling budget on non-problems. Words that DO
score high are the ones actually worth keeping / generating more of.

Best used against a model trained WITHOUT the curated hard-negative set (set
generated_negative_features's sampling_weight to 0.0 in
training_parameters.yaml before that baseline run) -- that isolates which
words the model confuses "naturally", before any deliberate anti-confusion
training skews the picture.

Requires pymicro-wakeword in addition to this pipeline's usual deps:
    pip install pymicro-wakeword

Usage:
    python score_negative_words.py --config /path/to/baseline_model.json
    python score_negative_words.py --config baseline.json --words чичо,чип,бочко
    python score_negative_words.py --config baseline.json --voices 3 --csv scores.csv
"""

import argparse
import asyncio
import csv
import os
import subprocess
import time
import wave

import numpy as np

from create_negative_samples import NEGATIVE_WORDS, GOOGLE_VOICES, EDGE_VOICES, check_auth_google

PROBE_DIR = "word_probe_clips"

_google_client_cache = {}


def _google_client():
    from google.cloud import texttospeech
    if "client" not in _google_client_cache:
        _google_client_cache["client"] = texttospeech.TextToSpeechClient()
    return _google_client_cache["client"]


def synth_google(word, voice_name, out_path):
    from google.cloud import texttospeech

    synthesis_input = texttospeech.SynthesisInput(text=word)
    voice_params = texttospeech.VoiceSelectionParams(language_code="bg-BG", name=voice_name)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000
    )
    response = _google_client().synthesize_speech(
        input=synthesis_input, voice=voice_params, audio_config=audio_config
    )
    with open(out_path, "wb") as f:
        f.write(response.audio_content)


async def synth_edge(word, voice_name, out_path_wav):
    import edge_tts

    tmp_mp3 = out_path_wav + ".mp3"
    communicate = edge_tts.Communicate(word, voice_name)
    await communicate.save(tmp_mp3)
    subprocess.run(
        ["sox", tmp_mp3, "-r", "16000", "-c", "1", "-b", "16", out_path_wav],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    if os.path.exists(tmp_mp3):
        os.remove(tmp_mp3)


def generate_probe_clips(words, n_voices):
    os.makedirs(PROBE_DIR, exist_ok=True)
    have_google = check_auth_google()

    voice_pool = []
    if have_google:
        voice_pool += [("g", name) for _, name in GOOGLE_VOICES]
    voice_pool += [("e", name) for _, name in EDGE_VOICES]
    if not have_google:
        print("[probe] Google credentials not found -- using Edge TTS voices only.")

    chosen_voices = voice_pool[:n_voices] if n_voices <= len(voice_pool) else voice_pool

    clips = {}
    for word in words:
        paths = []
        safe_word = word.replace(" ", "_")
        for engine, voice_name in chosen_voices:
            voice_short = voice_name.split("-")[-1]
            out_path = os.path.join(PROBE_DIR, f"{safe_word}__{voice_short}.wav")
            if not os.path.exists(out_path):
                if engine == "g":
                    synth_google(word, voice_name, out_path)
                else:
                    asyncio.run(synth_edge(word, voice_name, out_path))
                time.sleep(0.1)
            paths.append(out_path)
        clips[word] = paths
    return clips


def score_clip(mww, path):
    from pymicro_wakeword import MicroWakeWordFeatures

    mww.reset()
    feats = MicroWakeWordFeatures()
    has_prob = hasattr(mww, "process_streaming_prob")

    with wave.open(path, "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    peak = 0.0
    for feat in feats.process_streaming(pcm.tobytes()):
        if has_prob:
            p = mww.process_streaming_prob(feat)
            if p is not None:
                peak = max(peak, p)
        else:
            if mww.process_streaming(feat):
                peak = 1.0
    return peak


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", required=True, help="Path to the model JSON manifest to score against")
    ap.add_argument("--words", help="Comma-separated subset to test (default: full NEGATIVE_WORDS list)")
    ap.add_argument("--voices", type=int, default=2, help="TTS voices per word (default 2)")
    ap.add_argument(
        "--threshold", type=float, default=0.5,
        help="Peak score below which a word is flagged 'drop' (default 0.5)",
    )
    ap.add_argument("--csv", help="Optional path to write full results as CSV")
    args = ap.parse_args()

    words = [w.strip() for w in args.words.split(",")] if args.words else list(dict.fromkeys(NEGATIVE_WORDS))

    from pymicro_wakeword import MicroWakeWord

    mww = MicroWakeWord.from_config(args.config)
    print(f">> Model: cutoff={mww.probability_cutoff} window={mww.sliding_window_size}")

    print(f">> Generating probe clips for {len(words)} word(s), {args.voices} voice(s) each...")
    clips = generate_probe_clips(words, args.voices)

    print(">> Scoring...")
    results = []
    for word, paths in clips.items():
        scores = [score_clip(mww, p) for p in paths]
        results.append((word, max(scores), sum(scores) / len(scores), len(scores)))

    results.sort(key=lambda r: r[1], reverse=True)

    print(f"\n{'word':<20} {'max':>6} {'avg':>6}  verdict")
    print("-" * 50)
    for word, mx, avg, n in results:
        verdict = "KEEP" if mx >= args.threshold else "drop"
        print(f"{word:<20} {mx:>6.3f} {avg:>6.3f}  {verdict}")

    keep = [w for w, mx, _, _ in results if mx >= args.threshold]
    drop = [w for w, mx, _, _ in results if mx < args.threshold]
    print(f"\n>> {len(keep)} to KEEP, {len(drop)} to drop (threshold {args.threshold}).")
    print(">> KEEP list:", ", ".join(f'"{w}"' for w in keep))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["word", "max_score", "avg_score", "n_clips", "verdict"])
            for word, mx, avg, n in results:
                writer.writerow([word, f"{mx:.4f}", f"{avg:.4f}", n, "KEEP" if mx >= args.threshold else "drop"])
        print(f">> Wrote {args.csv}")


if __name__ == "__main__":
    main()
