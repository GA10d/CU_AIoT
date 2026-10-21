#!/usr/bin/env bash
# One-click launcher for Lab 5 Checkpoint 1 (Gradio voice assistant).
# Usage: ./run.sh            (or: bash run.sh)
set -euo pipefail

ENV_NAME="aiot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Locate conda (works even if the shell hasn't run `conda init`).
if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base)"
else
    for candidate in /opt/anaconda3 "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" /opt/homebrew/Caskroom/miniconda/base; do
        if [ -x "$candidate/bin/conda" ]; then
            CONDA_BASE="$candidate"
            break
        fi
    done
fi
if [ -z "${CONDA_BASE:-}" ]; then
    echo "[ERROR] conda not found. Install Anaconda/Miniconda first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "[ERROR] conda env '$ENV_NAME' not found. Create it with:" >&2
    echo "    conda create -n $ENV_NAME python=3.11 -y && conda activate $ENV_NAME && pip install gradio openai-whisper" >&2
    exit 1
fi

conda activate "$ENV_NAME"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[WARN] ffmpeg not found in PATH; whisper needs it to transcribe audio." >&2
    echo "       Install with: conda install -n $ENV_NAME -c conda-forge ffmpeg -y   (or: brew install ffmpeg)" >&2
fi

echo "[INFO] Starting Lab 5 Checkpoint 1 in conda env '$ENV_NAME' ..."
exec python -u web_app.py "$@"
