#!/usr/bin/env python3
"""Augment wake-word clips and negative clips with matching split structures."""

import os
import shutil
from mmap_ninja.ragged import RaggedMmap
from microwakeword.audio.augmentation import Augmentation
from microwakeword.audio.clips import Clips
from microwakeword.audio.spectrograms import SpectrogramGeneration

OUTPUT_DIR = "generated_augmented_features"
NEG_OUTPUT_DIR = "generated_negative_features"


def clean_old_features():
    for out_dir in [OUTPUT_DIR, NEG_OUTPUT_DIR]:
        if os.path.exists(out_dir):
            print(f"[features] Removing existing '{out_dir}'...")
            shutil.rmtree(out_dir)


def build_clips_and_augmenter():
    clips = Clips(
        input_directory="generated_samples/augmented",
        file_pattern="*.wav",
        max_clip_duration_s=None,
        remove_silence=False,
        random_split_seed=10,
        split_count=0.1,
    )
    augmenter = Augmentation(
        augmentation_duration_s=3.2,
        augmentation_probabilities={
            "SevenBandParametricEQ": 0.1,
            "TanhDistortion": 0.1,
            "PitchShift": 0.1,
            "BandStopFilter": 0.1,
            "AddColorNoise": 0.1,
            "AddBackgroundNoise": 0.75,
            "Gain": 1.0,
            "RIR": 0.5,
        },
        impulse_paths=["mit_rirs"],
        background_paths=["fma_16k", "audioset_16k"],
        background_min_snr_db=-5,
        background_max_snr_db=10,
        min_jitter_s=0.195,
        max_jitter_s=0.205,
    )
    return clips, augmenter


def build_positive_features(clips, augmenter):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for split in ["training", "validation", "testing"]:
        out_dir = os.path.join(OUTPUT_DIR, split)
        os.makedirs(out_dir, exist_ok=True)

        split_name = "train"
        repetition = int(os.environ.get("TRAIN_REPETITION", "2"))
        spectrograms = SpectrogramGeneration(
            clips=clips, augmenter=augmenter, slide_frames=10, step_ms=10
        )
        if split == "validation":
            split_name = "validation"
            repetition = 1
        elif split == "testing":
            split_name = "test"
            repetition = 1
            spectrograms = SpectrogramGeneration(
                clips=clips, augmenter=augmenter, slide_frames=1, step_ms=10
            )

        print(f"[features] Building positive {split} set...")
        RaggedMmap.from_generator(
            out_dir=os.path.join(out_dir, "wakeword_mmap"),
            sample_generator=spectrograms.spectrogram_generator(
                split=split_name, repeat=repetition
            ),
            batch_size=100,
            verbose=True,
        )


def build_negative_features(augmenter):
    if not os.path.exists("generated_negatives/augmented"):
        print("[features] Warning: 'generated_negatives/augmented' not found.")
        return

    print("[features] Building dedicated negative features...")
    os.makedirs(NEG_OUTPUT_DIR, exist_ok=True)

    neg_clips = Clips(
        input_directory="generated_negatives/augmented",
        file_pattern="*.wav",
        max_clip_duration_s=None,
        remove_silence=False,
        random_split_seed=10,
        split_count=0.1,
    )

    for split in ["training", "validation", "testing"]:
        out_dir = os.path.join(NEG_OUTPUT_DIR, split)
        os.makedirs(out_dir, exist_ok=True)

        split_name = "train"
        if split == "validation":
            split_name = "validation"
        elif split == "testing":
            split_name = "test"

        # Same augmenter as positives (noise/RIR/EQ/etc.) — without this,
        # hard negatives only ever exist as clean studio-quality TTS, while
        # positives are trained across noisy/reverberant variations. That
        # asymmetry can bias the model toward treating noisy audio as more
        # positive-like than it should.
        spectrograms = SpectrogramGeneration(
            clips=neg_clips, augmenter=augmenter, slide_frames=10, step_ms=10
        )

        print(f"[features] Building negative {split} set...")
        RaggedMmap.from_generator(
            out_dir=os.path.join(out_dir, "wakeword_mmap"),
            sample_generator=spectrograms.spectrogram_generator(
                split=split_name, repeat=1
            ),
            batch_size=100,
            verbose=True,
        )


def main():
    clean_old_features()
    clips, augmenter = build_clips_and_augmenter()
    build_positive_features(clips, augmenter)
    build_negative_features(augmenter)
    print("[features] Feature generation complete.")


if __name__ == "__main__":
    main()