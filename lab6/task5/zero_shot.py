"""Task 5.1: zero-shot NormWear on the full UCI HAR test set.

NormWear's zero-shot path takes (1) a question describing the task, (2) one answer
sentence per class, and (3) the raw signal window. The text goes through its
TinyLlama text encoder; the signal goes through the NormWear encoder + MSiTF fusion
(signal_encode); the prediction is the closest answer embedding.

Usage:
    python zero_shot.py                 # 3 accelerometer channels (same as the ESP32)
    python zero_shot.py --channels all  # 6 channels: total_acc xyz + body_gyro xyz
"""
import argparse
import json
import time

import numpy as np
import torch

from normwear_utils import DATA_DIR, DEVICE, ENCODER_CKPT, MSITF_CKPT, RESULTS_DIR
from uci_har import LABEL_NAMES, SAMPLING_RATE, UCIHARSignals

# Same question/answers NormWear's own sentence_template.py uses for uci_har.
QUESTION = "What is the current activity?"
OPTIONS = [
    "The person is walking.",
    "The person is walking upstairs.",
    "The person is walking downstairs.",
    "The person is sitting.",
    "The person is standing.",
    "The person is laying.",
]


def load_zero_shot_model():
    from NormWear.zero_shot.msitf_fusion import NormWearZeroShot

    model = NormWearZeroShot(weight_path=str(ENCODER_CKPT), msitf_ckpt=str(MSITF_CKPT))
    # NormWearZeroShot builds its encoder with the SciPy CWT; switch to the PyTorch wavelet.
    model.sensor_model.optimized_cwt = True
    return model.to(DEVICE).eval()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", choices=["acc", "all"], default="acc")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0, help="only use the first N test windows (quick check)")
    args = parser.parse_args()

    test = UCIHARSignals(DATA_DIR, "test", channels=args.channels)
    x, y = test.x, test.y.numpy()
    if args.limit:
        x, y = x[:args.limit], y[:args.limit]
    print("Test windows: {}, input shape per window: {}".format(len(x), tuple(x.shape[1:])))

    model = load_zero_shot_model()
    start = time.perf_counter()
    with torch.no_grad():
        txt = model.txt_encode([QUESTION] + OPTIONS)  # [7, 2048]
        query, option_embed = txt[:1], txt[1:]

        preds = []
        n_batches = (len(x) + args.batch_size - 1) // args.batch_size
        for b, s in enumerate(range(0, len(x), args.batch_size)):
            batch = x[s:s + args.batch_size].to(DEVICE)
            signal_embed = model.signal_encode(batch, query, sampling_rate=SAMPLING_RATE)
            preds.append(model.inference(signal_embed, option_embed).argmax(dim=1).cpu())
            if (b + 1) % 5 == 0 or b + 1 == n_batches:
                print("  batch {}/{}".format(b + 1, n_batches), flush=True)
    elapsed = time.perf_counter() - start

    preds = torch.cat(preds).numpy()
    acc = float((preds == y).mean())
    counts = np.bincount(preds, minlength=len(LABEL_NAMES))
    print("\nZero-shot accuracy: {:.2%} ({} windows, {} channels)".format(acc, len(y), x.shape[1]))
    print("Inference time: {:.1f} s on {}".format(elapsed, DEVICE))
    print("Prediction counts:", dict(zip(LABEL_NAMES, counts.tolist())))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "zero_shot_{}.json".format(args.channels)
    out.write_text(json.dumps({
        "accuracy": acc, "n": int(len(y)), "channels": args.channels,
        "seconds": elapsed, "device": str(DEVICE),
        "question": QUESTION, "options": OPTIONS,
        "pred_counts": dict(zip(LABEL_NAMES, counts.tolist())),
    }, indent=2))
    print("Saved", out)


if __name__ == "__main__":
    main()
