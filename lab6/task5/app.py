"""Lab 6 cloud server: Checkpoint 3 storage + Checkpoint 4 NormWear inference.

POST /upload    store an ESP32 window in data.jsonl
GET  /samples   last 10 stored windows
POST /classify  NormWear embedding -> linear head -> activity label (also logged)

Run on the VM (inside screen):  python app.py
"""
import json
import threading
import time

import torch
from flask import Flask, jsonify, request

from normwear_utils import HEAD_CKPT, HERE, LinearHead, embed, load_encoder

app = Flask(__name__)
DATA = HERE / "data.jsonl"
PREDICTIONS = HERE / "predictions.jsonl"

SHORT_NAMES = {"WALKING_UPSTAIRS": "UPSTAIRS", "WALKING_DOWNSTAIRS": "DOWNSTAIRS"}

# Loaded once at startup; the lock keeps Flask's worker threads off the model at the same time.
print("Loading NormWear encoder and linear head...")
ENCODER = load_encoder()
_head_ckpt = torch.load(HEAD_CKPT)
HEAD = LinearHead()
HEAD.load_state_dict(_head_ckpt["state_dict"])
HEAD.eval()
LABELS = _head_ckpt["labels"]
MODEL_LOCK = threading.Lock()
print("Ready (head trained on '{}' channels, {} shots/class)".format(_head_ckpt["channels"], _head_ckpt["shots"]))


def read_window(body):
    acc = body.get("acc")
    if not (isinstance(acc, list) and len(acc) == 3 and all(len(c) == 128 for c in acc)):
        return None
    return acc


def append_jsonl(path, record):
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


@app.get("/")
def index():
    return "lab6 server ok"


@app.post("/upload")
def upload():
    body = request.get_json(force=True)
    acc = read_window(body)
    if acc is None:
        return jsonify(error="acc must be [3][128]"), 400
    append_jsonl(DATA, {"ts": time.time(), "device": body.get("device", "esp32"),
                        "label": body.get("label"), "fs": body.get("fs", 50), "acc": acc})
    return jsonify(ok=True)


@app.get("/samples")
def samples():
    if not DATA.exists():
        return jsonify([])
    out = []
    for line in DATA.read_text().splitlines()[-10:]:
        r = json.loads(line)
        out.append({"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                    "device": r["device"], "label": r["label"],
                    "shape": [len(r["acc"]), len(r["acc"][0])],
                    "first_xyz": [c[0] for c in r["acc"]]})
    return jsonify(out)


@app.post("/classify")
def classify():
    body = request.get_json(force=True)
    acc = read_window(body)
    if acc is None:
        return jsonify(error="acc must be [3][128]"), 400

    start = time.perf_counter()
    x = torch.tensor(acc, dtype=torch.float32).unsqueeze(0)  # [1, 3, 128]
    with MODEL_LOCK, torch.no_grad():
        z = embed(ENCODER, x, sampling_rate=body.get("fs", 50))  # [1, 768]
        probs = torch.softmax(HEAD(z), dim=1)[0]
    pred = int(probs.argmax())
    label = LABELS[pred]
    ms = round((time.perf_counter() - start) * 1000)

    result = {"label": label, "short": SHORT_NAMES.get(label, label),
              "confidence": round(float(probs[pred]), 3),
              "probs": {name: round(float(p), 3) for name, p in zip(LABELS, probs)},
              "inference_ms": ms}
    append_jsonl(PREDICTIONS, {"ts": time.time(), "device": body.get("device", "esp32"),
                               "true_label": body.get("label"), "acc": acc, **result})
    print("classify: true={} pred={} ({:.0%}) in {} ms".format(
        body.get("label"), label, result["confidence"], ms), flush=True)
    return jsonify(result)


@app.get("/predictions")
def predictions():
    if not PREDICTIONS.exists():
        return jsonify([])
    out = []
    for line in PREDICTIONS.read_text().splitlines()[-10:]:
        r = json.loads(line)
        out.append({"time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                    "true_label": r["true_label"], "pred": r["label"],
                    "confidence": r["confidence"], "inference_ms": r["inference_ms"]})
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
