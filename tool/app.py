#!/usr/bin/env python3
"""Local-only web control panel for a MicroPython HUZZAH ESP32."""

from __future__ import annotations

import glob
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
HOST = "127.0.0.1"
PORT = 8765
MAX_PROGRAM_SIZE = 2 * 1024 * 1024
DEFAULT_BAUD = 115200
PORT_PATTERNS = (
    "/dev/cu.usbserial-*",
    "/dev/cu.SLAB_USBtoUART*",
    "/dev/cu.wchusbserial*",
    "/dev/cu.usbmodem*",
)


class ControlState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.status = "idle"
        self.status_text = "串口已释放，等待烧录"
        self.serial_port = None
        self.serial_thread: threading.Thread | None = None
        self.serial_stop = threading.Event()
        self.operation_lock = threading.Lock()
        self.logs: deque[dict] = deque(maxlen=1200)
        self.next_log_id = 1

    def add_log(self, message: str, kind: str = "info") -> None:
        if not message:
            return
        with self.lock:
            for line in message.rstrip("\n").splitlines() or [""]:
                self.logs.append(
                    {
                        "id": self.next_log_id,
                        "time": time.strftime("%H:%M:%S"),
                        "kind": kind,
                        "message": line,
                    }
                )
                self.next_log_id += 1

    def set_status(self, status: str, text: str) -> None:
        with self.lock:
            self.status = status
            self.status_text = text

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "statusText": self.status_text,
                "ports": discover_ports(),
                "monitoring": self.serial_port is not None,
            }


STATE = ControlState()


def discover_ports() -> list[str]:
    ports: set[str] = set()
    for pattern in PORT_PATTERNS:
        ports.update(glob.glob(pattern))
    return sorted(ports)


