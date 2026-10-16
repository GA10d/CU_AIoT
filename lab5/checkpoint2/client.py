"""Interactive client: send one JSON command and display its response."""

import json
import socket


ESP_IP = "10.206.165.2"
PORT = 8080

HELP_TEXT = """Enter one JSON command per line. 
Type help to show examples, or q to quit."""


def send_command(command, host=ESP_IP, port=PORT):

    payload = (json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8")

    with socket.create_connection((host, port), timeout=5) as client:
        client.settimeout(30)
        client.sendall(payload)

        reply = b""
        while b"\n" not in reply:
            chunk = client.recv(1024)
            if not chunk:
                raise RuntimeError("Connection closed before a complete response")
            reply += chunk
            if len(reply) > 4096:
                raise RuntimeError("Server response is too long")

    return json.loads(reply.split(b"\n", 1)[0].decode("utf-8"))


def main():
    print("Target ESP32: {}:{}".format(ESP_IP, PORT))
    print(HELP_TEXT)

    try:
        while True:
            raw_text = input("JSON> ").strip()
            if not raw_text:
                continue
            if raw_text.lower() in ("q", "quit", "exit"):
                break
            if raw_text.lower() == "help":
                print(HELP_TEXT)
                continue

            try:
                command = json.loads(raw_text)
            except json.JSONDecodeError as error:
                print("Invalid JSON: {}".format(error))
                continue

            try:
                response = send_command(command)
                print(json.dumps(response, ensure_ascii=False))
            except OSError as error:
                if isinstance(error, TimeoutError):
                    print("Request timed out. Check the server and Wi-Fi connection.")
                else:
                    code = getattr(error, "winerror", None) or error.errno
                    print(
                        "Network error (code {}). Check the ESP32 IP, server, and Wi-Fi.".format(
                            code if code is not None else "unknown"
                        )
                    )
            except (RuntimeError, ValueError) as error:
                print("Request failed: {}".format(error))

    except (EOFError, KeyboardInterrupt):
        print()

    print("Client exited.")


if __name__ == "__main__":
    main()
