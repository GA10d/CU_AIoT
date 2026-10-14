"""Computer-side client, also imported by web_app.py.

Examples:
    python smartwatch_client.py 192.168.1.23 display_time
    python smartwatch_client.py 192.168.1.23 display_text "Hello watch"
    python smartwatch_client.py 192.168.1.23 set_alarm 16 30
"""
import json
import socket

from command_protocol import COMMAND_ARG_COUNTS, validate_command


class SmartwatchClient:
    def __init__(self, host, port=8080, timeout=20):
        if not host or not host.strip():
            raise ValueError("Set WATCH_HOST to the ESP32 IP address")
        if not 1 <= int(port) <= 65535 or float(timeout) <= 0:
            raise ValueError("Invalid WATCH_PORT or WATCH_TIMEOUT")
        self.host = host.strip()
        self.port = int(port)
        self.timeout = float(timeout)

    def send_request(self, command):
        validate_command(command)
        request = json.dumps(command).encode() + b"\n"
        if len(request) - 1 > 1024:
            raise ValueError("Command exceeds the server's 1024-byte limit")
        # No automatic retry: the device may have executed a timed-out request.
        with socket.create_connection((self.host, self.port), self.timeout) as connection:
            connection.sendall(request)
            received = bytearray()
            while b"\n" not in received:
                chunk = connection.recv(512)
                if not chunk:
                    raise ConnectionError("ESP32 closed the connection without a complete reply")
                received.extend(chunk)
                if len(received) > 4096:
                    raise ValueError("ESP32 reply exceeds the size limit")
        response = json.loads(bytes(received).split(b"\n", 1)[0].decode())
        if not isinstance(response, dict) or type(response.get("ok")) is not bool:
            raise ValueError("Invalid response from ESP32")
        return response

    def send_command(self, name, args=None):
        return self.send_request({"name": name, "args": [] if args is None else args})

    def screen_on(self):
        return self.send_command("screen_on")

    def screen_off(self):
        return self.send_command("screen_off")

    def display_time(self):
        return self.send_command("display_time")

    def set_alarm(self, hour, minute):
        return self.send_command("set_alarm", [hour, minute])

    def display_text(self, text):
        return self.send_command("display_text", [text])

    def display_location(self):
        return self.send_command("display_location")

    def display_weather(self):
        return self.send_command("display_weather")


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Send one JSON command to the smartwatch")
    parser.add_argument("host", help="ESP32 IP printed in the serial console")
    parser.add_argument("command", choices=tuple(COMMAND_ARG_COUNTS))
    parser.add_argument("args", nargs="*", help="Text, or alarm hour and minute")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--timeout", type=float, default=20)
    options = parser.parse_args()
    arguments = options.args
    if len(arguments) != COMMAND_ARG_COUNTS[options.command]:
        parser.error("{} requires {} arguments".format(
            options.command, COMMAND_ARG_COUNTS[options.command]))
    if options.command == "set_alarm":
        try:
            arguments = [int(value) for value in arguments]
        except ValueError:
            parser.error("Alarm hour and minute must be integers")
    try:
        client = SmartwatchClient(options.host, options.port, options.timeout)
        response = client.send_command(options.command, arguments)
    except (OSError, ValueError) as error:
        print("Client error: {}".format(error), file=sys.stderr)
        return 1
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
