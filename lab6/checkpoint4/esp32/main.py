import time

import network
import urequests
from machine import Pin, SPI, SoftI2C
import ssd1306

from device_config import WIFI_SSID, WIFI_PASSWORD, SERVER_URL, DEVICE_ID

# UCI HAR window: 128 samples at 50 Hz (2.56 s), acceleration in g.
WINDOW = 128
SAMPLE_PERIOD_US = 20000
COUNTDOWN_S = 3

# (label sent to the server, text shown on the 128x32 OLED). None = unlabeled.
LABELS = [
    (None, "NO LABEL"),
    ("WALKING", "WALKING"),
    ("WALKING_UPSTAIRS", "UPSTAIRS"),
    ("WALKING_DOWNSTAIRS", "DOWNSTAIRS"),
    ("SITTING", "SITTING"),
    ("STANDING", "STANDING"),
    ("LAYING", "LAYING"),
]

DEBOUNCE_MS = 250


def hardware_init():
    # init power control
    Pin(13, Pin.OUT).value(1)
    Pin(2, Pin.OUT).value(1)

    # init i2c and display
    i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
    display = ssd1306.SSD1306_I2C(128, 32, i2c)

    # init ADXL345 over SPI (same wiring as Lab 4)
    cs = Pin(4, Pin.OUT, value=1)
    spi = SPI(2, baudrate=1000000, polarity=1, phase=1, bits=8, firstbit=SPI.MSB,
              sck=Pin(5), mosi=Pin(19), miso=Pin(21))

    return {
        "display": display,
        "accel": ADXL345(spi, cs),
        "button_a": Pin(12, Pin.IN, Pin.PULL_UP),
        "button_b": Pin(15, Pin.IN, Pin.PULL_UP),
    }


class ADXL345:
    # FULL_RES keeps 3.9 mg/LSB (256 LSB/g) at every range.
    LSB_PER_G = 256

    def __init__(self, spi, cs):
        self.spi = spi
        self.cs = cs
        self._buf = bytearray(6)
        if self._read_register(0x00) != 0xE5:
            raise RuntimeError("ADXL345 not found (device ID mismatch)")
        self._write_register(0x2D, 0x00)  # standby while configuring
        self._write_register(0x31, 0x09)  # FULL_RES, +/-4 g (walking peaks can pass 2 g)
        self._write_register(0x2C, 0x09)  # output data rate 50 Hz
        self._write_register(0x2E, 0x00)  # no interrupts
        self._write_register(0x38, 0x00)  # FIFO bypass
        self._write_register(0x2D, 0x08)  # measure

    def _read_register(self, address):
        buf = bytearray(1)
        self.cs.value(0)
        try:
            self.spi.write(bytearray([0x80 | address]))
            self.spi.readinto(buf)
        finally:
            self.cs.value(1)
        return buf[0]

    def _write_register(self, address, value):
        self.cs.value(0)
        try:
            self.spi.write(bytearray([address, value]))
        finally:
            self.cs.value(1)

    @staticmethod
    def _signed_int16(low, high):
        value = (high << 8) | low
        return value - 65536 if value >= 32768 else value

    def read_g(self):
        """Return (x, y, z) acceleration in g."""
        buf = self._buf
        self.cs.value(0)
        try:
            self.spi.write(bytearray([0x80 | 0x40 | 0x32]))
            self.spi.readinto(buf)
        finally:
            self.cs.value(1)
        return (self._signed_int16(buf[0], buf[1]) / self.LSB_PER_G,
                self._signed_int16(buf[2], buf[3]) / self.LSB_PER_G,
                self._signed_int16(buf[4], buf[5]) / self.LSB_PER_G)


def show_lines(display, lines):
    display.fill(0)
    for row, line in enumerate(lines[:4]):
        display.text(line[:16], 0, row * 8)
    display.show()


def connect_wifi(display, timeout_s=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        show_lines(display, ["Connecting WiFi"])
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(timeout_s):
            if wlan.isconnected():
                break
            time.sleep(1)
    if not wlan.isconnected():
        raise OSError("WiFi timeout")
    print("WiFi connected:", wlan.ifconfig())
    return wlan


def record_window(accel):
    """Sample WINDOW points at 50 Hz and return channels-first [[x...], [y...], [z...]]."""
    xs, ys, zs = [], [], []
    next_t = time.ticks_us()
    for _ in range(WINDOW):
        while time.ticks_diff(next_t, time.ticks_us()) > 0:
            pass
        x, y, z = accel.read_g()
        xs.append(round(x, 4))
        ys.append(round(y, 4))
        zs.append(round(z, 4))
        next_t = time.ticks_add(next_t, SAMPLE_PERIOD_US)
    return [xs, ys, zs]


def post_json(path, payload, timeout=15):
    response = urequests.post(SERVER_URL + path, json=payload, timeout=timeout)
    try:
        if response.status_code != 200:
            raise OSError("HTTP {}".format(response.status_code))
        return response.json()
    finally:
        response.close()


def collect_and_classify(hardware, label_index):
    """Record one window, send it to /classify, and show NormWear's prediction."""
    display = hardware["display"]
    label, short = LABELS[label_index]

    for remaining in range(COUNTDOWN_S, 0, -1):
        show_lines(display, ["True: " + short, "Start in {}s".format(remaining)])
        time.sleep(1)

    show_lines(display, ["True: " + short, "Recording..."])
    start = time.ticks_ms()
    acc = record_window(hardware["accel"])
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    print("Recorded {} samples in {} ms".format(WINDOW, elapsed))

    show_lines(display, ["True: " + short, "Classifying..."])
    # label is only logged on the server for the report; the model never sees it.
    payload = {"device": DEVICE_ID, "label": label, "fs": 50, "acc": acc}
    try:
        result = post_json("/classify", payload, timeout=30)
    except Exception as error:
        print("Classify failed:", error)
        show_lines(display, ["Classify failed", str(error)[:16]])
        return
    print("Server:", result)
    show_lines(display, ["Pred:", result["short"],
                         "conf {}%".format(round(result["confidence"] * 100)),
                         "A:again B:label"])


def pressed(button, last_ms):
    now = time.ticks_ms()
    if button.value() == 0 and time.ticks_diff(now, last_ms) > DEBOUNCE_MS:
        return now
    return None


def main():
    hardware = hardware_init()
    display = hardware["display"]
    connect_wifi(display)

    label_index = 0
    last_a = last_b = time.ticks_ms()
    show_lines(display, ["True: " + LABELS[label_index][1], "A:classify", "B:true label"])

    while True:
        t = pressed(hardware["button_b"], last_b)
        if t is not None:
            last_b = t
            label_index = (label_index + 1) % len(LABELS)
            show_lines(display, ["True: " + LABELS[label_index][1], "A:classify", "B:true label"])

        t = pressed(hardware["button_a"], last_a)
        if t is not None:
            collect_and_classify(hardware, label_index)
            last_a = time.ticks_ms()

        time.sleep_ms(10)


if __name__ == "__main__":
    main()
