"""Exercise actual firmware functions without importing machine or starting Wi-Fi."""
import ast
import gc
import json
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace


class FakeConnection:
    def __init__(self, max_send=37):
        self.max_send = max_send
        self.received = bytearray()
        self.largest_send = 0
        self.closed = False

    def settimeout(self, seconds):
        self.timeout = seconds

    def send(self, data):
        self.largest_send = max(self.largest_send, len(data))
        sent = min(self.max_send, len(data))
        self.received.extend(data[:sent])
        return sent

    def close(self):
        self.closed = True


class StreamingResponseTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "esp32/main.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"JSONSocketWriter", "write_json_value", "send_json_line", "handle_client"}
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                 and n.name in names]
        self.ns = {"json": json, "gc": gc}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), self.ns)

    def test_full_sensor_window_roundtrips_with_bounded_sends_and_no_container_dumps(self):
        response = {"ok": True, "data": {
            "channels": ["total_acc_x", "total_acc_y", "total_acc_z"],
            "data": [[round((i - 64) / 256, 4) for i in range(128)] for _ in range(3)],
            "timestamps_us": [i * 20000 for i in range(128)],
            "units": "g", "num_samples": 128, "device": "ESP32 + ADXL345",
            "sampling_rate_hz": 50, "effective_rate_hz": 49.9,
            "elapsed_ms": 2560.0, "max_gap_ms": 21.0, "overruns": 0, "range_g": 4,
            "note": '引号 " and newline\n', "optional": None}}
        scalar_calls = []
        def scalar_dumps(value):
            self.assertNotIsInstance(value, (dict, list, tuple))
            scalar_calls.append(value)
            return json.dumps(value)
        self.ns["json"] = SimpleNamespace(dumps=scalar_dumps)
        conn = FakeConnection(max_send=13)
        self.ns["send_json_line"](conn, response)
        self.assertEqual(json.loads(conn.received), response)
        self.assertEqual(conn.received.count(b"\n"), 1)
        self.assertTrue(conn.received.endswith(b"\n"))
        self.assertLessEqual(conn.largest_send, 512)
        self.assertGreater(len(conn.received), 4000)
        self.assertGreater(len(scalar_calls), 384)

    def test_zero_byte_send_does_not_spin_forever(self):
        with self.assertRaises(OSError):
            self.ns["send_json_line"](FakeConnection(max_send=0), {"ok": True})

    def test_memory_error_closes_client_releases_response_and_allows_next_request(self):
        class Payload(dict):
            pass
        references = []
        def make_response(raw_text):
            response = Payload(ok=True, data=[1, 2, 3])
            references.append(weakref.ref(response))
            return response
        self.ns["receive_line"] = lambda conn: '{"name":"capture_HAR","args":[]}'
        self.ns["handle_json"] = make_response
        real_send = self.ns["send_json_line"]
        calls = []
        def send(conn, response):
            calls.append(1)
            if len(calls) == 1:
                raise MemoryError("injected allocation failure")
            real_send(conn, response)
        self.ns["send_json_line"] = send
        first, second = FakeConnection(), FakeConnection()
        self.ns["handle_client"](first)
        self.assertTrue(first.closed)
        self.assertIsNone(references[0]())
        self.ns["handle_client"](second)
        self.assertTrue(second.closed)
        self.assertEqual(json.loads(second.received), {"ok": True, "data": [1, 2, 3]})
        self.assertIsNone(references[1]())


if __name__ == "__main__":
    unittest.main()
