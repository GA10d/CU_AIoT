"""Shared paths and NormWear helpers for Task 5.1-5.3.

Expected layout next to this file (setup_vm.sh creates it):
    NormWear/                 cloned repo (imported as the `NormWear` package)
    ckpt/normwear_pretrain_ckpt.pth
    ckpt/normwear_msitf_zeroshot_last_checkpoint-5.pth
    UCI HAR Dataset/
Each path can be overridden with an environment variable of the same name.
"""
import os
import sys
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
NORMWEAR_PARENT = Path(os.environ.get("NORMWEAR_PARENT", HERE))
CKPT_DIR = Path(os.environ.get("CKPT_DIR", HERE / "ckpt"))
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE / "UCI HAR Dataset"))
RESULTS_DIR = Path(os.environ.get("RESULTS_DIR", HERE / "results"))

ENCODER_CKPT = CKPT_DIR / "normwear_pretrain_ckpt.pth"
MSITF_CKPT = CKPT_DIR / "normwear_msitf_zeroshot_last_checkpoint-5.pth"
HEAD_CKPT = RESULTS_DIR / "linear_head.pt"

if str(NORMWEAR_PARENT) not in sys.path:
    sys.path.insert(0, str(NORMWEAR_PARENT))

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
EMBED_DIM = 768


def load_encoder():
    """Frozen NormWear encoder using the PyTorch wavelet (scipy.signal.cwt is gone in new SciPy)."""
    from NormWear.main_model import NormWearModel

    model = NormWearModel(weight_path=str(ENCODER_CKPT), optimized_cwt=True).to(DEVICE)
    model.eval()
    for p in model.parameters():
        p.requires_grad = False
    return model


@torch.no_grad()
def embed(encoder, x, sampling_rate=50):
    """[B, C, L] raw windows -> [B, 768]: mean over patches and channels."""
    out = encoder.get_embedding(x.float().cpu(), sampling_rate=sampling_rate, device=DEVICE)  # [B, C, P, 768]
    return out.mean(dim=(1, 2)).cpu()


@torch.no_grad()
def embed_all(encoder, x, batch_size=64, log_every=10):
    chunks = []
    n_batches = (len(x) + batch_size - 1) // batch_size
    for b, start in enumerate(range(0, len(x), batch_size)):
        chunks.append(embed(encoder, x[start:start + batch_size]))
        if (b + 1) % log_every == 0 or b + 1 == n_batches:
            print("  embedded batch {}/{}".format(b + 1, n_batches), flush=True)
    return torch.cat(chunks)


class LinearHead(torch.nn.Module):
    """One fully connected layer: 768-d NormWear embedding -> 6 activity logits."""

    def __init__(self, in_features=EMBED_DIM, num_classes=6):
        super().__init__()
        self.fc = torch.nn.Linear(in_features, num_classes)

    def forward(self, z):
        return self.fc(z)
