#!/usr/bin/env python3
"""Multi-Engine Bulgarian Sample Generator & Pitch Multiplier for microWakeWord.

Usage:
    python create_samples.py 1          # Generate 1 sample per voice and play back each
    python create_samples.py 150        # Bulk generation mode (SSML + SoX pitch multiplier)
"""

import asyncio
import os
import random
import subprocess
import sys
import time

TARGET_WORD = os.environ.get("TARGET_WORD", "Чочко")
OUT_DIR = "generated_samples"
RAW_DIR = os.path.join(OUT_DIR, "raw")
AUG_DIR = os.path.join(OUT_DIR, "augmented")

# Semitones applied via SoX pitch shift
PITCH_SEMITONES = [-4, -2, -1, 0, 1, 2, 4]

# Google Chirp 3 HD Voices
GOOGLE_VOICES = [
    ("male", "bg-BG-Chirp3-HD-Charon"),
    ("male", "bg-BG-Chirp3-HD-Iapetus"),
    ("female", "bg-BG-Chirp3-HD-Leda"),
    ("female", "bg-BG-Chirp3-HD-Despina"),
    ("female", "bg-BG-Chirp3-HD-Callirrhoe"),
]

# Edge TTS Voices
EDGE_VOICES = [
    ("male", "bg-BG-BorislavNeural"),
    ("female", "bg-BG-KalinaNeural"),
]


def play_audio(path):
    """Play WAV file using system audio backends."""
    for cmd in (
        ["pw-play", path],
        ["aplay", "-q", "-D", "pipewire", path],
        ["aplay", "-q", path],
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
    ):
        try:
            subprocess.run(cmd, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    print(f"   (No player found to play {path})")
    return False


def check_auth_google():
    cred_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    default_path = os.path.expanduser(
        "~/.config/gcloud/application_default_credentials.json"
    )
    return bool(
        (cred_env and os.path.exists(cred_env))
        or os.path.exists(default_path)
    )


def generate_google_samples(samples_per_voice, should_play):
    if not check_auth_google():
        print("[Google TTS] Skipping: Credentials not found.")
        return

    from google.api_core.exceptions import ResourceExhausted
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()

    for gender, voice_name in GOOGLE_VOICES:
        voice_short = voice_name.split("-")[-1]
        print(f"[Google/{gender}/{voice_short}] Generating...")

        for i in range(samples_per_voice):
            out_path = os.path.join(
                RAW_DIR, f"g_{voice_short}_{i:04d}.wav"
            )

            if not os.path.exists(out_path):
                rate_pct = 100 if should_play else random.randint(85, 115)
                pitch_st = 0 if should_play else random.randint(-3, 3)
                ssml_text = f'<speak><prosody rate="{rate_pct}%" pitch="{pitch_st:+d}st">{TARGET_WORD}</prosody></speak>'

                synthesis_input = texttospeech.SynthesisInput(
                    ssml=ssml_text
                )
                voice_params = texttospeech.VoiceSelectionParams(
                    language_code="bg-BG", name=voice_name
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                )

                for attempt in range(5):
                    try:
                        response = client.synthesize_speech(
                            input=synthesis_input,
                            voice=voice_params,
                            audio_config=audio_config,
                        )
                        with open(out_path, "wb") as f:
                            f.write(response.audio_content)
                        break
                    except ResourceExhausted:
                        time.sleep(2.0 * (attempt + 1))
                    except Exception as e:
                        print(f"   Error: {e}")
                        break
                time.sleep(0.15)

            if should_play and os.path.exists(out_path):
                print(f"   -> Playing {out_path}...")
                play_audio(out_path)


async def generate_edge_voice_samples(
    gender, voice_name, samples_per_voice, should_play
):
    import edge_tts

    voice_short = voice_name.split("-")[-1]
    print(f"[Edge/{gender}/{voice_short}] Generating...")

    for i in range(samples_per_voice):
        out_path_mp3 = os.path.join(
            RAW_DIR, f"e_{voice_short}_{i:04d}_temp.mp3"
        )
        out_path_wav = os.path.join(RAW_DIR, f"e_{voice_short}_{i:04d}.wav")

        if not os.path.exists(out_path_wav):
            rate_val = (
                "+0%" if should_play else f"{random.randint(-15, 15):+d}%"
            )
            pitch_val = (
                "+0Hz" if should_play else f"{random.randint(-10, 10):+d}Hz"
            )

            communicate = edge_tts.Communicate(
                TARGET_WORD, voice_name, rate=rate_val, pitch=pitch_val
            )
            await communicate.save(out_path_mp3)

            subprocess.run(
                [
                    "sox",
                    out_path_mp3,
                    "-r",
                    "16000",
                    "-c",
                    "1",
                    "-b",
                    "16",
                    out_path_wav,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(out_path_mp3):
                os.remove(out_path_mp3)

        if should_play and os.path.exists(out_path_wav):
            print(f"   -> Playing {out_path_wav}...")
            play_audio(out_path_wav)


def apply_sox_pitch_shift():
    print("\n>> Applying pitch shifting (SoX) to multiply voice timbres...")
    raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith(".wav")]

    for idx, fname in enumerate(raw_files):
        src_path = os.path.join(RAW_DIR, fname)
        base_name = os.path.splitext(fname)[0]

        for st in PITCH_SEMITONES:
            dst_path = os.path.join(
                AUG_DIR, f"{base_name}_st{st:+d}.wav"
            )
            if os.path.exists(dst_path):
                continue

            if st == 0:
                subprocess.run(
                    ["cp", src_path, dst_path], check=True
                )
            else:
                cents = st * 100
                subprocess.run(
                    ["sox", src_path, dst_path, "pitch", str(cents)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

        if (idx + 1) % 100 == 0 or idx == len(raw_files) - 1:
            print(f"   Processed {idx + 1}/{len(raw_files)} base files.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_samples.py <samples_per_voice>")
        sys.exit(1)

    try:
        samples_per_voice = int(sys.argv[1])
    except ValueError:
        print(f"Error: Argument must be an integer, got '{sys.argv[1]}'")
        sys.exit(1)

    should_play = samples_per_voice == 1

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(AUG_DIR, exist_ok=True)

    print(f">> Target Word: '{TARGET_WORD}'")
    print(
        f">> Target: {samples_per_voice} clip(s) per voice across 7 voices"
    )

    # 1. Google Voices
    generate_google_samples(samples_per_voice, should_play)

    # 2. Edge TTS Voices
    for gender, voice_name in EDGE_VOICES:
        asyncio.run(
            generate_edge_voice_samples(
                gender, voice_name, samples_per_voice, should_play
            )
        )

    # Skip pitch shifting in test playback mode
    if should_play:
        print("\n>> Test run completed.")
        return

    # 3. SoX Pitch Shifting (bulk mode only)
    apply_sox_pitch_shift()

    total_augmented = len(
        [f for f in os.listdir(AUG_DIR) if f.endswith(".wav")]
    )
    print(
        f"\n>> Finished! {total_augmented} total positive samples in '{AUG_DIR}/'"
    )


if __name__ == "__main__":
    main()
    