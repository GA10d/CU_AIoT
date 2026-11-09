"""ESP32 TCP server: one newline-terminated JSON command/reply per connection.

Call poll() from main's loop. Idle clients and partial packets do not block
the clock. Command handlers themselves run synchronously.
"""
import errno
import json
import socket

try:
    from time import ticks_diff, ticks_ms
except ImportError:
    from time import monotonic

    def ticks_ms():
        return int(monotonic() * 1000)

    def ticks_diff(a, b):
        return a - b

from command_protocol import CommandError, validate_command


class CommandServer:
    def __init__(self, execute_command, host="0.0.0.0", port=8080,
                 client_timeout_ms=5000, max_request_bytes=1024):
        self.execute_command = execute_command
        self.host = host
        self.port = port
        self.client_timeout_ms = client_timeout_ms
        self.max_request_bytes = max_request_bytes
        self._listener = None
        self._client = None
        self._received = bytearray()
        self._outgoing = None
        self._sent = 0
        self._last_activity = 0

    @staticmethod
    def _would_block(error):
        return bool(error.args) and error.args[0] in (
            errno.EAGAIN, getattr(errno, "EWOULDBLOCK", errno.EAGAIN))

    def start(self):
        if self._listener is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            address = socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                                         socket.SOCK_STREAM)[0][-1]
            listener.bind(address)
            listener.listen(2)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self._listener = listener

    def _close_client(self):
        if self._client is not None:
            self._client.close()
        self._client = None
        self._received = bytearray()
        self._outgoing = None
        self._sent = 0

    def close(self):
        self._close_client()
        if self._listener is not None:
            self._listener.close()
            self._listener = None

    def _reply(self, payload):
        try:
            self._outgoing = json.dumps(payload).encode() + b"\n"
        except (TypeError, ValueError):
            self._outgoing = json.dumps({"ok": False, "error": {
                "code": "execution_failed", "message": "Result is not JSON serializable"
            }}).encode() + b"\n"
        self._sent = 0
        self._last_activity = ticks_ms()

    def _error(self, code, message):
        self._reply({"ok": False, "error": {"code": code, "message": message}})

    def _read_request(self):
        try:
            chunk = self._client.recv(256)
        except OSError as error:
            if not self._would_block(error):
                self._close_client()
            return
        if chunk is None:
            return
        if not chunk:
            self._close_client()
            return
        self._last_activity = ticks_ms()
        self._received.extend(chunk)
        end = self._received.find(b"\n")
        if end < 0:
            if len(self._received) > self.max_request_bytes:
                self._error("request_too_large", "Command exceeds size limit")
            return
        if end > self.max_request_bytes:
            self._error("request_too_large", "Command exceeds size limit")
            return
        try:
            command = json.loads(bytes(self._received[:end]).decode())
        except ValueError:
            self._error("invalid_json", "Request must contain valid UTF-8 JSON")
            return
        try:
            validate_command(command)
            result = self.execute_command(command)
        except CommandError as error:
            self._error(error.code, str(error))
        except (TypeError, ValueError) as error:
            self._error("invalid_arguments", str(error))
        except Exception as error:
            self._error("execution_failed", str(error))
        else:
            self._reply({"ok": True, "command": command["name"], "result": result})

    def _send_response(self):
        try:
            sent = self._client.send(self._outgoing[self._sent:self._sent + 256])
        except OSError as error:
            if not self._would_block(error):
                self._close_client()
            return
        if sent is None:
            return
        if sent == 0:
            self._close_client()
            return
        self._sent += sent
        self._last_activity = ticks_ms()
        if self._sent == len(self._outgoing):
            self._close_client()

    def poll(self):
        if self._listener is None:
            raise RuntimeError("Server has not started")
        if self._client is None:
            try:
                client, _ = self._listener.accept()
            except OSError as error:
                if self._would_block(error):
                    return
                raise
            try:
                client.setblocking(False)
            except Exception:
                client.close()
                return
            self._client = client
            self._last_activity = ticks_ms()
        if ticks_diff(ticks_ms(), self._last_activity) >= self.client_timeout_ms:
            if self._outgoing is None:
                self._error("request_timeout", "No complete command received before timeout")
            else:
                self._close_client()
            return
        if self._outgoing is None:
            self._read_request()
        else:
            self._send_response()
