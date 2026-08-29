#!/usr/bin/env python3
"""
aec_score.py - objective end-to-end scoring of an acoustic echo canceller.

Turns "it removes more than half my voice" into two numbers you can compare
across configuration changes:

  ERLE          how much echo the AEC removes            (want > 30 dB)
  RETENTION     how much near-end speech survives        (want > -3 dB)
  WHISTLE       musical-noise / isolated-tone indicator  (want < ~2)

Rig
---
You need a second, independent loudspeaker acting as the "talker" - a cheap
wired USB speaker is ideal; do NOT use Bluetooth, its latency wanders.
Place it at a fixed distance (50 cm is fine) and MARK THE POSITION WITH TAPE.
Every later run must use the identical geometry and identical levels or the
numbers are not comparable.

Before running, force unity gain on both capture nodes so the raw and
echo-cancelled paths are directly comparable:

    wpctl set-volume <raw-source-id> 1.0
    wpctl set-volume <aec-source-id> 1.0

Usage
-----
    python3 aec_score.py devices
    python3 aec_score.py run \
        --enclosure-out "ec_sink" \
        --talker-out    "alsa_output.usb-..." \
        --in-aec        "ec_source" \
        --in-raw        "alsa_input.platform-...seeed2micvoicec..." \
        --tag baseline

    python3 aec_score.py compare baseline no_ns no_agc
"""

import argparse
import json
import os
import sys
import threading
import time

import numpy as np
from scipy.signal import lfilter, stft

FS = 48000
BANDS = [(125, 250), (250, 500), (500, 1000), (1000, 2000),
         (2000, 4000), (4000, 8000)]


# ---------------------------------------------------------------- test signals
def speech_shaped(dur, fs=FS, seed=0, syllable_rate=4.0):
    """Speech-shaped noise with a syllabic envelope and realistic pauses.

    Not real speech, but stationary enough to be repeatable and modulated
    enough to exercise a VAD / AGC / residual-echo suppressor the same way.
    """
    rng = np.random.default_rng(seed)
    n = int(dur * fs)
    x = rng.standard_normal(n)

    # long-term average speech spectrum: flat to ~500 Hz, -9 dB/oct above
    b, a = [1.0], [1.0, -0.92]
    x = lfilter(b, a, x)                       # tilt up low end
    b2, a2 = [1.0, -0.85], [1.0]
    x = lfilter(b2, a2, x)                     # gentle HF roll-in
    # band-limit to 100 Hz .. 8 kHz
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / fs)
    X[(f < 100) | (f > 8000)] = 0
    x = np.fft.irfft(X, n)

    # syllabic envelope + pauses (so RETENTION can be measured on active frames)
    t = np.arange(n) / fs
    env = 0.5 * (1 + np.sin(2 * np.pi * syllable_rate * t + rng.uniform(0, 6.28)))
    env = env ** 1.5
    pause = np.ones(n)
    for start in rng.uniform(0, dur - 0.6, size=int(dur / 3)):
        i = int(start * fs)
        pause[i:i + int(0.5 * fs)] = 0.0
    x = x * env * pause
    return (x / (np.max(np.abs(x)) + 1e-12)).astype(np.float32)


def load_or_make(path, dur, seed):
    if path:
        import soundfile as sf
        d, sr = sf.read(path, dtype="float32", always_2d=False)
        if d.ndim > 1:
            d = d.mean(axis=1)
        if sr != FS:
            sys.exit(f"{path} is {sr} Hz, please resample to {FS}")
        return d[: int(dur * FS)]
    return speech_shaped(dur, seed=seed)


# ---------------------------------------------------------------- transport
def _play(sig, device, level):
    import sounddevice as sd
    sd.play(np.tile((sig * level).reshape(-1, 1), (1, 2)),
            samplerate=FS, device=device, blocking=True)


def capture_scenario(dur, in_dev, plays, settle=1.0):
    """plays = list of (signal, out_device, level). Returns mono recording."""
    import sounddevice as sd
    rec = sd.rec(int((dur + 2 * settle) * FS), samplerate=FS, channels=2,
                 device=in_dev, dtype="float32", blocking=False)
    time.sleep(settle)
    threads = [threading.Thread(target=_play, args=p) for p in plays]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sd.wait()
    r = np.asarray(rec, dtype=np.float64)
    r = r.mean(axis=1)
    return r[int(settle * FS): int((settle + dur) * FS)]


# ---------------------------------------------------------------- metrics
def frame_energy(x, win=0.02):
    n = int(win * FS)
    m = len(x) // n
    return (x[: m * n].reshape(m, n) ** 2).mean(axis=1)


def band_energy(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / FS)
    X[(f < lo) | (f >= hi)] = 0
    return float(np.mean(np.fft.irfft(X, len(x)) ** 2))


def db(num, den):
    return float(10 * np.log10(max(num, 1e-30) / max(den, 1e-30)))


def whistle_index(x):
    """Count isolated narrowband peaks that flicker in and out over time.

    Musical noise = many short-lived tonal bins. A clean residual has few.
    """
    f, t, Z = stft(x, fs=FS, nperseg=1024, noverlap=768)
    P = 20 * np.log10(np.abs(Z) + 1e-12)
    med = np.median(P, axis=0, keepdims=True)
    mask = P > (med + 18)
    per_frame = mask.sum(axis=0)
    # short-lived = high frame-to-frame churn in which bins are hot
    churn = np.mean(np.abs(np.diff(mask.astype(int), axis=1)))
    return float(per_frame.mean() * churn * 100)


