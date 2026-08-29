#!/usr/bin/env bash
# Pre-AEC variant of test_mww.py: taps the raw hardware capture node
# (before echo cancellation) instead of the post-AEC default `pipewire`
# device, so you can compare wake-word scores with/without AEC.
#
# Usage (same args as test_mww.py):
#   ./test_mww_preaec.sh --config chochko-micro.json
#   ./test_mww_preaec.sh --builtin alexa
#
# Compare against the normal post-AEC run:
#   arecord -D pipewire -r 16000 -c 1 -f S16_LE -t raw - | python3 test_mww.py --config ...
#
# Override the raw capture node if your hardware differs (check with
# `wpctl status` / `pw-link -lo` — must match the echo-cancel module's own
# capture.props.target.object in
# ~/.config/pipewire/pipewire.conf.d/90-echo-cancel.conf):
#   RAW_CAPTURE_NODE=alsa_input.some-other-node ./test_mww_preaec.sh --config ...
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW_CAPTURE_NODE="${RAW_CAPTURE_NODE:-alsa_input.platform-soc_sound.stereo-fallback}"

echo ">> Capturing PRE-AEC audio from: $RAW_CAPTURE_NODE" >&2
echo ">> Ctrl-C to stop, same as test_mww.py normally." >&2

# pw-record picks its output container from the target filename's extension;
# "-" has none, so it falls back to headerless raw PCM on stdout rather than
# a WAV stream (confirmed: piping it into `sox -t wav -` failed with "RIFF
# header not found"). That means no conversion step is needed at all here —
# just force a known sample format (s16, matching test_mww.py's expectation)
# and feed it straight through.
pw-record --target="$RAW_CAPTURE_NODE" --channels=1 --rate=16000 --format=s16 - \
  | python3 "$HERE/test_mww.py" "$@"
