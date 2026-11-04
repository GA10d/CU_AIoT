#!/usr/bin/env bash
# Double-click in Finder: flash the Lab 6 Checkpoint 3 + 4 firmware to the ESP32.
#   A = Checkpoint 4 (classify via /classify), C = Checkpoint 3 (upload via /upload), B = true label
# Uploads boot.py, main.py, ssd1306.py, device_config.py from checkpoint4/esp32, reboots the
# board, then shows its boot output so you can see "WiFi connected" (press Ctrl-] to close).
cd "$(dirname "$0")/checkpoint4/esp32" || exit 1

pause_and_exit() {
    echo
    read -r -p "Press Return to close this window..." _
    exit "$1"
}

if [ ! -f device_config.py ]; then
    echo "[ERROR] checkpoint4/esp32/device_config.py is missing."
    echo "        Copy device_config.example.py to device_config.py and fill in Wi-Fi + server URL."
    pause_and_exit 1
fi

# The firmware talks to this URL; warn early if the VM or Flask is not up.
SERVER_URL="$(grep -o 'http://[^"]*' device_config.py | head -1)"
echo "[INFO] Server in device_config.py: $SERVER_URL"
if curl -s -m 5 "$SERVER_URL/" | grep -q "lab6 server ok"; then
    echo "[OK]   Server is reachable."
else
    echo "[WARN] Server is not reachable. Start the VM and run app.py in screen,"
    echo "       or update SERVER_URL in checkpoint4/esp32/device_config.py if the VM IP changed."
    echo "       Flashing anyway; the board will show an error when you press A or C."
fi
echo

./flash.sh --monitor || pause_and_exit 1
