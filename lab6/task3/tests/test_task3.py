"""Offline contract tests; these do not establish that physical hardware works."""
import argparse
import copy
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import client


def sample_window():
    return {"sampling_rate_hz": 50, "num_samples": 128, "units": "g",
            "channels": list(client.CHANNELS),
            "data": [[0.0] * 128, [0.0] * 128, [1.0] * 128],
            "timestamps_us": [i * 20000 for i in range(128)], "overruns": 0}


class Task3Tests(unittest.TestCase):
    def test_prompt_uses_only_real_acceleration_channels(self):
        prompt = client.make_prompt(sample_window(), "direct", "Waist", "Lab")
        sensor_data = json.loads(prompt.split("Sensor data: ")[1].split("\n\n")[0])
        self.assertEqual(tuple(sensor_data), client.CHANNELS)
        self.assertIn("Device: ESP32 + ADXL345", prompt)
        self.assertIn("Gyroscope: Not available", prompt)
        self.assertNotIn("True label", prompt)

    def test_parse_outputs_rejects_unrequested_labels_and_partial_matches(self):
        self.assertEqual(client.extract_label("**WALKING_DOWNSTAIRS**", "direct"),
                         "WALKING_DOWNSTAIRS")
        self.assertIsNone(client.extract_label("WALKING or STANDING", "direct"))
        self.assertEqual(client.extract_label("Explanation\nFINAL_LABEL: LAYING", "cot"), "LAYING")
        self.assertIsNone(client.extract_label("FINAL_LABEL: WALKING_FAST", "cot"))
        self.assertIsNone(client.extract_label("FINAL_LABEL: WALKING OR SITTING", "cot"))

    def test_window_shape_units_values_and_timing_are_checked(self):
        quality = client.validate_window(sample_window())
        self.assertEqual(quality["effective_rate_hz"], 50)
        self.assertEqual(quality["mean_vector_magnitude_g"], 1)
        invalid = []
        for field, value in (("units", "m/s2"), ("sampling_rate_hz", 100),
                             ("overruns", 1), ("channels", ["x", "y", "z"])):
            window = sample_window()
            window[field] = value
            invalid.append(window)
        for value in (float("nan"), float("inf"), True):
            window = sample_window()
            window["data"][0][1] = value
            invalid.append(window)
        window = sample_window()
        window["timestamps_us"][50] += 40000
        invalid.append(window)
        for window in invalid:
            with self.subTest(window=window), self.assertRaises(ValueError):
                client.validate_window(window)

    def test_socket_accepts_fragmented_sensor_reply_larger_than_4096(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        payload = (json.dumps({"ok": True, "data": sample_window(), "padding": "x" * 6000}) + "\n").encode()
        errors = []
        def serve():
            try:
                with listener, listener.accept()[0] as conn:
                    received = b""
                    while b"\n" not in received:
                        received += conn.recv(1024)
                    for offset in range(0, len(payload), 173):
                        conn.sendall(payload[offset:offset + 173])
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        response = client.send_command({"name": "capture_HAR", "args": []}, "127.0.0.1", port)
        thread.join(5)
        self.assertFalse(errors)
        self.assertFalse(thread.is_alive())
        self.assertEqual(response["data"], sample_window())

    def test_oled_lines_fit_screen(self):
        for label in client.LABELS:
            lines = client.oled_text(label).splitlines()
            self.assertLessEqual(len(lines), 4)
            self.assertTrue(all(len(line) <= 16 for line in lines))

    def test_classification_survives_failed_display_and_truth_is_not_in_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(results=Path(directory), location="Waist", setting="Lab",
                window=None, style="direct", model="test-model", countdown=0, host="test", port=8080)
            replies = [{"ok": True, "data": sample_window()}, OSError("OLED offline")]
            with patch.object(client, "send_command", side_effect=replies), \
                    patch.object(client, "query_gemini", return_value="WALKING"):
                output = client.run_job(args, "classify_HAR", "WALKING")
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["status"], "classified")
            self.assertTrue(result["correct"])
            self.assertFalse(result["display_ok"])
            self.assertTrue((output / "window.json").exists())
            self.assertNotIn("true_label", (output / "prompt.txt").read_text())
            summary = client.summarize(Path(directory))
            self.assertEqual(summary["by_style"]["direct"]["accuracy"], 1)
            self.assertFalse(summary["by_style"]["direct"]["at_least_10_and_all_6_classes"])

    def test_api_failure_keeps_measurements_and_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(results=Path(directory), location="Waist", setting="Lab",
                window=None, style="direct", model="test-model", countdown=0, host="test", port=8080)
            with patch.object(client, "send_command", return_value={"ok": True, "data": sample_window()}), \
                    patch.object(client, "query_gemini", side_effect=RuntimeError("API unavailable")):
                with self.assertRaises(RuntimeError):
                    client.run_job(args, "classify_HAR", "WALKING")
            output = next((Path(directory) / "samples").iterdir())
            self.assertTrue((output / "window.json").exists())
            self.assertTrue((output / "prompt.txt").exists())
            self.assertEqual(json.loads((output / "result.json").read_text())["status"], "error")

    def test_sensor_signed_conversion_and_50hz_configuration(self):
        class FakePin:
            OUT = 1
            def __init__(self, *args, **kwargs): pass
            def value(self, value): pass
        class FakeSPI:
            MSB = 0
            def __init__(self, *args, **kwargs):
                self.registers = {0: 0xE5}
            def write(self, data):
                self.address = data[0] & 0x3F
                if len(data) == 2:
                    self.registers[self.address] = data[1]
            def read(self, count):
                return bytes([self.registers.get(self.address, 0)])
            def readinto(self, target):
                target[:] = bytes([0, 255, 128, 0, 0, 1])  # -256, 128, 256
        spec = importlib.util.spec_from_file_location("har_sensor_test", ROOT / "esp32/har_sensor.py")
        module = importlib.util.module_from_spec(spec)
        machine = types.SimpleNamespace(Pin=FakePin, SPI=FakeSPI)
        with patch.dict(sys.modules, {"machine": machine}), \
                patch.object(__import__("time"), "sleep_ms", lambda _: None, create=True):
            spec.loader.exec_module(module)
            sensor = module.ADXL345()
            self.assertEqual(sensor.spi.registers[0x2C], 0x09)
            self.assertEqual(sensor.read_xyz_g(), [-1.0, 0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