def normalize_port(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("请选择串口")
    if not value.startswith("/dev/cu."):
        raise ValueError("只允许使用 /dev/cu.* 串口")
    if value not in discover_ports():
        raise ValueError(f"串口不存在或已断开：{value}")
    return value


def parse_baud(value) -> int:
    try:
        baud = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("波特率必须是整数") from exc
    if baud < 300 or baud > 4_000_000:
        raise ValueError("波特率超出允许范围")
    return baud


def port_owners(port: str) -> str:
    try:
        result = subprocess.run(
            ["lsof", "-n", port],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    lines = result.stdout.strip().splitlines()
    return "\n".join(lines[1:]) if len(lines) > 1 else ""


def stop_monitor(log: bool = True) -> None:
    STATE.serial_stop.set()
    with STATE.lock:
        serial_port = STATE.serial_port
        serial_thread = STATE.serial_thread
        STATE.serial_port = None
        STATE.serial_thread = None
    if serial_port is not None:
        try:
            serial_port.close()
        except Exception:
            pass
    if serial_thread and serial_thread is not threading.current_thread():
        serial_thread.join(timeout=1.5)
    STATE.serial_stop.clear()
    STATE.set_status("idle", "串口已释放，等待烧录")
    if log:
        STATE.add_log("串口已释放。", "success")


def serial_reader(serial_port) -> None:
    buffer = bytearray()
    try:
        while not STATE.serial_stop.is_set() and serial_port.is_open:
            chunk = serial_port.read(serial_port.in_waiting or 1)
            if not chunk:
                continue
            buffer.extend(chunk)
            while b"\n" in buffer:
                raw, _, remainder = buffer.partition(b"\n")
                buffer = bytearray(remainder)
                STATE.add_log(raw.rstrip(b"\r").decode("utf-8", errors="replace"), "serial")
        if buffer:
            STATE.add_log(buffer.decode("utf-8", errors="replace"), "serial")
    except Exception as exc:
        if not STATE.serial_stop.is_set():
            STATE.add_log(f"串口读取失败：{exc}", "error")
            STATE.set_status("error", "串口读取中断")
    finally:
        try:
            serial_port.close()
        except Exception:
            pass
        with STATE.lock:
            if STATE.serial_port is serial_port:
                STATE.serial_port = None
                STATE.serial_thread = None


def start_monitor(port: str, baud: int) -> None:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("缺少 pyserial，请在 aiot 环境运行：python -m pip install pyserial") from exc

    stop_monitor(log=False)
    owners = port_owners(port)
    if owners:
        raise RuntimeError(f"串口正被其他程序占用：\n{owners}")

    STATE.add_log(f"$ serial-monitor {port} {baud}", "command")
    try:
        serial_port = serial.Serial(port=port, baudrate=baud, timeout=0.2)
    except Exception as exc:
        raise RuntimeError(f"无法打开串口：{exc}") from exc

    thread = threading.Thread(target=serial_reader, args=(serial_port,), daemon=True)
    with STATE.lock:
        STATE.serial_port = serial_port
        STATE.serial_thread = thread
    STATE.set_status("monitoring", "正在查看串口输出")
    STATE.add_log("串口监视已启动。按一下板子的 EN/RESET 可查看启动输出。", "success")
    thread.start()


def find_upload_tool() -> tuple[str, str] | None:
    mpremote_candidates = [
        shutil.which("mpremote"),
        "/opt/anaconda3/envs/aiot/bin/mpremote",
        str(Path.home() / "anaconda3/envs/aiot/bin/mpremote"),
        str(Path.home() / "miniconda3/envs/aiot/bin/mpremote"),
    ]
    for candidate in mpremote_candidates:
        if candidate and Path(candidate).is_file():
            return "mpremote", candidate
    return None


def serial_read_until(serial_port, marker: bytes, timeout: float, description: str) -> bytes:
    deadline = time.monotonic() + timeout
    received = bytearray()
    while time.monotonic() < deadline:
        # Read one byte at a time so protocol delimiters never consume bytes
        # belonging to the next Raw REPL response section.
        chunk = serial_port.read(1)
        if chunk:
            received.extend(chunk)
            if marker in received:
                return bytes(received)
    tail = bytes(received[-160:]).decode("utf-8", errors="replace")
    raise RuntimeError(f"等待 {description} 超时。设备最后返回：{tail!r}")


def raw_repl_exec(serial_port, source: str) -> bytes:
    serial_port.write(source.encode("utf-8") + b"\x04")
    serial_port.flush()
    acknowledgement = serial_read_until(serial_port, b"OK", 4, "MicroPython 确认命令")
    if not acknowledgement.endswith(b"OK"):
        raise RuntimeError("MicroPython 没有接受上传命令")
    standard_output = serial_read_until(serial_port, b"\x04", 8, "命令输出")[:-1]
    standard_error = serial_read_until(serial_port, b"\x04", 8, "命令错误输出")[:-1]
    serial_read_until(serial_port, b">", 4, "Raw REPL 提示符")
    if standard_error:
        error_text = standard_error.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ESP32 执行上传命令失败：{error_text}")
    return standard_output


def upload_bytes_with_raw_repl(serial_port, program: bytes) -> None:
    # Interrupt a running main.py, then switch to MicroPython raw REPL mode.
    serial_port.write(b"\r\x03\x03")
    serial_port.flush()
    time.sleep(0.15)
    serial_port.reset_input_buffer()
    serial_port.write(b"\r\x01")
    serial_port.flush()
    banner = serial_read_until(serial_port, b">", 5, "MicroPython Raw REPL")
    # Some ESP32 MicroPython builds return only "\r\n>" when raw REPL is
    # already active. Briefly collect any trailing bytes so a friendly-REPL
    # prompt (">>>") is still rejected rather than mistaken for raw mode.
    time.sleep(0.04)
    if serial_port.in_waiting:
        banner += serial_port.read(serial_port.in_waiting)
    compact_banner = banner.strip()
    if b"raw REPL" not in banner and compact_banner != b">":
        text = banner.decode("utf-8", errors="replace")
        raise RuntimeError(f"设备没有进入 MicroPython Raw REPL：{text!r}")

    temporary_name = ".main.py.upload"
    raw_repl_exec(serial_port, "import ubinascii, uos")
    raw_repl_exec(serial_port, f"f=open({temporary_name!r},'wb')")
    chunk_size = 384
    chunk_count = max(1, (len(program) + chunk_size - 1) // chunk_size)
    last_progress = -1
    for index, offset in enumerate(range(0, len(program), chunk_size), start=1):
        encoded = base64.b64encode(program[offset : offset + chunk_size]).decode("ascii")
        raw_repl_exec(serial_port, f"f.write(ubinascii.a2b_base64({encoded!r}))")
        progress = int(index * 100 / chunk_count)
        if progress // 20 != last_progress // 20 or progress == 100:
            STATE.add_log(f"正在传输 main.py… {progress}%", "output")
            last_progress = progress
    raw_repl_exec(serial_port, "f.close()")
    raw_repl_exec(
        serial_port,
        f"\ntry:\n uos.remove('main.py')\nexcept OSError:\n pass\nuos.rename({temporary_name!r},'main.py')",
    )
    # Return to the friendly REPL and soft-reset so the new main.py starts.
    serial_port.write(b"\x02\x04")
    serial_port.flush()


def upload_with_builtin_serial(port: str, program: bytes) -> None:
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("缺少 pyserial，请在 aiot 环境运行：python -m pip install pyserial") from exc

    STATE.add_log(f"$ built-in-micropython-uploader {port} main.py", "command")
    try:
        serial_port = serial.Serial(port=port, baudrate=115200, timeout=0.15, write_timeout=4)
    except Exception as exc:
        raise RuntimeError(f"无法打开串口：{exc}") from exc
    try:
        upload_bytes_with_raw_repl(serial_port, program)
    finally:
        try:
            serial_port.close()
        except Exception:
            pass


def stream_process(command: list[str], cwd: Path) -> None:
    STATE.add_log("$ " + " ".join(command), "command")
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        STATE.add_log(line, "output")
    return_code = process.wait(timeout=30)
    if return_code != 0:
        raise RuntimeError(f"烧录工具退出，状态码 {return_code}")


def upload_program(port: str, program: bytes) -> None:
    if not STATE.operation_lock.acquire(blocking=False):
        raise RuntimeError("已有操作正在进行，请稍候")
    try:
        stop_monitor(log=False)
        owners = port_owners(port)
        if owners:
            raise RuntimeError(f"串口正被其他程序占用：\n{owners}")

        STATE.set_status("flashing", "正在烧录 main.py")
        STATE.add_log("准备烧录，已确认串口处于释放状态。", "info")
        upload_tool = find_upload_tool()
        if upload_tool:
            _tool_kind, tool_path = upload_tool
            with tempfile.TemporaryDirectory(prefix="huzzah-upload-") as temp_dir:
                temp_path = Path(temp_dir)
                (temp_path / "main.py").write_bytes(program)
                command = [tool_path, "connect", port, "fs", "cp", "main.py", ":main.py"]
                stream_process(command, temp_path)
        else:
            upload_with_builtin_serial(port, program)

        STATE.add_log("main.py 烧录完成。", "success")
        STATE.set_status("idle", "烧录完成，串口已释放")
    except Exception:
        STATE.set_status("error", "烧录失败，串口已释放")
        raise
    finally:
        STATE.operation_lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "HUZZAHControl/1.0"

    def log_message(self, _format: str, *_args) -> None:
        return

    def send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 64 * 1024:
            raise ValueError("请求过大")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json(STATE.snapshot())
            return
        if parsed.path == "/api/logs":
            after = int(parse_qs(parsed.query).get("after", ["0"])[0])
            with STATE.lock:
                logs = [entry for entry in STATE.logs if entry["id"] > after]
            self.send_json({"logs": logs})
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True})
            return

        path = "/index.html" if parsed.path == "/" else parsed.path
        requested = (STATIC_ROOT / path.lstrip("/")).resolve()
        if STATIC_ROOT not in requested.parents or not requested.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8" if requested.suffix == ".html" else "text/plain"
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/monitor/start":
                payload = self.read_json()
                start_monitor(normalize_port(payload.get("port", "")), parse_baud(payload.get("baud")))
                self.send_json({"ok": True})
                return

            if self.path == "/api/monitor/stop":
                stop_monitor()
                self.send_json({"ok": True})
                return

            if self.path == "/api/upload":
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_PROGRAM_SIZE:
                    raise ValueError("main.py 必须为 1 byte–2 MB")
                port = normalize_port(self.headers.get("X-Serial-Port", ""))
                filename = self.headers.get("X-Filename", "")
                if Path(filename).name != "main.py":
                    raise ValueError("只能烧录名为 main.py 的文件")
                program = self.rfile.read(length)
                if b"\x00" in program:
                    raise ValueError("main.py 看起来不是文本文件")
                upload_program(port, program)
                self.send_json({"ok": True})
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, RuntimeError) as exc:
            STATE.add_log(str(exc), "error")
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            STATE.add_log(f"未预期错误：{exc}", "error")
            STATE.set_status("error", "操作失败")
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def shutdown_handler(_signum=None, _frame=None) -> None:
    stop_monitor(log=False)
    raise KeyboardInterrupt


def main() -> None:
    if not STATIC_ROOT.is_dir():
        raise SystemExit("static directory is missing")
    signal.signal(signal.SIGTERM, shutdown_handler)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    STATE.add_log("HUZZAH 控制台已启动。", "success")
    print(f"HUZZAH 控制台：{url}")
    print("按 Control-C 停止服务。")
    if os.environ.get("HUZZAH_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_monitor(log=False)
        server.server_close()


if __name__ == "__main__":
    main()
