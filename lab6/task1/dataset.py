from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader


HAR_LABELS = {
    0: "WALKING",
    1: "WALKING_UPSTAIRS",
    2: "WALKING_DOWNSTAIRS",
    3: "SITTING",
    4: "STANDING",
    5: "LAYING",
}

CHANNEL_FILES = [
    "total_acc_x_{split}.txt",
    "total_acc_y_{split}.txt",
    "total_acc_z_{split}.txt",
    "body_gyro_x_{split}.txt",
    "body_gyro_y_{split}.txt",
    "body_gyro_z_{split}.txt",
]


class UCIHARSignals(Dataset):
    def __init__(self, root, split="train"):
        if split not in ("train", "test"):
            raise ValueError("split must be 'train' or 'test'")

        root = Path(root)
        signal_dir = root / split / "Inertial Signals"

        channels = [
            np.loadtxt(
                signal_dir / filename.format(split=split),
                dtype=np.float32,
            )
            for filename in CHANNEL_FILES
        ]

        # Six [N, 128] arrays -> one [N, 6, 128] array.
        x = np.stack(channels, axis=1)

        # Original labels are 1–6; PyTorch labels are 0–5.
        y = np.loadtxt(
            root / split / f"y_{split}.txt",
            dtype=np.int64,
        ) - 1

        if x.shape != (len(y), 6, 128):
            raise ValueError(f"Unexpected input shape: {x.shape}")

        if not np.isin(y, list(HAR_LABELS)).all():
            raise ValueError("Unexpected labels")

        # Keep the original signal values for Task 2.
        self.x = torch.from_numpy(x)
        self.y = torch.from_numpy(y)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        x = self.x[i]
        y = int(self.y[i])
        return x, y, HAR_LABELS[y]


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent.parent / "data" / "UCI HAR Dataset"

    for split in ("train", "test"):
        dataset = UCIHARSignals(data_dir, split)
        loader = DataLoader(
            dataset,
            batch_size=32,
            shuffle=(split == "train"),
        )

        xb, yb, names = next(iter(loader))

        print(f"\nSplit: {split}")
        print("Number of samples:", len(dataset))
        print("x shape:", xb.shape)
        print("y shape:", yb.shape)
        print("Label names:", names[:3])