#!/usr/bin/env python3
"""Score existing generated-negative WAV clips against a trained model and
flag the low-scoring ones for removal.

Unlike score_negative_words.py (which generates fresh labeled per-word
probes), this operates directly on an existing clip pool -- e.g. the
generated_negatives/augmented/ directory already built by
create_negative_samples.py -- scoring each individual rendering (specific
voice + pitch-shift) rather than aggregating by word. That's finer-grained:
some renderings of a word land closer to the wake word than others, so
per-clip filtering can keep just the confusable renderings of a word while
dropping the rest, not just keep-or-drop the whole word.

Run against a model trained WITHOUT this hard-negative set (sampling_weight:
0.0 on generated_negative_features in training_parameters.yaml for that
baseline run) so scores reflect natural confusability, not whatever the
model already learned to suppress.

Usage:
    python score_negative_clips.py --config baseline.json --dir generated_negatives/augmented
    python score_negative_clips.py --config baseline.json --dir generated_negatives/augmented \\
        --threshold 0.5 --move-rejected generated_negatives/rejected
"""

import argparse
import csv
import os
import shutil

from score_negative_words import score_clip


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--config", required=True, help="Path to the model JSON manifest to score against")
    ap.add_argument("--dir", required=True, help="Directory of WAV clips to score")
    ap.add_argument("--threshold", type=float, default=0.5, help="Score below which a clip is flagged 'drop'")
    ap.add_argument("--csv", help="Optional path to write full per-clip results as CSV")
    ap.add_argument(
        "--move-rejected",
        help="If given, move low-scoring clips here instead of only reporting them (reversible; no delete)",
    )
    args = ap.parse_args()

    from pymicro_wakeword import MicroWakeWord

    mww = MicroWakeWord.from_config(args.config)
    print(f">> Model: cutoff={mww.probability_cutoff} window={mww.sliding_window_size}")

    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".wav"))
    print(f">> Scoring {len(files)} clip(s) in {args.dir} ...")

    results = []
    for i, fname in enumerate(files, 1):
        path = os.path.join(args.dir, fname)
        score = score_clip(mww, path)
        results.append((fname, score))
        if i % 200 == 0 or i == len(files):
            print(f"   {i}/{len(files)}")

    results.sort(key=lambda r: r[1], reverse=True)

    keep = [r for r in results if r[1] >= args.threshold]
    drop = [r for r in results if r[1] < args.threshold]

    print(f"\n>> {len(keep)} clip(s) >= {args.threshold} (keep), {len(drop)} below (drop).")
    if drop:
        print(">> Lowest-scoring examples:")
        for fname, score in sorted(drop, key=lambda r: r[1])[:10]:
            print(f"   {score:.3f}  {fname}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["file", "score", "verdict"])
            for fname, score in results:
                writer.writerow([fname, f"{score:.4f}", "keep" if score >= args.threshold else "drop"])
        print(f">> Wrote {args.csv}")

    if args.move_rejected:
        os.makedirs(args.move_rejected, exist_ok=True)
        for fname, _ in drop:
            shutil.move(os.path.join(args.dir, fname), os.path.join(args.move_rejected, fname))
        print(f">> Moved {len(drop)} rejected clip(s) to {args.move_rejected}/ (nothing deleted)")


if __name__ == "__main__":
    main()
