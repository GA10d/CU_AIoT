"""Task 3 PC interface: ESP32 capture -> Gemini -> OLED -> experiment files."""
import argparse
import csv
import json
import math
import os
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

LABELS = ("WALKING", "WALKING_UPSTAIRS", "WALKING_DOWNSTAIRS",
          "SITTING", "STANDING", "LAYING")
CHANNELS = ("total_acc_x", "total_acc_y", "total_acc_z")
DEFAULT_RESULTS = Path(__file__).resolve().parent / "results"
HELP = """Commands:
  capture [TRUE_LABEL]       Record and save one window without calling Gemini
  classify_HAR [TRUE_LABEL]  Record, classify, save, and display on OLED
  summary                   Export summary.json and summary.csv
  {\"name\":\"display_text\",\"args\":[\"Hello\"]}  Existing Lab 5 JSON commands
  help / q
Labels: WALKING, WALKING_UPSTAIRS, WALKING_DOWNSTAIRS, SITTING, STANDING, LAYING
Start moving before the countdown ends; keep the sensor at the declared location.
"""


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def send_command(command, host, port=8080):
    if not host:
        raise ValueError("Specify --host with the ESP32 IP printed at startup")
    payload = (json.dumps(command) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=10) as conn:
        conn.settimeout(30)
        conn.sendall(payload)
        reply = bytearray()
        while b"\n" not in reply:
            chunk = conn.recv(4096)
            if not chunk:
                raise RuntimeError("ESP32 closed the connection before a full JSON line")
            reply.extend(chunk)
            if len(reply) > 131072:
                raise RuntimeError("ESP32 reply exceeds 128 KiB")
    response = json.loads(reply.split(b"\n", 1)[0])
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise RuntimeError("ESP32 error: " + str(response.get("message", response)
                           if isinstance(response, dict) else response))
    return response


def validate_window(window):
    if not isinstance(window, dict):
        raise ValueError("Sensor window must be a JSON object")
    if (window.get("units") != "g" or window.get("sampling_rate_hz") != 50
            or window.get("num_samples") != 128
            or window.get("channels") != list(CHANNELS)):
        raise ValueError("Expected 50 Hz, 128 points, XYZ total acceleration in g")
    data = window.get("data")
    if not isinstance(data, list) or len(data) != 3:
        raise ValueError("Expected data shape [3,128]")
    for channel in data:
        if not isinstance(channel, list) or len(channel) != 128:
            raise ValueError("Each acceleration channel must contain 128 points")
        if any(isinstance(v, bool) or not isinstance(v, (float, int))
               or not math.isfinite(v) for v in channel):
            raise ValueError("Acceleration values must be finite numbers")
    timestamps = window.get("timestamps_us")
    if not isinstance(timestamps, list) or len(timestamps) != 128:
        raise ValueError("Missing 128 observed sample timestamps")
    if any(isinstance(t, bool) or not isinstance(t, (int, float))
           or not math.isfinite(t) for t in timestamps):
        raise ValueError("Invalid sample timestamps")
    gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
    if min(gaps) <= 0:
        raise ValueError("Sample timestamps must be strictly increasing")
    effective_rate = 127000000 / (timestamps[-1] - timestamps[0])
    if not 45 <= effective_rate <= 55 or max(gaps) > 35000 or window.get("overruns", 0):
        raise ValueError("Sampling timing failed QA; saved raw data, please recapture")
    return {"effective_rate_hz": round(effective_rate, 3),
            "max_gap_ms": max(gaps) / 1000,
            "mean_vector_magnitude_g": sum(
                math.sqrt(sum(data[a][i] ** 2 for a in range(3)))
                for i in range(128)) / 128}


