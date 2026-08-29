#!/usr/bin/env python3
"""Phase 2: download augmentation + negative/background data for microWakeWord
(local, cwd-relative). Formerly prepare_data.py — renamed, logic unchanged.

Mirrors the Colab notebook's "download augmentation data" and "download negative
datasets" cells, but:
  * loads AudioSet via the `datasets` library (streamed, parquet-native) instead
    of the dead flat `.tar` URLs the original notebook used, and
  * fixes the FMA loop bug (it looped over audioset_dataset instead of
    fma_dataset) and makes FMA best-effort.

Run from your working dir (run_all.sh cd's there for you):
    python load_noise_stuff.py
"""
import glob
import os
from pathlib import Path

import numpy as np
import scipy.io.wavfile
import datasets
from tqdm import tqdm

# How many background clips to pull from AudioSet (balanced train has ~22k).
NUM_AUDIOSET_CLIPS = int(os.environ.get("NUM_AUDIOSET_CLIPS", "1500"))


def download_mit_rirs():
    out = "./mit_rirs"
    if os.path.exists(out) and len(glob.glob(f"{out}/*.wav")) > 0:
        print(f"[mit_rirs] already populated ({len(glob.glob(f'{out}/*.wav'))} wavs) - skipping")
        return
    os.makedirs(out, exist_ok=True)
    print("[mit_rirs] downloading impulse responses...")
    ds = datasets.load_dataset(
        "davidscripka/MIT_environmental_impulse_responses", split="train", streaming=True
    )
    for row in tqdm(ds):
        name = row["audio"]["path"].split("/")[-1]
        scipy.io.wavfile.write(
            os.path.join(out, name), 16000, (row["audio"]["array"] * 32767).astype(np.int16)
        )


def download_audioset():
    out = "./audioset_16k"
    if os.path.exists(out) and len(glob.glob(f"{out}/*.wav")) > 0:
        print(f"[audioset_16k] already populated ({len(glob.glob(f'{out}/*.wav'))} wavs) - skipping")
        return
    os.makedirs(out, exist_ok=True)
    print(f"[audioset_16k] streaming up to {NUM_AUDIOSET_CLIPS} clips from agkphysics/AudioSet...")
    try:
        ds = datasets.load_dataset("agkphysics/AudioSet", "balanced", split="train", streaming=True)
    except Exception:
        ds = datasets.load_dataset(
            "agkphysics/AudioSet", "balanced", split="train", streaming=True, trust_remote_code=True
        )
    ds = ds.cast_column("audio", datasets.Audio(sampling_rate=16000))
    for i, row in enumerate(tqdm(ds, total=NUM_AUDIOSET_CLIPS)):
        if i >= NUM_AUDIOSET_CLIPS:
            break
        arr = np.asarray(row["audio"]["array"])
        scipy.io.wavfile.write(
            os.path.join(out, f"audioset_{i:06d}.wav"), 16000, (arr * 32767).astype(np.int16)
        )


def download_fma():
    """Secondary background source (music). Best-effort; AudioSet is primary."""
    out = "./fma_16k"
    os.makedirs(out, exist_ok=True)
    if len(glob.glob(f"{out}/*.wav")) > 0:
        print(f"[fma_16k] already populated ({len(glob.glob(f'{out}/*.wav'))} wavs) - skipping")
        return
    try:
        if not os.path.exists("./fma"):
            os.mkdir("./fma")
            link = "https://huggingface.co/datasets/mchl914/fma_xsmall/resolve/main/fma_xs.zip"
            os.system(f'wget -O fma/fma_xs.zip "{link}"')
            os.system("cd fma && unzip -q fma_xs.zip")
        fma_files = [str(p) for p in Path("fma").glob("**/*.mp3")]
        if not fma_files:
            print("[fma_16k] no mp3 files found after extraction; skipping (AudioSet is primary).")
            return
        fds = datasets.Dataset.from_dict({"audio": fma_files})
        fds = fds.cast_column("audio", datasets.Audio(sampling_rate=16000))
        for i, row in enumerate(tqdm(fds)):
            arr = np.asarray(row["audio"]["array"])
            scipy.io.wavfile.write(
                os.path.join(out, f"fma_{i:06d}.wav"), 16000, (arr * 32767).astype(np.int16)
            )
    except Exception as e:  # noqa: BLE001
        print(f"[fma_16k] failed ({e!r}); skipping. AudioSet is the primary source.")


def download_negative_datasets():
    """Pre-generated spectrogram features for negative sets (microWakeWord's HF repo)."""
    out = "./negative_datasets"
    filenames = ["dinner_party.zip", "dinner_party_eval.zip", "no_speech.zip", "speech.zip"]
    os.makedirs(out, exist_ok=True)
    root = "https://huggingface.co/datasets/kahrendt/microwakeword/resolve/main/"
    for fname in filenames:
        target_dir = os.path.join(out, fname.replace(".zip", ""))
        if os.path.isdir(target_dir):
            print(f"[negatives] {target_dir} exists - skipping")
            continue
        zip_path = os.path.join(out, fname)
        print(f"[negatives] downloading {fname}...")
        os.system(f'wget -O "{zip_path}" "{root + fname}"')
        os.system(f'unzip -q "{zip_path}" -d "{out}"')


def main():
    download_mit_rirs()
    download_audioset()
    download_fma()
    download_negative_datasets()

    n_a = len(glob.glob("audioset_16k/*.wav"))
    n_f = len(glob.glob("fma_16k/*.wav"))
    n_r = len(glob.glob("mit_rirs/*.wav"))
    print(f"\n== summary == mit_rirs:{n_r}  audioset_16k:{n_a}  fma_16k:{n_f}")
    if n_a + n_f == 0:
        raise SystemExit("No background clips were written. Check the AudioSet download output above.")
    if n_r == 0:
        raise SystemExit("No impulse responses (mit_rirs). Check the MIT RIR download above.")
    print("Noise/background data ready.")


if __name__ == "__main__":
    main()
