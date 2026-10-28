"""Task 5.2: few-shot linear probe on frozen NormWear embeddings.

1. Encode K windows per class from the UCI HAR train set and the full test set with
   NormWearModel.get_embedding -> [B, C, P, 768], averaged over patches and channels.
2. Train one nn.Linear(768, 6) with cross-entropy (encoder stays frozen).
3. Report test accuracy before (untrained head, plus the 5.1 zero-shot result) and after.

Test-set embeddings are cached in results/, so re-running with a different K or
seed only re-encodes the few training windows.

Usage:
    python linear_probe.py                # 10 shots per class, 3 accelerometer channels
    python linear_probe.py --shots 5
"""
import argparse
import json
import time

import torch
import torch.nn.functional as F

from normwear_utils import DATA_DIR, HEAD_CKPT, RESULTS_DIR, LinearHead, embed_all, load_encoder
from uci_har import LABEL_NAMES, UCIHARSignals, few_shot_indices


def accuracy(head, z, y):
    with torch.no_grad():
        return float((head(z).argmax(dim=1) == y).float().mean())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", choices=["acc", "all"], default="acc",
                        help="use 'acc' if the head will serve ESP32 data (no gyroscope)")
    parser.add_argument("--shots", type=int, default=10, help="training windows per class")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    encoder = load_encoder()
    start = time.perf_counter()

    train = UCIHARSignals(DATA_DIR, "train", channels=args.channels)
    idx = few_shot_indices(train.y.numpy(), args.shots, seed=args.seed)
    print("Encoding {} train windows ({} per class)...".format(len(idx), args.shots))
    z_train, y_train = embed_all(encoder, train.x[idx]), train.y[idx]

    test_cache = RESULTS_DIR / "test_embeddings_{}.pt".format(args.channels)
    if test_cache.exists():
        cached = torch.load(test_cache)
        z_test, y_test = cached["z"], cached["y"]
        print("Loaded cached test embeddings from", test_cache)
    else:
        test = UCIHARSignals(DATA_DIR, "test", channels=args.channels)
        print("Encoding {} test windows...".format(len(test)))
        z_test, y_test = embed_all(encoder, test.x), test.y
        torch.save({"z": z_test, "y": y_test}, test_cache)
    embed_seconds = time.perf_counter() - start
    print("Embeddings: train {}, test {} ({:.1f} s)".format(tuple(z_train.shape), tuple(z_test.shape), embed_seconds))

    head = LinearHead()
    before = accuracy(head, z_test, y_test)
    optimizer = torch.optim.Adam(head.parameters(), lr=args.lr)
    for epoch in range(1, args.epochs + 1):
        head.train()
        loss = F.cross_entropy(head(z_train), y_train)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        if epoch % 20 == 0 or epoch == 1:
            print("epoch {:3d}  loss {:.4f}  train acc {:.2%}".format(
                epoch, loss.item(), accuracy(head, z_train, y_train)))
    head.eval()
    after = accuracy(head, z_test, y_test)

    zero_shot_file = RESULTS_DIR / "zero_shot_{}.json".format(args.channels)
    zero_shot = json.loads(zero_shot_file.read_text())["accuracy"] if zero_shot_file.exists() else None

    print("\nTest accuracy ({} windows):".format(len(y_test)))
    if zero_shot is not None:
        print("  zero-shot (5.1):        {:.2%}".format(zero_shot))
    print("  untrained linear head:  {:.2%}".format(before))
    print("  after {}-shot training: {:.2%}".format(args.shots, after))

    torch.save({"state_dict": head.state_dict(), "channels": args.channels,
                "labels": LABEL_NAMES, "shots": args.shots}, HEAD_CKPT)
    (RESULTS_DIR / "linear_probe_{}.json".format(args.channels)).write_text(json.dumps({
        "zero_shot_accuracy": zero_shot, "untrained_head_accuracy": before,
        "trained_head_accuracy": after, "shots_per_class": args.shots,
        "epochs": args.epochs, "lr": args.lr, "seed": args.seed,
        "channels": args.channels, "embedding_seconds": embed_seconds,
    }, indent=2))
    print("Saved head to", HEAD_CKPT)


if __name__ == "__main__":
    main()