def make_prompt(window, style, location, setting):
    validate_window(window)
    if style not in ("cot", "direct"):
        raise ValueError("style must be cot or direct")
    if not location or not location.strip():
        raise ValueError("Specify the actual attached location with --location")
    sensor_data = {name: [round(float(v), 4) for v in window["data"][i]]
                   for i, name in enumerate(CHANNELS)}
    # Same structure, activity options, precision, and response instructions as Task 2.
    common = (
        "Identify the human activity from this sensor window.\n"
        "Device: ESP32 + ADXL345\n"
        f"Attached location: {location}\n"
        f"Setting: {setting}\n"
        "Sampling rate: 50 Hz\n"
        "Window length: 128 samples, approximately 2.56 seconds\n"
        "Accelerometer: total acceleration including gravity, in g\n"
        "Gyroscope: Not available; only three accelerometer channels are supplied\n"
        f"Candidate activities: {', '.join(LABELS)}\n"
        "Each array below contains one channel in time order.\n"
        f"Sensor data: {json.dumps(sensor_data)}\n\n"
    )
    if style == "cot":
        return common + (
            "Explain your reasoning step by step, then give the activity. "
            "Choose exactly one candidate activity. "
            "End with a line in this exact format:\nFINAL_LABEL: <ACTIVITY>"
        )
    return common + (
        "Give only the activity label. "
        "Return exactly one candidate activity name, without explanation."
    )


def extract_label(text, style):
    text = text.strip().upper()
    if style == "direct":
        label = text.strip("`* \n\r\t.")
        return label if label in LABELS else None
    options = "|".join(sorted(LABELS, key=len, reverse=True))
    # Require the entire final line to match, avoiding partial activity names.
    matches = re.findall(rf"^\s*FINAL_LABEL:\s*({options})\s*$", text, re.MULTILINE)
    return matches[-1] if matches else None


def query_gemini(prompt, model):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set the GEMINI_API_KEY environment variable first")
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("Install PC requirements: python -m pip install -r requirements.txt") from exc
    client = genai.Client(api_key=api_key, http_options={"timeout": 120000})
    try:
        response = client.models.generate_content(
            model=model, contents=prompt, config={"temperature": 0})
        return response.text or ""
    finally:
        client.close()


def oled_text(label):
    return "HAR prediction\n" + (label.replace("_", "\n") if label else "Invalid output")


