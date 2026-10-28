#!/usr/bin/env bash
# Upload Lab 6 Checkpoint 4 code to the ESP32 (MicroPython) and reboot it.
#
# Usage:
#   ./flash.sh                  auto-detect the serial port
#   ./flash.sh /dev/cu.usbserial-XXXX
#   ./flash.sh --monitor        after reboot, attach to the REPL to watch boot output (Ctrl-] to exit)
#   ESP32_PORT=/dev/cu.xxx ./flash.sh
set -euo pipefail

ENV_NAME="aiot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${ESP32_PORT:-}"
MONITOR=0
for arg in "$@"; do
    case "$arg" in
        --monitor|-m) MONITOR=1 ;;
        /dev/*) PORT="$arg" ;;
        *) echo "[ERROR] unknown argument: $arg" >&2; exit 1 ;;
    esac
done

# --- find mpremote (prefer the aiot conda env) ---------------------------------
MPREMOTE=""
for candidate in /opt/anaconda3/envs/$ENV_NAME/bin/mpremote \
                 "$HOME/anaconda3/envs/$ENV_NAME/bin/mpremote" \
                 "$HOME/miniconda3/envs/$ENV_NAME/bin/mpremote" \
                 "$HOME/miniforge3/envs/$ENV_NAME/bin/mpremote"; do
    if [ -x "$candidate" ]; then MPREMOTE="$candidate"; break; fi
done
if [ -z "$MPREMOTE" ] && command -v mpremote >/dev/null 2>&1; then
    MPREMOTE="$(command -v mpremote)"
fi
if [ -z "$MPREMOTE" ]; then
    echo "[ERROR] mpremote not found. Install it into the $ENV_NAME env:" >&2
    echo "    conda run -n $ENV_NAME pip install mpremote" >&2
    exit 1
fi

# --- find the serial port -------------------------------------------------------
if [ -z "$PORT" ]; then
    ports=()
    for p in /dev/cu.usbserial-* /dev/cu.SLAB_USBtoUART* /dev/cu.wchusbserial* /dev/cu.usbmodem*; do
        [ -e "$p" ] && ports+=("$p")
    done
    if [ ${#ports[@]} -eq 0 ]; then
        echo "[ERROR] no ESP32 serial port found. Plug the board in via USB and retry." >&2
        exit 1
    elif [ ${#ports[@]} -gt 1 ]; then
        echo "[ERROR] several serial ports found; pass one explicitly:" >&2
        printf '    %s\n' "${ports[@]}" >&2
        exit 1
    fi
    PORT="${ports[0]}"
fi
if [ ! -e "$PORT" ]; then
    echo "[ERROR] serial port $PORT does not exist." >&2
    exit 1
fi

# Another program (serial monitor, Thonny, HUZZAH Control Deck) holding the port blocks the upload.
if command -v lsof >/dev/null 2>&1; then
    owners="$(lsof -n "$PORT" 2>/dev/null | awk 'NR>1 {print $1" (pid "$2")"}' | sort -u || true)"
    if [ -n "$owners" ]; then
        echo "[ERROR] $PORT is in use by: $owners" >&2
        echo "        Close that serial monitor and retry." >&2
        exit 1
    fi
fi

# --- files to upload ------------------------------------------------------------
if [ ! -f device_config.py ]; then
    echo "[ERROR] device_config.py is missing. Create it from the example and fill in Wi-Fi + server URL:" >&2
    echo "    cp device_config.example.py device_config.py" >&2
    exit 1
fi
if grep -q 'your_wifi_name\|your_wifi_password' device_config.py; then
    echo "[ERROR] device_config.py still has placeholder Wi-Fi credentials." >&2
    exit 1
fi

files=()
for f in *.py; do
    case "$f" in
        *.example.py|test_*.py) ;;
        *) files+=("$f") ;;
    esac
done
if [ ! -f main.py ]; then
    echo "[ERROR] main.py not found in $SCRIPT_DIR" >&2
    exit 1
fi

# --- upload -----------------------------------------------------------------------
echo "[INFO] Port:   $PORT"
echo "[INFO] Tool:   $MPREMOTE"
echo "[INFO] Files:  ${files[*]}"

# Check the board responds and that the OLED driver (not part of this repo) is already there.
if ! device_ls="$("$MPREMOTE" connect "$PORT" fs ls : 2>&1)"; then
    echo "[ERROR] could not talk to the board on $PORT:" >&2
    echo "$device_ls" >&2
    echo "        Try pressing the RESET button on the ESP32, or unplug/replug it." >&2
    exit 1
fi
if ! grep -q 'ssd1306.py' <<<"$device_ls"; then
    echo "[WARN] ssd1306.py is not on the board; main.py imports it. Upload the driver separately." >&2
fi

echo "[INFO] Uploading ..."
"$MPREMOTE" connect "$PORT" fs cp "${files[@]}" :
echo "[INFO] Rebooting the board ..."
"$MPREMOTE" connect "$PORT" reset
echo "[OK] Done. The board is restarting main.py."

if [ "$MONITOR" -eq 1 ]; then
    echo "[INFO] Attaching to the REPL (Ctrl-] to exit) ..."
    exec "$MPREMOTE" connect "$PORT" repl
else
    echo "       Watch boot output with: ./flash.sh --monitor   (or: $MPREMOTE connect $PORT repl)"
fi
