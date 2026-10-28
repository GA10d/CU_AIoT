"""MicroPython ADXL345 SPI acquisition: raw total acceleration in g."""
import gc
import time
from machine import Pin, SPI


class ADXL345:
    def __init__(self, spi_id=2, sck=5, mosi=19, miso=21, cs=4):
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.spi = SPI(spi_id, baudrate=1000000, polarity=1, phase=1,
                       bits=8, firstbit=SPI.MSB,
                       sck=Pin(sck), mosi=Pin(mosi), miso=Pin(miso))
        self.buf = bytearray(6)
        if self.read_register(0x00) != 0xE5:
            raise OSError("ADXL345 not found (expected DEVID 0xE5); check SPI pins")
        self.write_register(0x2D, 0x00)  # standby while configuring
        self.write_register(0x31, 0x09)  # full resolution, right justified, +/-4 g
        self.write_register(0x2C, 0x09)  # 50 Hz output data rate
        self.write_register(0x2E, 0x00)  # poll status; no interrupt wire needed
        self.write_register(0x38, 0x00)  # FIFO bypass
        self.write_register(0x2D, 0x08)  # measurement mode
        time.sleep_ms(100)
        for address, expected in ((0x31, 0x09), (0x2C, 0x09), (0x2D, 0x08)):
            if self.read_register(address) != expected:
                raise OSError("ADXL345 register configuration failed")

    def read_register(self, address):
        self.cs.value(0)
        try:
            self.spi.write(bytes([0x80 | address]))
            return self.spi.read(1)[0]
        finally:
            self.cs.value(1)

    def write_register(self, address, value):
        self.cs.value(0)
        try:
            self.spi.write(bytes([address, value]))
        finally:
            self.cs.value(1)

    def read_xyz_g(self):
        self.cs.value(0)
        try:
            self.spi.write(b"\xf2")  # read + multi-byte + DATAX0 (0x32)
            self.spi.readinto(self.buf)
        finally:
            self.cs.value(1)
        values = []
        for i in (0, 2, 4):
            value = self.buf[i] | (self.buf[i + 1] << 8)
            if value >= 32768:
                value -= 65536
            values.append(value / 256.0)
        return values

    def capture(self):
        """Read each new sample once; preserve observed read times for QA."""
        channels = [[0.0] * 128 for _ in range(3)]
        timestamps = [0] * 128
        gc.collect()
        self.read_xyz_g()  # discard a stale measurement and clear DATA_READY
        start = time.ticks_us()
        overruns = 0
        for i in range(128):
            wait_start = time.ticks_us()
            while True:
                status = self.read_register(0x30)
                if status & 0x80:
                    break
                if time.ticks_diff(time.ticks_us(), wait_start) > 250000:
                    raise OSError("ADXL345 DATA_READY timeout")
                time.sleep_ms(1)
            # In bypass mode OVERRUN means an unread measurement was replaced.
            if status & 0x01:
                overruns += 1
            xyz = self.read_xyz_g()
            timestamps[i] = time.ticks_diff(time.ticks_us(), start)
            for axis in range(3):
                channels[axis][i] = round(xyz[axis], 4)
        span_us = timestamps[-1] - timestamps[0]
        gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, 128)]
        elapsed_us = time.ticks_diff(time.ticks_us(), start)
        first = timestamps[0]
        return {
            "device": "ESP32 + ADXL345",
            "sampling_rate_hz": 50,
            "num_samples": 128,
            "units": "g",
            "channels": ["total_acc_x", "total_acc_y", "total_acc_z"],
            "data": channels,
            "timestamps_us": [t - first for t in timestamps],
            "effective_rate_hz": round(127000000.0 / span_us, 3),
            "elapsed_ms": round(elapsed_us / 1000.0, 3),
            "max_gap_ms": round(max(gaps) / 1000.0, 3),
            "overruns": overruns,
            "range_g": 4,
        }