def run_job(args, command, true_label=None):
    if true_label is not None and true_label not in LABELS:
        raise ValueError("TRUE_LABEL must be one of: " + ", ".join(LABELS))
    if not args.location:
        raise ValueError("Specify actual sensor placement using --location")
    sample_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ_") + uuid.uuid4().hex[:6]
    output_dir = args.results / "samples" / sample_id
    output_dir.mkdir(parents=True)
    result = {"sample_id": sample_id, "true_label": true_label,
              "style": args.style if command == "classify_HAR" else None,
              "model": args.model if command == "classify_HAR" else None,
              "location": args.location, "setting": args.setting,
              "source_window": str(args.window.resolve()) if args.window else None,
              "prediction": None, "correct": None, "display_ok": False}
    write_json(output_dir / "metadata.json", result)
    print("Saving to:", output_dir)
    try:
        if args.window:
            window = json.loads(args.window.read_text(encoding="utf-8"))
        else:
            print("Prepare activity:", true_label or "unlabelled")
            for remaining in range(args.countdown, 0, -1):
                print("Recording in", remaining, flush=True)
                time.sleep(1)
            print("Recording now; continue your activity...", flush=True)
            window = send_command({"name": "capture_HAR", "args": []},
                                  args.host, args.port)["data"]
        # Save physical measurements before validation or any API request.
        write_json(output_dir / "window.json", window)
        quality = validate_window(window)
        write_json(output_dir / "quality.json", quality)
        print("Sampling QA:", json.dumps(quality))
        if command == "capture":
            result["status"] = "captured"
        else:
            prompt = make_prompt(window, args.style, args.location, args.setting)
            (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            started = time.perf_counter()
            raw_output = query_gemini(prompt, args.model)
            result["latency_seconds"] = round(time.perf_counter() - started, 3)
            (output_dir / "response.txt").write_text(raw_output, encoding="utf-8")
            label = extract_label(raw_output, args.style)
            result.update(prediction=label, correct=(label == true_label) if true_label else None,
                          status="classified" if label else "invalid_output")
            print("Gemini output:\n" + raw_output)
            print("Prediction:", label, "| True label:", true_label)
            # Persist the classification even if the OLED or Wi-Fi fails afterwards.
            write_json(output_dir / "result.json", result)
            try:
                send_command({"name": "screen_on", "args": []}, args.host, args.port)
                send_command({"name": "display_text", "args": [oled_text(label)]},
                             args.host, args.port)
                result["display_ok"] = True
            except (OSError, RuntimeError, ValueError) as exc:
                result["display_error"] = str(exc)
                print("Classification saved, but OLED update failed:", exc)
    except Exception as exc:
        result.update(status="error", error=str(exc))
        write_json(output_dir / "result.json", result)
        raise
    write_json(output_dir / "result.json", result)
    return output_dir


def summarize(results_dir):
    rows = [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((results_dir / "samples").glob("*/result.json"))]
    classified = [row for row in rows if row["status"] in ("classified", "invalid_output")]
    summary = {"total_records": len(rows), "classification_records": len(classified), "by_style": {}}
    for style in ("direct", "cot"):
        labelled = [r for r in classified if r["style"] == style and r.get("true_label") in LABELS]
        counts = {label: sum(r["true_label"] == label for r in labelled) for label in LABELS}
        summary["by_style"][style] = {
            "labelled_count": len(labelled),
            "correct": sum(r["correct"] is True for r in labelled),
            "accuracy": sum(r["correct"] is True for r in labelled) / len(labelled) if labelled else None,
            "invalid_outputs": sum(r["prediction"] is None for r in labelled),
            "coverage": counts,
            "at_least_10_and_all_6_classes": len(labelled) >= 10 and all(counts.values()),
        }
    results_dir.mkdir(parents=True, exist_ok=True)
    fields = ["sample_id", "true_label", "prediction", "correct", "style", "model",
              "status", "display_ok", "location", "source_window", "latency_seconds", "error"]
    with (results_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    write_json(results_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    print("Exported:", results_dir / "summary.csv")
    return summary


def interactive(args):
    print(HELP)
    while True:
        try:
            text = input("HAR> ").strip()
            if not text:
                continue
            if text.lower() in ("q", "quit", "exit"):
                return
            if text.lower() == "help":
                print(HELP)
            elif text.lower() == "summary":
                summarize(args.results)
            elif text.startswith("{"):
                print(json.dumps(send_command(json.loads(text), args.host, args.port), indent=2))
            else:
                parts = text.split()
                if parts[0] not in ("capture", "classify_HAR") or len(parts) > 2:
                    raise ValueError("Use capture [LABEL], classify_HAR [LABEL], summary, or help")
                truth = parts[1].upper() if len(parts) == 2 else None
                run_job(args, parts[0], truth)
        except (EOFError, KeyboardInterrupt):
            print("\nClient exited.")
            return
        except Exception as exc:
            print("Error:", exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="interactive",
                        choices=("interactive", "capture", "classify_HAR", "summary"))
    parser.add_argument("--host", help="ESP32 IPv4 address")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--location", help="Actual fixed attached location, e.g. Waist")
    parser.add_argument("--setting", default="Real-world activity recording in our environment")
    parser.add_argument("--style", choices=("direct", "cot"), default="direct")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    parser.add_argument("--true-label", choices=LABELS)
    parser.add_argument("--countdown", type=int, default=3)
    parser.add_argument("--window", type=Path, help="Replay a previously saved window.json")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    if args.countdown < 0:
        parser.error("--countdown must be nonnegative")
    if args.command == "summary":
        summarize(args.results)
    else:
        if not args.location:
            parser.error("--location is required; supply the actual sensor placement")
        if not args.host and not (args.window and args.command == "capture"):
            parser.error("--host is required for ESP32 communication and OLED display")
        if args.command == "interactive":
            interactive(args)
        else:
            try:
                run_job(args, args.command, args.true_label)
            except Exception as exc:
                parser.exit(1, "Task 3 failed: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
