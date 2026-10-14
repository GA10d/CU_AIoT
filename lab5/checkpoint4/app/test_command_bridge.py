"""Run on the computer: python -m unittest -v test_command_bridge.py.

Uses loopback TCP and fake LLM/hardware; no API calls or ESP32 required.
"""
import asyncio
import ast
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

SERVER_FOLDER = Path(__file__).resolve().parent.parent / "server"
sys.path.append(str(SERVER_FOLDER))

from command_protocol import COMMAND_ARG_COUNTS
from command_server import CommandServer
from smartwatch_client import SmartwatchClient


class Harness:
    def __init__(self):
        self.commands = []
        self.ticks = 0
        self.failure = None
        self.errors = []
        self.stop = threading.Event()
        self.server = CommandServer(self.execute, host="127.0.0.1", port=0,
                                    client_timeout_ms=200)
        self.server.start()
        self.port = self.server._listener.getsockname()[1]
        self.client = SmartwatchClient("127.0.0.1", self.port, timeout=2)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def execute(self, command):
        self.commands.append(command)
        if self.failure is not None:
            raise self.failure
        return {"received": command["args"]}

    def run(self):
        try:
            while not self.stop.is_set():
                self.ticks += 1
                self.server.poll()
                time.sleep(0.001)
        except Exception as error:
            self.errors.append(error)

    def close(self):
        self.stop.set()
        self.thread.join(2)
        self.server.close()
        if self.thread.is_alive() or self.errors:
            raise AssertionError("Server failed: {}".format(self.errors))

    def connect(self):
        return socket.create_connection(("127.0.0.1", self.port), timeout=2)

    @staticmethod
    def receive(connection):
        data = b""
        while b"\n" not in data:
            chunk = connection.recv(512)
            if not chunk:
                raise AssertionError("Missing reply")
            data += chunk
        return json.loads(data.split(b"\n", 1)[0])

    def raw(self, data):
        with self.connect() as connection:
            connection.sendall(data)
            return self.receive(connection)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Harness()

    def tearDown(self):
        self.bridge.close()

    def test_all_seven_client_commands(self):
        examples = {
            "screen_on": [], "screen_off": [], "display_time": [],
            "set_alarm": [16, 30], "display_text": ["Hello\nwatch"],
            "display_location": [], "display_weather": [],
        }
        for name, args in examples.items():
            reply = getattr(self.bridge.client, name)(*args)
            self.assertTrue(reply["ok"])
            self.assertEqual(reply["result"]["received"], args)
        self.assertEqual(len(self.bridge.commands), 7)

    def test_invalid_json_and_utf8_do_not_execute(self):
        for data in [b"{bad}\n", b"\xff\n"]:
            self.assertEqual(self.bridge.raw(data)["error"]["code"], "invalid_json")
        self.assertEqual(self.bridge.commands, [])

    def test_invalid_commands_and_arguments(self):
        examples = [
            ([], "invalid_command"),
            ({"name": "screen_on"}, "invalid_command"),
            ({"name": "unknown", "args": []}, "unknown_command"),
            ({"name": "screen_off", "args": [1]}, "invalid_arguments"),
            ({"name": "set_alarm", "args": [24, 0]}, "invalid_arguments"),
            ({"name": "set_alarm", "args": [True, 0]}, "invalid_arguments"),
            ({"name": "display_text", "args": ["你好"]}, "invalid_arguments"),
        ]
        for request, code in examples:
            response = self.bridge.raw(json.dumps(request).encode() + b"\n")
            self.assertEqual(response["error"]["code"], code)
        self.assertEqual(self.bridge.commands, [])

    def test_fragmented_request_keeps_polling(self):
        request = b'{"name":"display_time","args":[]}\n'
        with self.bridge.connect() as connection:
            connection.sendall(request[:12])
            before = self.bridge.ticks
            time.sleep(0.04)
            self.assertGreater(self.bridge.ticks, before)
            self.assertEqual(self.bridge.commands, [])
            connection.sendall(request[12:])
            self.assertTrue(self.bridge.receive(connection)["ok"])
        self.assertEqual(len(self.bridge.commands), 1)

    def test_idle_connection_times_out_without_stopping_loop(self):
        before = self.bridge.ticks
        with self.bridge.connect() as connection:
            response = self.bridge.receive(connection)
        self.assertEqual(response["error"]["code"], "request_timeout")
        self.assertGreater(self.bridge.ticks, before + 10)
        self.assertTrue(self.bridge.client.display_time()["ok"])

    def test_oversized_request(self):
        response = self.bridge.raw(b"x" * 1100)
        self.assertEqual(response["error"]["code"], "request_too_large")
        self.assertEqual(self.bridge.commands, [])

    def test_disconnect_does_not_break_next_request(self):
        with self.bridge.connect() as connection:
            connection.sendall(b'{"name":')
        self.assertTrue(self.bridge.client.screen_on()["ok"])

    def test_execution_error_is_reported_and_server_survives(self):
        self.bridge.failure = OSError("Weather service unavailable")
        response = self.bridge.client.display_weather()
        self.assertEqual(response["error"]["code"], "execution_failed")
        self.bridge.failure = None
        self.assertTrue(self.bridge.client.display_time()["ok"])

    def test_partial_sends_preserve_reply(self):
        class ShortSocket:
            data = b""
            closed = False

            def send(self, data):
                self.data += data[:3]
                return len(data[:3])

            def close(self):
                self.closed = True

        sender = CommandServer(lambda command: None)
        connection = ShortSocket()
        sender._client = connection
        sender._reply({"ok": True, "result": "short writes"})
        while sender._client is not None:
            sender._send_response()
        self.assertTrue(connection.closed)
        self.assertEqual(json.loads(connection.data), {"ok": True, "result": "short writes"})

    def test_protocol_copies_are_identical(self):
        self.assertEqual(Path(__file__).with_name("command_protocol.py").read_text(),
                         (SERVER_FOLDER / "command_protocol.py").read_text())

    def test_protocol_matches_main_registry(self):
        tree = ast.parse((SERVER_FOLDER / "main.py").read_text())
        names = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "COMMAND_LIST" and node.func.attr == "update"):
                names.update(ast.literal_eval(key) for key in node.args[0].keys)
        self.assertEqual(names, set(COMMAND_ARG_COUNTS))


