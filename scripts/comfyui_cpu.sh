#!/usr/bin/env bash
# CPU-first ComfyUI launcher for a weak laptop (Intel i5, NO GPU, 12GB RAM, Ubuntu).
#
# Goals: never touch a GPU code path, keep RAM under control, free models between
# runs (12GB is tight), and don't oversubscribe the CPU. Pair with the LCM graph
# in data/comfy/cpu_lcm_txt2img.json (8-step generation) so a 512x768 still takes
# ~35-60s instead of 3-5 min. ShortsFactory talks to it at COMFYUI_BASE_URL.
#
#   COMFYUI_DIR=~/ComfyUI ./scripts/comfyui_cpu.sh
set -euo pipefail

# Physical cores only (i5 is usually 4). Oversubscribing threads SLOWS CPU SD.
CORES="$(nproc)"
THREADS=$(( CORES > 4 ? 4 : CORES ))
export OMP_NUM_THREADS="$THREADS"
export MKL_NUM_THREADS="$THREADS"
export OPENBLAS_NUM_THREADS="$THREADS"
# Keep PyTorch from grabbing all RAM for caching allocator arenas.
export PYTORCH_NO_CUDA_MEMORY_CACHING=1

COMFYUI_DIR="${COMFYUI_DIR:-$HOME/ComfyUI}"
cd "$COMFYUI_DIR"

# --cpu                    : force the CPU backend (no CUDA probing)
# --cpu-vae                : decode the VAE on CPU too (consistent, no surprises)
# --use-split-cross-attention : lowest-RAM attention path
# --disable-smart-memory   : release model weights between prompts (frees ~4-6GB)
# --preview-method none    : skip live previews (saves CPU + RAM)
# --dont-print-server      : quieter logs
exec python main.py \
  --cpu \
  --cpu-vae \
  --use-split-cross-attention \
  --disable-smart-memory \
  --preview-method none \
  --port "${COMFYUI_PORT:-8188}"
