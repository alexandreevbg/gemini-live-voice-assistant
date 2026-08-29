#!/usr/bin/env python3
"""
enclosure_probe.py - in-situ characterisation of the loudspeaker -> microphone
echo path of a small enclosure (e.g. Raspberry Pi + ReSpeaker 2-Mic + 3 W driver).

Everything is measured in the DIGITAL domain, i.e. exactly what an AEC sees:
DAC -> class-D amp -> driver -> enclosure -> air + structure -> mic -> PGA -> ADC.

Modes
-----
  sweep : exponential sine sweep (Farina). Gives the echo impulse response,
          bulk delay, ERL (echo return loss), ring-down time, per-band ERL,
          and - crucially - harmonic distortion separated from the linear IR.
  noise : white noise. Gives magnitude-squared coherence between the reference
          and the mic, i.e. how much of the echo is linearly predictable at all.
          Coherence is the single best predictor of achievable ERLE.

IMPORTANT: run this against the RAW ALSA/PipeWire nodes for the WM8960 card,
NOT against the echo-cancelled virtual source. List devices with:
    python3 enclosure_probe.py devices

Install:
    sudo apt install python3-numpy python3-scipy python3-matplotlib
    pip3 install --break-system-packages sounddevice
"""

import argparse
import json
import sys

import numpy as np
from scipy.signal import fftconvolve, coherence, welch


# ----------------------------------------------------------------------------
# signal generation
# ----------------------------------------------------------------------------
def make_ess(fs, dur, f1, f2, fade=0.02):
    """Exponential sine sweep + its inverse filter (Farina 2000)."""
    n = int(round(dur * fs))
    t = np.arange(n) / fs
    R = np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * dur / R * (np.exp(t * R / dur) - 1.0))

    # raised-cosine fades to avoid clicks
    nf = max(1, int(fade * fs))
    w = 0.5 * (1 - np.cos(np.pi * np.arange(nf) / nf))
    x[:nf] *= w
    x[-nf:] *= w[::-1]

    # inverse filter: time-reversed sweep with -6 dB/oct envelope
    inv = x[::-1] / np.exp(t * R / dur)
    peak = np.max(np.abs(fftconvolve(x, inv)))
    inv /= peak
    return x.astype(np.float32), inv.astype(np.float32), R


def harmonic_offsets(dur, R, n_max=5):
    """Time (s) BEFORE the linear IR at which harmonic n appears."""
    return {n: dur * np.log(n) / R for n in range(2, n_max + 1)}


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------
def schroeder_decay(h, fs, peak_i):
    """Backwards-integrated energy decay curve (dB) starting at the IR peak."""
    e = h[peak_i:] ** 2
    edc = np.cumsum(e[::-1])[::-1]
    edc = 10 * np.log10(np.maximum(edc / edc[0], 1e-30))
    return edc


def decay_time(edc, fs, drop_db):
    idx = np.argmax(edc <= -drop_db)
    if idx == 0 and edc[0] > -drop_db:
        return float("nan")
    return idx / fs


def band_erl(h_lin, fs, edges):
    """Per-band echo return loss in dB, from the windowed linear IR."""
    N = 1 << int(np.ceil(np.log2(len(h_lin))))
    H = np.fft.rfft(h_lin, N)
    f = np.fft.rfftfreq(N, 1 / fs)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (f >= lo) & (f < hi)
        if not m.any():
            continue
        # RMS gain in band -> negative dB means echo is attenuated vs playback
        g = np.sqrt(np.mean(np.abs(H[m]) ** 2))
        out.append((float(lo), float(hi), float(20 * np.log10(max(g, 1e-12)))))
    return out