def load_web_app():
    path = Path(__file__).with_name("web_app.py")
    spec = importlib.util.spec_from_file_location("bridge_web_app", path)
    module = importlib.util.module_from_spec(spec)
    stubs = {
        "gradio": types.SimpleNamespace(),
        "whisper": types.SimpleNamespace(),
        "dotenv": types.SimpleNamespace(load_dotenv=lambda path: None),
        "agent_system": types.SimpleNamespace(SmartwatchAssistant=object),
    }
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


class WebAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bridge = Harness()
        self.web = load_web_app()

    def tearDown(self):
        self.bridge.close()

    @staticmethod
    def assistant(response):
        async def get_response(prompt):
            return response
        return types.SimpleNamespace(get_response=get_response)

    async def test_gradio_to_tcp_result(self):
        raw = '{"name":"display_text","args":["Hello watch"]}'
        result = await self.web.process_input(None, "show hello", None,
                                             self.assistant(raw), self.bridge.client)
        self.assertEqual(result[:2], ("show hello", raw))
        self.assertTrue(json.loads(result[2])["ok"])
        self.assertEqual(self.bridge.commands[0]["name"], "display_text")

    async def test_audio_to_command(self):
        model = types.SimpleNamespace(transcribe=lambda audio, fp16: {"text": "show time"})
        result = await self.web.process_input("recording.wav", "", model,
            self.assistant('{"name":"display_time","args":[]}'), self.bridge.client)
        self.assertEqual(result[0], "show time")
        self.assertTrue(json.loads(result[2])["ok"])

    async def test_bad_llm_response_never_reaches_device(self):
        for raw in ['{bad}', '{"name":"set_alarm","args":[99,0]}']:
            result = await self.web.process_input(None, "test", None,
                                                 self.assistant(raw), self.bridge.client)
            self.assertFalse(json.loads(result[2])["ok"])
        self.assertEqual(self.bridge.commands, [])

    async def test_missing_device_ip_has_actionable_error(self):
        result = await self.web.process_input(None, "time", None,
            self.assistant('{"name":"display_time","args":[]}'), None)
        self.assertEqual(json.loads(result[2])["error"]["code"], "not_configured")

    async def test_socket_send_does_not_block_event_loop(self):
        progress = []

        def send_request(command):
            time.sleep(0.05)
            progress.append("sent")
            return {"ok": True, "result": None}

        async def heartbeat():
            await asyncio.sleep(0.01)
            progress.append("heartbeat")

        await asyncio.gather(self.web.process_input(None, "time", None,
            self.assistant('{"name":"display_time","args":[]}'),
            types.SimpleNamespace(send_request=send_request)), heartbeat())
        self.assertEqual(progress, ["heartbeat", "sent"])

    async def test_device_failure_is_shown_in_gradio(self):
        self.bridge.failure = OSError("Device request failed")
        result = await self.web.process_input(None, "weather", None,
            self.assistant('{"name":"display_weather","args":[]}'), self.bridge.client)
        self.assertEqual(json.loads(result[2])["error"]["code"], "execution_failed")


if __name__ == "__main__":
    unittest.main()
