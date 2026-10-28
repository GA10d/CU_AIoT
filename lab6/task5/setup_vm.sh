#!/usr/bin/env bash
# One-time setup for Task 5 on the GCP VM (Ubuntu 22.04, CPU).
# Run from this folder:  bash setup_vm.sh
# Creates: venv/, NormWear/, ckpt/, "UCI HAR Dataset"/
set -euo pipefail
cd "$(dirname "$0")"

RELEASE=https://github.com/Mobile-Sensing-and-UbiComp-Laboratory/NormWear/releases/download/v1.0.0-alpha
UCI_URL="https://archive.ics.uci.edu/static/public/240/human+activity+recognition+using+smartphones.zip"

sudo apt-get install -y unzip git python3-venv >/dev/null

# --- Python env (CPU-only PyTorch; the conda pytorch channel in config_env.sh is discontinued) ---
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -q transformers timm scipy scikit-learn pandas tqdm flask

# --- NormWear code + checkpoints ---
if [ ! -d NormWear ]; then
    git clone --depth 1 https://github.com/Mobile-Sensing-and-UbiComp-Laboratory/NormWear.git
fi
mkdir -p ckpt
for f in normwear_pretrain_ckpt.pth normwear_msitf_zeroshot_last_checkpoint-5.pth; do
    [ -f "ckpt/$f" ] || curl -L --fail -o "ckpt/$f" "$RELEASE/$f"
done

# --- UCI HAR dataset (the outer zip wraps "UCI HAR Dataset.zip") ---
if [ ! -d "UCI HAR Dataset" ]; then
    curl -L --fail -o uci_har.zip "$UCI_URL"
    unzip -q -o uci_har.zip -d uci_tmp
    if [ -f "uci_tmp/UCI HAR Dataset.zip" ]; then
        unzip -q -o "uci_tmp/UCI HAR Dataset.zip" -d .
    else
        mv "uci_tmp/UCI HAR Dataset" .
    fi
    rm -rf uci_tmp uci_har.zip __MACOSX
fi

python uci_har.py "UCI HAR Dataset"
echo "[OK] Setup done. Next: python zero_shot.py && python linear_probe.py && python app.py"
