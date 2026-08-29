#!/usr/bin/env python3
"""Record wake-word utterances on the device and auto-split them into one-word clips.

You say the wake word repeatedly (with ~1 s pauses, moving around the room), and
this cuts the stream at silence into individual 16 kHz mono WAV clips using a
simple energy-based voice-activity detector (numpy only — no webrtcvad/ffmpeg
needed). Then review them and delete the bad ones.

Designed for the Chochko device (RPi Zero 2W + ReSpeaker 2-mic, PipeWire+AEC).
Recording through `arecord -D pipewire` uses the SAME echo-cancelled mono source
the wake-word runtime sees, so these clips match real inference conditions.

USAGE
-----
1) Record live from the ReSpeaker (recommended — same path as test_mww.py):
     arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - \
       | ~/.venv/bin/python record_clips.py --stdin --out real_clips
   Say the wake word with ~1 s gaps; press Ctrl+C (stops arecord) when done.

2) Segment an EXISTING recording (wav from arecord, or anything ffmpeg reads):
     ~/.venv/bin/python record_clips.py --input session.wav --out real_clips

3) Review clips one by one (plays each, keep/delete):
     ~/.venv/bin/python record_clips.py --review real_clips

4) Renumber after deletions leave gaps (also fixes the old overwrite bug --
   recording used to resume from the file COUNT, not the highest index used,
   so post-review sessions could silently clobber existing clips):
     ~/.venv/bin/python record_clips.py --renumber real_clips

Tuning: if it merges two words or splits one in two, adjust --gap-ms (silence
needed to cut) and --threshold-factor (higher = only louder speech counts).
"""
import argparse
import contextlib
import os
import subprocess
import sys
import wave

import numpy as np

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2      # int16
FRAME_MS = 20             # analysis frame
FRAME_LEN = int(SAMPLE_RATE * FRAME_MS / 1000)   # samples per frame


# --------------------------- audio input ---------------------------

def read_stdin_pcm():
    """Read raw s16le 16 kHz mono PCM from stdin until EOF/Ctrl+C (arecord pipe)."""
    print(">> Reading raw 16 kHz mono PCM from stdin (arecord). "
          "Say the wake word with ~1 s gaps; Ctrl+C to finish.", file=sys.stderr)
    chunks = []
    try:
        while True:
            b = sys.stdin.buffer.read(4096)
            if not b:
                break
            chunks.append(b)
    except KeyboardInterrupt:
        pass
    return b"".join(chunks)


def load_pcm_16k_mono(path):
    """Return raw int16 PCM at 16 kHz mono. Fast path for matching WAVs; else ffmpeg."""
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            if (wf.getframerate() == SAMPLE_RATE and wf.getnchannels() == 1
                    and wf.getsampwidth() == BYTES_PER_SAMPLE):
                return wf.readframes(wf.getnframes())
    except (wave.Error, EOFError):
        pass  # not a plain 16k mono WAV — fall through to ffmpeg
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-f", "wav", "-acodec", "pcm_s16le", tmp],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        sys.exit(f"'{path}' is not 16 kHz mono WAV and ffmpeg isn't installed.\n"
                 "Either record with: arecord -r 16000 -c 1 -f S16_LE -t wav ...\n"
                 "or install ffmpeg: sudo apt install -y ffmpeg")
    with contextlib.closing(wave.open(tmp, "rb")) as wf:
        pcm = wf.readframes(wf.getnframes())
    os.unlink(tmp)
    return pcm


def record_sounddevice(seconds):
    """Optional PC-side capture (needs sounddevice). The device uses --stdin instead."""
    try:
        import sounddevice as sd
    except ImportError:
        sys.exit("--record needs sounddevice (pip install sounddevice + "
                 "sudo apt install -y libportaudio2). On the RPi use --stdin with arecord.")
    buf = []

    def cb(indata, frames, t, status):
        buf.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=cb):
        if seconds:
            print(f">> Recording {seconds}s...", file=sys.stderr)
            sd.sleep(int(seconds * 1000))
        else:
            print(">> Recording... Ctrl+C to stop.", file=sys.stderr)
            try:
                while True:
                    sd.sleep(200)
            except KeyboardInterrupt:
                pass
    return np.concatenate(buf, axis=0).tobytes() if buf else b""


