#!/usr/bin/env python3
"""Bulgarian Hard-Negative Sample Generator for microWakeWord.

Generates ~2,500 base negative samples of Bulgarian phonetic near-misses,
common words, and short syllables across 7 TTS voices, then pitch-shifts them.

Usage:
    python create_negative_samples.py 350
"""

import asyncio
import os
import random
import subprocess
import sys
import time

OUT_DIR = "generated_negatives"
RAW_DIR = os.path.join(OUT_DIR, "raw")
AUG_DIR = os.path.join(OUT_DIR, "augmented")

# Pitch shifting semitones applied via SoX (-4 to +4)
PITCH_SEMITONES = [-4, -2, -1, 0, 1, 2, 4]

# Curated Bulgarian Hard Negatives
NEGATIVE_WORDS = [
    # Phonetic Near-Misses (~50%)
    "Точко", "Чочо", "Кочко", "Бачко", "Мачко", "Точка", "Четка",
    "Чочкови", "Чочка", "Точки", "Кочка", "Бачка", "Бочко", "Почко",
    
    # Critical Number & Phonetic Negatives
    "четири", "четирейсет", "четиринадесет", "четиристотин",
    "четвъртък", "честно", "често", "число", "чиния", 
    "чакам", "чашка", "чичо", "чип", "чоп",
    
    # Common Command & Conversational Words (~35%)
    "Всичко", "Какво", "Защо", "Това", "Благодаря", "Светло", "Пусни",
    "Спри", "Часът", "Разбрах", "Добре", "Къде", "Кога", "Няма",
    
    # Short Syllables & Phonemes (~15%)
    "Да", "Не", "Чакай", "Още", "Чо", "Ко", "Чи", "Че", "Чу"
]

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


def check_auth_google():
    cred_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    default_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    return bool((cred_env and os.path.exists(cred_env)) or os.path.exists(default_path))


def next_available_index(prefix):
    """Highest existing '{prefix}_NNNN.wav' index + 1. Scans actual files
    rather than trusting a passed-in count, so pruning (which removes files
    from the middle of the range, leaving gaps) can never cause a fresh
    generation run to silently overwrite -- or skip past -- a survivor."""
    if not os.path.isdir(RAW_DIR):
        return 0
    indices = []
    for f in os.listdir(RAW_DIR):
        if f.startswith(prefix + "_") and f.endswith(".wav"):
            num = f[len(prefix) + 1:-4]
            if num.isdigit():
                indices.append(int(num))
    return max(indices) + 1 if indices else 0


def generate_google_negatives(samples_per_voice):
    if not check_auth_google():
        print("[Google TTS] Skipping: Credentials not found.")
        return

    from google.cloud import texttospeech
    from google.api_core.exceptions import ResourceExhausted

    client = texttospeech.TextToSpeechClient()

    for gender, voice_name in GOOGLE_VOICES:
        voice_short = voice_name.split("-")[-1]
        prefix = f"g_neg_{voice_short}"
        start = next_available_index(prefix)
        print(f"[Google/{gender}/{voice_short}] Generating {samples_per_voice} new negative clips "
              f"(starting at index {start})...")

        for i in range(start, start + samples_per_voice):
            out_path = os.path.join(RAW_DIR, f"{prefix}_{i:04d}.wav")

            target_word = random.choice(NEGATIVE_WORDS)
            rate_pct = random.randint(70, 130)
            pitch_st = random.randint(-3, 3)
            ssml_text = f'<speak><prosody rate="{rate_pct}%" pitch="{pitch_st:+d}st">{target_word}</prosody></speak>'

            synthesis_input = texttospeech.SynthesisInput(ssml=ssml_text)
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
                        input=synthesis_input, voice=voice_params, audio_config=audio_config
                    )
                    with open(out_path, "wb") as f:
                        f.write(response.audio_content)
                    break
                except ResourceExhausted:
                    time.sleep(2.0 * (attempt + 1))
                except Exception as e:
                    print(f"   Error: {e}")
                    break
            time.sleep(0.12)