def score(near_ref, far_raw, far_aec, both):
    active = frame_energy(near_ref) > (np.percentile(frame_energy(near_ref), 60))
    n = int(0.02 * FS)

    def masked(x):
        m = min(len(active), len(x) // n)
        return x[: m * n].reshape(m, n)[active[:m]].ravel()

    e_near = float(np.mean(masked(near_ref) ** 2))
    e_both = float(np.mean(masked(both) ** 2))

    out = {
        "erle_db": db(np.mean(far_raw ** 2), np.mean(far_aec ** 2)),
        "retention_db": db(e_both, e_near),
        "residual_echo_dbfs": float(10 * np.log10(max(np.mean(far_aec ** 2), 1e-30))),
        "whistle_index": whistle_index(far_aec),
        "retention_by_band_db": {},
        "erle_by_band_db": {},
    }
    for lo, hi in BANDS:
        k = f"{lo}-{hi}"
        out["retention_by_band_db"][k] = db(band_energy(both, lo, hi),
                                            band_energy(near_ref, lo, hi))
        out["erle_by_band_db"][k] = db(band_energy(far_raw, lo, hi),
                                       band_energy(far_aec, lo, hi))
    return out


# ---------------------------------------------------------------- commands
def cmd_devices(_):
    import sounddevice as sd
    print(sd.query_devices())


def cmd_run(a):
    far = load_or_make(a.far_wav, a.dur, seed=1)
    near = load_or_make(a.near_wav, a.dur, seed=2)
    d = os.path.join(a.dir, a.tag)
    os.makedirs(d, exist_ok=True)

    print("1/4 near-end only  (talker on, enclosure silent) -> AEC source")
    near_ref = capture_scenario(a.dur, a.in_aec, [(near, a.talker_out, a.near_level)])
    print("2/4 far-end only   (enclosure on, talker silent) -> RAW source")
    far_raw = capture_scenario(a.dur, a.in_raw, [(far, a.enclosure_out, a.far_level)])
    print("3/4 far-end only   (enclosure on, talker silent) -> AEC source")
    far_aec = capture_scenario(a.dur, a.in_aec, [(far, a.enclosure_out, a.far_level)])
    print("4/4 double-talk    (both on)                     -> AEC source")
    both = capture_scenario(a.dur, a.in_aec, [(near, a.talker_out, a.near_level),
                                              (far, a.enclosure_out, a.far_level)])

    for name, sig in [("near_ref", near_ref), ("far_raw", far_raw),
                      ("far_aec", far_aec), ("both", both)]:
        np.save(os.path.join(d, name + ".npy"), sig)
        if np.max(np.abs(sig)) > 0.99:
            print(f"!! {name} is clipping - results invalid", file=sys.stderr)

    res = score(near_ref, far_raw, far_aec, both)
    res["tag"] = a.tag
    res["levels"] = {"far": a.far_level, "near": a.near_level}
    with open(os.path.join(d, "score.json"), "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))
    verdict(res)


def verdict(r):
    print("\n--- verdict ---")
    if r["erle_db"] < 20:
        print(f"ERLE {r['erle_db']:.1f} dB: the linear filter is not converging. "
              "Suspect nonlinearity, a time-varying mic gain, or a tail longer "
              "than the filter. Do NOT tune suppression until this is fixed.")
    elif r["erle_db"] < 30:
        print(f"ERLE {r['erle_db']:.1f} dB: marginal. Suppression will be doing "
              "the rest of the work, which is what damages near-end speech.")
    else:
        print(f"ERLE {r['erle_db']:.1f} dB: healthy.")

    if r["retention_db"] < -8:
        print(f"RETENTION {r['retention_db']:.1f} dB: severe near-end damage.")
    elif r["retention_db"] < -3:
        print(f"RETENTION {r['retention_db']:.1f} dB: audible but workable.")
    else:
        print(f"RETENTION {r['retention_db']:.1f} dB: good.")

    worst = min(r["retention_by_band_db"].items(), key=lambda kv: kv[1])
    print(f"worst band: {worst[0]} Hz at {worst[1]:.1f} dB")
    print(f"WHISTLE index {r['whistle_index']:.2f} "
          f"({'musical noise likely' if r['whistle_index'] > 2 else 'clean'})")


def cmd_compare(a):
    rows = []
    for tag in a.tags:
        p = os.path.join(a.dir, tag, "score.json")
        if not os.path.exists(p):
            print(f"missing {p}", file=sys.stderr)
            continue
        rows.append(json.load(open(p)))
    if not rows:
        return
    w = max(len(r["tag"]) for r in rows) + 2
    print(f"{'tag':<{w}}{'ERLE':>8}{'RETAIN':>9}{'WHISTLE':>9}{'worst band':>16}")
    for r in rows:
        wb = min(r["retention_by_band_db"].items(), key=lambda kv: kv[1])
        print(f"{r['tag']:<{w}}{r['erle_db']:>8.1f}{r['retention_db']:>9.1f}"
              f"{r['whistle_index']:>9.2f}{wb[0] + ' ' + format(wb[1], '.1f'):>16}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)

    s.add_parser("devices").set_defaults(func=cmd_devices)

    r = s.add_parser("run")
    r.add_argument("--enclosure-out", required=True)
    r.add_argument("--talker-out", required=True)
    r.add_argument("--in-aec", required=True)
    r.add_argument("--in-raw", required=True)
    r.add_argument("--tag", required=True)
    r.add_argument("--dir", default="runs")
    r.add_argument("--dur", type=float, default=45.0)
    r.add_argument("--far-level", type=float, default=0.3)
    r.add_argument("--near-level", type=float, default=0.3)
    r.add_argument("--far-wav", default=None)
    r.add_argument("--near-wav", default=None)
    r.set_defaults(func=cmd_run)

    c = s.add_parser("compare")
    c.add_argument("tags", nargs="+")
    c.add_argument("--dir", default="runs")
    c.set_defaults(func=cmd_compare)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