# --------------------------- energy VAD segmentation ---------------------------

def frame_rms(pcm):
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    n = len(x) // FRAME_LEN
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    fr = x[:n * FRAME_LEN].reshape(n, FRAME_LEN)
    return np.sqrt((fr * fr).mean(axis=1) + 1.0)


def speech_flags(pcm, factor, floor_ratio=0.06):
    """Per-frame speech/not-speech via an auto noise-floor threshold."""
    rms = frame_rms(pcm)
    if rms.size == 0:
        return rms.astype(bool)
    noise = float(np.percentile(rms, 15))     # robust noise floor
    peak = float(rms.max())
    thresh = max(noise * factor, peak * floor_ratio)
    return rms > thresh


def collect_segments(flags, gap_frames):
    """State machine: a run of speech ends after `gap_frames` of silence."""
    segs = []
    triggered = False
    start = 0
    sil = 0
    for i, v in enumerate(flags):
        if not triggered:
            if v:
                triggered, start, sil = True, i, 0
        else:
            if v:
                sil = 0
            else:
                sil += 1
                if sil >= gap_frames:
                    segs.append((start, i - sil + 1))
                    triggered = False
    if triggered:
        segs.append((start, len(flags)))
    return segs


def segment(pcm, factor, gap_ms, padding_ms, min_ms, max_ms):
    flags = speech_flags(pcm, factor)
    if flags.size == 0:
        return []
    gap_frames = max(1, int(gap_ms / FRAME_MS))
    pad = int(padding_ms / FRAME_MS)
    total_frames = len(pcm) // (FRAME_LEN * BYTES_PER_SAMPLE)
    clips = []
    for s, e in collect_segments(flags, gap_frames):
        s2 = max(0, s - pad)
        e2 = min(total_frames, e + pad)
        dur_ms = (e2 - s2) * FRAME_MS
        if dur_ms < min_ms or dur_ms > max_ms:
            continue
        b0 = s2 * FRAME_LEN * BYTES_PER_SAMPLE
        b1 = e2 * FRAME_LEN * BYTES_PER_SAMPLE
        clips.append(pcm[b0:b1])
    return clips


# --------------------------- output + review ---------------------------

def write_wav(pcm_bytes, path):
    with contextlib.closing(wave.open(path, "wb")) as wf:
        wf.setnchannels(1)
        wf.setsampwidth(BYTES_PER_SAMPLE)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)


def next_index(out_dir, prefix):
    """Highest existing '{prefix}_NNN.wav' index + 1 (not a file count, which
    would shrink after --review deletions and cause new clips to overwrite
    surviving ones)."""
    if not os.path.isdir(out_dir):
        return 0
    indices = []
    for f in os.listdir(out_dir):
        if f.startswith(prefix + "_") and f.endswith(".wav"):
            num = f[len(prefix) + 1:-4]
            if num.isdigit():
                indices.append(int(num))
    return max(indices) + 1 if indices else 0


def renumber(out_dir, prefix):
    """Close gaps left by --review deletions: relabel existing clips as
    {prefix}_000.wav, {prefix}_001.wav, ... in their current sorted order."""
    def index_of(name):
        return int(name[len(prefix) + 1:-4])

    clips = sorted(
        (f for f in os.listdir(out_dir)
         if f.startswith(prefix + "_") and f.endswith(".wav")
         and f[len(prefix) + 1:-4].isdigit()),
        key=index_of,
    )
    if not clips:
        sys.exit(f"No '{prefix}_*.wav' clips in {out_dir}")
    # Two passes so a target filename that's still in use never gets clobbered.
    tmp_paths = []
    for name in clips:
        tmp = os.path.join(out_dir, f".renum_{name}")
        os.rename(os.path.join(out_dir, name), tmp)
        tmp_paths.append(tmp)
    for i, tmp in enumerate(tmp_paths):
        os.rename(tmp, os.path.join(out_dir, f"{prefix}_{i:03d}.wav"))
    print(f">> Renumbered {len(clips)} clips in {out_dir}/ to "
          f"{prefix}_000.wav .. {prefix}_{len(clips) - 1:03d}.wav")


