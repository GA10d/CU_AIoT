import json, time
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA = Path(__file__).with_name("data.jsonl")


@app.get("/")
def index():
    return "lab6 server ok"


@app.post("/upload")
def upload():
    body = request.get_json(force=True)
    acc = body.get("acc")
    if not (isinstance(acc, list) and len(acc) == 3 and all(len(c) == 128 for c in acc)):
        return jsonify(error="acc must be [3][128]"), 400
    rec = {"ts": time.time(), "device": body.get("device", "esp32"),
           "label": body.get("label"), "fs": body.get("fs", 50), "acc": acc}
    with DATA.open("a") as f:
        f.write(json.dumps(rec) + "\n")
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