async def generate_edge_negatives(gender, voice_name, samples_per_voice):
    import edge_tts

    voice_short = voice_name.split("-")[-1]
    prefix = f"e_neg_{voice_short}"
    start = next_available_index(prefix)
    print(f"[Edge/{gender}/{voice_short}] Generating {samples_per_voice} new negative clips "
          f"(starting at index {start})...")

    for i in range(start, start + samples_per_voice):
        out_path_mp3 = os.path.join(RAW_DIR, f"{prefix}_{i:04d}_temp.mp3")
        out_path_wav = os.path.join(RAW_DIR, f"{prefix}_{i:04d}.wav")

        target_word = random.choice(NEGATIVE_WORDS)
        rate_val = f"{random.randint(-30, 30):+d}%"
        pitch_val = f"{random.randint(-10, 10):+d}Hz"

        communicate = edge_tts.Communicate(target_word, voice_name, rate=rate_val, pitch=pitch_val)
        await communicate.save(out_path_mp3)

        subprocess.run(
            ["sox", out_path_mp3, "-r", "16000", "-c", "1", "-b", "16", out_path_wav],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(out_path_mp3):
            os.remove(out_path_mp3)


def apply_sox_pitch_shift():
    print("\n>> Applying pitch shifting (SoX) to negative samples...")
    raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith(".wav")]

    for idx, fname in enumerate(raw_files):
        src_path = os.path.join(RAW_DIR, fname)
        base_name = os.path.splitext(fname)[0]

        for st in PITCH_SEMITONES:
            dst_path = os.path.join(AUG_DIR, f"{base_name}_st{st:+d}.wav")
            if os.path.exists(dst_path):
                continue

            if st == 0:
                subprocess.run(["cp", src_path, dst_path], check=True)
            else:
                cents = st * 100
                subprocess.run(
                    ["sox", src_path, dst_path, "pitch", str(cents)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

        if (idx + 1) % 100 == 0 or idx == len(raw_files) - 1:
            print(f"   Processed {idx + 1}/{len(raw_files)} base negative files.")


def main():
    global NEGATIVE_WORDS

    if "--pitch-only" in sys.argv:
        # Re-derive augmented/ from whatever's currently in raw/ (e.g. after
        # pruning low-scoring clips) without calling any TTS API again.
        os.makedirs(AUG_DIR, exist_ok=True)
        apply_sox_pitch_shift()
        total_augmented = len([f for f in os.listdir(AUG_DIR) if f.endswith(".wav")])
        print(f"\n>> SUCCESS: {total_augmented} total negative WAVs in '{AUG_DIR}/'")
        return

    samples_per_voice = 350  # 350 clips * 7 voices ≈ 2,450 base clips -> ~17,150 pitch-shifted samples
    args = sys.argv[1:]

    if args:
        try:
            samples_per_voice = int(args[0])
            extra_words = args[1:]
        except ValueError:
            extra_words = args
    else:
        extra_words = []

    if extra_words:
        NEGATIVE_WORDS = extra_words
        print(f">> Restricting target words to: {NEGATIVE_WORDS}")

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(AUG_DIR, exist_ok=True)

    print(f">> Generating {samples_per_voice} new clip(s) per voice across 7 voices "
          f"(each voice picks up wherever its own existing files leave off)")

    # 1. Google Voices
    generate_google_negatives(samples_per_voice)

    # 2. Edge Voices
    for gender, voice_name in EDGE_VOICES:
        asyncio.run(generate_edge_negatives(gender, voice_name, samples_per_voice))

    # 3. Pitch shifting
    apply_sox_pitch_shift()

    total_augmented = len([f for f in os.listdir(AUG_DIR) if f.endswith(".wav")])
    print(f"\n>> SUCCESS: {total_augmented} total negative WAVs created in '{AUG_DIR}/'")


if __name__ == "__main__":
    main()
    