def play(path):
    for cmd in (["pw-play", path],
                ["aplay", "-q", "-D", "pipewire", path],
                ["aplay", "-q", path],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]):
        try:
            subprocess.run(cmd, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def review(out_dir):
    clips = sorted(f for f in os.listdir(out_dir) if f.endswith(".wav"))
    if not clips:
        sys.exit(f"No .wav clips in {out_dir}")
    print(f">> Reviewing {len(clips)} clips.  [Enter]=keep  d=delete  r=replay  q=quit")
    kept = deleted = 0
    for name in clips:
        path = os.path.join(out_dir, name)
        while True:
            if not play(path):
                print("   (no audio player found; install alsa-utils or use pw-play)")
            ans = input(f"   {name}  [keep]/d/r/q > ").strip().lower()
            if ans in ("", "k"):
                kept += 1
                break
            if ans == "d":
                os.unlink(path)
                deleted += 1
                print("   deleted")
                break
            if ans == "q":
                print(f">> Stopped. kept={kept} deleted={deleted}")
                return
            # 'r'/anything -> replay
    print(f">> Done. kept={kept} deleted={deleted}")


# --------------------------- main ---------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stdin", action="store_true",
                    help="read raw 16k mono PCM from stdin (arecord -D pipewire ... -t raw -)")
    ap.add_argument("--input", help="segment this existing audio file")
    ap.add_argument("--record", action="store_true", help="PC-only live capture via sounddevice")
    ap.add_argument("--seconds", type=int, default=None, help="fixed length for --record")
    ap.add_argument("--review", metavar="DIR", help="play/keep/delete clips in DIR")
    ap.add_argument("--renumber", metavar="DIR",
                    help="close gaps left by --review deletions, relabeling clips 000..N-1")
    ap.add_argument("--out", default="real_clips", help="output dir (default: real_clips)")
    ap.add_argument("--prefix", default="cho", help="clip filename prefix (default: cho)")
    ap.add_argument("--save-session", help="also save the raw recording to this .wav")
    ap.add_argument("--threshold-factor", type=float, default=3.0,
                    help="speech threshold vs noise floor (higher = stricter). Default 3.0")
    ap.add_argument("--gap-ms", type=int, default=300, help="silence needed to split words")
    ap.add_argument("--padding-ms", type=int, default=250, help="context kept around each word")
    ap.add_argument("--min-ms", type=int, default=250, help="drop clips shorter than this")
    ap.add_argument("--max-ms", type=int, default=1500, help="drop clips longer than this")
    args = ap.parse_args()

    if args.review:
        review(args.review)
        return

    if args.renumber:
        renumber(args.renumber, args.prefix)
        return

    if args.stdin:
        pcm = read_stdin_pcm()
    elif args.input:
        pcm = load_pcm_16k_mono(args.input)
    elif args.record:
        pcm = record_sounddevice(args.seconds)
    else:
        ap.error("specify --stdin (arecord pipe), --input FILE, or --review DIR")

    if not pcm:
        sys.exit("No audio captured.")
    if args.save_session:
        write_wav(pcm, args.save_session)
        print(f">> Raw session saved to {args.save_session}", file=sys.stderr)

    clips = segment(pcm, args.threshold_factor, args.gap_ms,
                    args.padding_ms, args.min_ms, args.max_ms)
    os.makedirs(args.out, exist_ok=True)
    start = next_index(args.out, args.prefix)
    for k, seg in enumerate(clips):
        write_wav(seg, os.path.join(args.out, f"{args.prefix}_{start + k:03d}.wav"))
    total = start + len(clips)
    secs = len(pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
    print(f">> {secs:.1f}s captured -> wrote {len(clips)} clips to {args.out}/ (total {total}).")
    print(f">> Review next:  ~/.venv/bin/python {os.path.basename(__file__)} --review {args.out}")
    if not clips:
        print(">> No segments found. Try --threshold-factor 2.0 (looser), or check the "
              "capture level (arecord ... -t wav test.wav; aplay test.wav).")


if __name__ == "__main__":
    main()
