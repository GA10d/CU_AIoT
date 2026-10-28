"""UCI HAR raw inertial signals as a PyTorch Dataset (Task 1 layout, reused by Task 5)."""
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader

HAR_LABELS = {1: "WALKING", 2: "WALKING_UPSTAIRS", 3: "WALKING_DOWNSTAIRS",
              4: "SITTING", 5: "STANDING", 6: "LAYING"}
LABEL_NAMES = [HAR_LABELS[i] for i in range(1, 7)]

ACC_CHANNELS = [
    "total_acc_x_{split}.txt",
    "total_acc_y_{split}.txt",
    "total_acc_z_{split}.txt",
]
GYRO_CHANNELS = [
    "body_gyro_x_{split}.txt",
    "body_gyro_y_{split}.txt",
    "body_gyro_z_{split}.txt",
]
# "acc" matches the ESP32 (ADXL345 has no gyroscope); "all" is the 6-channel Task 1 input.
CHANNEL_SETS = {"acc": ACC_CHANNELS, "all": ACC_CHANNELS + GYRO_CHANNELS}

SAMPLING_RATE = 50


class UCIHARSignals(Dataset):
    """
    Returns for __getitem__(i):
        x: torch.FloatTensor with shape [C, L]   (channels-first for Conv1d)
        y: int in [0..5]
        y_name: str (human-readable)
    """

    def __init__(self, root, split="train", channels="all"):
        if split not in ("train", "test"):
            raise ValueError("split must be 'train' or 'test'")
        base = Path(root) / split / "Inertial Signals"
        # raw g / rad/s, no normalization (keep physical units for Tasks 2-5)
        x = np.stack([np.loadtxt(base / name.format(split=split), dtype=np.float32)
                      for name in CHANNEL_SETS[channels]], axis=1)  # [N, C, L]
        self.x = torch.from_numpy(x)
        labels = np.loadtxt(Path(root) / split / "y_{}.txt".format(split), dtype=np.int64)
        self.y = torch.from_numpy(labels - 1)  # 1..6 -> 0..5

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        y = int(self.y[i])
        return self.x[i], y, LABEL_NAMES[y]


def few_shot_indices(labels, per_class, seed=0):
    """Pick `per_class` random sample indices for each of the 6 classes."""
    rng = np.random.default_rng(seed)
    labels = np.asarray(labels)
    picked = [rng.choice(np.flatnonzero(labels == c), per_class, replace=False)
              for c in range(len(LABEL_NAMES))]
    return np.concatenate(picked)


if __name__ == "__main__":
    import sys

    data_dir = sys.argv[1] if len(sys.argv) > 1 else "UCI HAR Dataset"
    train_loader = DataLoader(UCIHARSignals(data_dir, "train"), batch_size=32, shuffle=True)
    xb, yb, yname = next(iter(train_loader))
    print("x:", xb.shape)  # [B, C, L], e.g. [32, 6, 128]
    print("y:", yb.shape)  # [B]
    print("names:", yname[:3])