def analyse_sweep(rec, x, inv, fs, dur, R, pre_pad, label):
    """Deconvolve one mic channel and report the numbers that matter."""
    h = fftconvolve(rec, inv)[: len(rec)]
    peak_i = int(np.argmax(np.abs(h)))
    peak = np.abs(h[peak_i])

    # bulk delay: peak position minus the pre-pad we inserted, minus the
    # inverse-filter group delay (= len(x) - 1 after 'full' convolution trim)
    delay_s = (peak_i - (len(x) - 1) - pre_pad) / fs

    # linear IR window: a little before the peak, out to the next harmonic
    offs = harmonic_offsets(dur, R)
    pre = int(0.002 * fs)
    tail = int(min(0.5, offs[2] * 0.8) * fs)
    lo = max(0, peak_i - pre)
    hi = min(len(h), peak_i + tail)
    h_lin = h[lo:hi]

    # harmonic energies (they sit BEFORE the linear peak)
    lin_e = float(np.sum(h_lin ** 2))
    harm = {}
    guard = int(0.004 * fs)
    for n, dt in offs.items():
        c = peak_i - int(dt * fs)
        a, b = max(0, c - guard), max(0, c + guard)
        if b > a:
            harm[n] = 10 * np.log10(max(np.sum(h[a:b] ** 2), 1e-30) / max(lin_e, 1e-30))

    # ERL over the sweep itself (broadband, in the digital domain)
    seg = rec[pre_pad: pre_pad + len(x)]
    erl = 20 * np.log10(max(rms(seg), 1e-12) / max(rms(x), 1e-12))

    edc = schroeder_decay(h, fs, peak_i)
    edges = [100, 200, 400, 800, 1600, 3200, 6400, min(12000, fs // 2 - 1)]

    return {
        "channel": label,
        "peak_dbfs": float(20 * np.log10(max(peak, 1e-12))),
        "bulk_delay_ms": float(delay_s * 1e3),
        "erl_db": float(erl),
        "t20_ms": float(decay_time(edc, fs, 20) * 1e3),
        "t30_ms": float(decay_time(edc, fs, 30) * 1e3),
        "harmonic_to_linear_db": {str(k): float(v) for k, v in harm.items()},
        "band_erl_db": band_erl(h_lin, fs, edges),
        "_ir": h,
        "_ir_peak_index": peak_i,
    }


def rms(v):
    return float(np.sqrt(np.mean(np.square(v))))


# ----------------------------------------------------------------------------
# capture
# ----------------------------------------------------------------------------
def play_record(sig, fs, in_dev, out_dev, in_ch, out_ch):
    import sounddevice as sd
    data = np.tile(sig.reshape(-1, 1), (1, out_ch))
    rec = sd.playrec(data, samplerate=fs, channels=in_ch,
                     device=(in_dev, out_dev), dtype="float32", blocking=True)
    return np.asarray(rec, dtype=np.float64)


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------
def cmd_devices(_):
    import sounddevice as sd
    print(sd.query_devices())


def cmd_sweep(a):
    x, inv, R = make_ess(a.rate, a.dur, a.f1, a.f2)
    pre = int(0.5 * a.rate)
    post = int(1.5 * a.rate)
    sig = np.concatenate([np.zeros(pre), x * a.amp, np.zeros(post)]).astype(np.float32)

    rec = play_record(sig, a.rate, a.in_dev, a.out_dev, a.in_ch, a.out_ch)
    if np.max(np.abs(rec)) > 0.99:
        print("!! ADC CLIPPING - lower mic gain or --amp, results are invalid", file=sys.stderr)

    results = []
    for c in range(rec.shape[1]):
        r = analyse_sweep(rec[:, c], x * a.amp, inv, a.rate, a.dur, R, pre, f"mic{c}")
        results.append(r)

    np.savez_compressed(a.out + ".npz", rec=rec, x=x, fs=a.rate,
                        irs=np.stack([r.pop("_ir")[:a.rate] for r in results]))
    for r in results:
        r.pop("_ir_peak_index", None)
    print(json.dumps(results, indent=2))
    with open(a.out + ".json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved {a.out}.npz / {a.out}.json", file=sys.stderr)


def cmd_noise(a):
    rng = np.random.default_rng(0)
    n = int(a.dur * a.rate)
    x = rng.standard_normal(n).astype(np.float32)
    x /= np.max(np.abs(x))
    pre = int(0.5 * a.rate)
    sig = np.concatenate([np.zeros(pre), x * a.amp, np.zeros(int(0.5 * a.rate))]).astype(np.float32)

    rec = play_record(sig, a.rate, a.in_dev, a.out_dev, a.in_ch, a.out_ch)
    ref = sig.astype(np.float64)

    nper = 4096
    for c in range(rec.shape[1]):
        f, Cxy = coherence(ref, rec[:, c], fs=a.rate, nperseg=nper)
        bands = [(100, 300), (300, 1000), (1000, 3000), (3000, 8000)]
        print(f"mic{c}: mean magnitude-squared coherence")
        for lo, hi in bands:
            m = (f >= lo) & (f < hi)
            print(f"   {lo:5d}-{hi:5d} Hz : {Cxy[m].mean():.3f}"
                  f"   (max theoretical ERLE {-10*np.log10(max(1-Cxy[m].mean(),1e-6)):5.1f} dB)")
        fs_, P = welch(rec[:, c], fs=a.rate, nperseg=nper)
    np.savez_compressed(a.out + "_coh.npz", rec=rec, x=sig, fs=a.rate)


def cmd_silence(a):
    """Noise floor / EMI probe: record with nothing played."""
    import sounddevice as sd
    rec = sd.rec(int(a.dur * a.rate), samplerate=a.rate, channels=a.in_ch,
                 device=a.in_dev, dtype="float32", blocking=True)
    rec = np.asarray(rec, dtype=np.float64)
    for c in range(rec.shape[1]):
        f, P = welch(rec[:, c], fs=a.rate, nperseg=8192)
        P_db = 10 * np.log10(np.maximum(P, 1e-30))
        med = np.median(P_db)
        peaks = [(float(f[i]), float(P_db[i] - med))
                 for i in np.argsort(P_db)[-12:] if P_db[i] - med > 12]
        peaks.sort()
        print(f"mic{c}: broadband {20*np.log10(max(rms(rec[:,c]),1e-12)):.1f} dBFS")
        for fr, pk in peaks:
            print(f"   tone at {fr:8.1f} Hz, +{pk:.1f} dB over floor")
    np.savez_compressed(a.out + "_silence.npz", rec=rec, fs=a.rate)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--rate", type=int, default=48000)
        sp.add_argument("--in-dev", default=None)
        sp.add_argument("--out-dev", default=None)
        sp.add_argument("--in-ch", type=int, default=2)
        sp.add_argument("--out-ch", type=int, default=2)
        sp.add_argument("--dur", type=float, default=5.0)
        sp.add_argument("--amp", type=float, default=0.1,
                        help="playback amplitude 0..1; sweep the value you actually use")
        sp.add_argument("--out", default="probe")

    sp = sub.add_parser("devices"); sp.set_defaults(func=cmd_devices)
    sp = sub.add_parser("sweep"); common(sp)
    sp.add_argument("--f1", type=float, default=50.0)
    sp.add_argument("--f2", type=float, default=16000.0)
    sp.set_defaults(func=cmd_sweep)
    sp = sub.add_parser("noise"); common(sp); sp.set_defaults(func=cmd_noise)
    sp = sub.add_parser("silence"); common(sp); sp.set_defaults(func=cmd_silence)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
