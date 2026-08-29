#!/usr/bin/env bash
# Phase 3 for microWakeWord: build features, train, quantize,
# and convert to a streaming tflite model.
#
# Runs on CPU. Prints validation metrics every 500 steps.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">> [1/2] Verifying training_parameters.yaml and resetting previous checkpoints..."
if [ ! -f "training_parameters.yaml" ]; then
    echo ">> ERROR: training_parameters.yaml not found in current directory!" >&2
    exit 1
fi

# Clean old model weights to ensure training starts fresh
rm -rf trained_models/

echo ">> [2/2] Training microWakeWord model..."
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-1}"

python -m microwakeword.model_train_eval \
  --training_config='training_parameters.yaml' \
  --train 1 \
  --restore_checkpoint 1 \
  --test_tf_nonstreaming 0 \
  --test_tflite_nonstreaming 0 \
  --test_tflite_nonstreaming_quantized 0 \
  --test_tflite_streaming 0 \
  --test_tflite_streaming_quantized 1 \
  --use_weights "best_weights" \
  mixednet \
  --pointwise_filters "64,64,64,64" \
  --repeat_in_block "1, 1, 1, 1" \
  --mixconv_kernel_sizes '[5], [11], [15], [23]' \
  --residual_connection "0,0,0,0" \
  --first_conv_filters 32 \
  --first_conv_kernel_size 5 \
  --stride 3

TFLITE="trained_models/wakeword/tflite_stream_state_internal_quant/stream_state_internal_quant.tflite"
if [ -f "$TFLITE" ]; then
  echo ""
  echo ">> SUCCESS. Model written to:"
  echo "   $(pwd)/$TFLITE"
  ls -la "$TFLITE"
else
  echo ""
  echo ">> Training finished but the expected tflite was NOT found at:" >&2
  echo "   $TFLITE" >&2
  echo "   Scroll up for the conversion error." >&2
  exit 1
fi