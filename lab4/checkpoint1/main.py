from machine import Pin, SPI
import time

# --- SPI Setup ---
# Try the provided MSP pins on Feather Huzzah ESP32
spi = SPI(1, baudrate=5000000, polarity=1, phase=1, sck=Pin(5), mosi=Pin(18), miso=Pin(19))

cs = Pin(15, Pin.OUT)
cs.value(1)  # Deselect device by default

# SPI Commands
SPI_READ = 1 << 7
SPI_SINGLE_BYTE = 0 << 6

# --- Test Device ID ---
def read_device_id():
	cs.value(0)
	spi.write(bytearray([SPI_READ | SPI_SINGLE_BYTE | 0x00]))  # DEVID register = 0x00
	buf = bytearray(1)
	spi.readinto(buf)
	cs.value(1)
	return buf[0]


# Run
device_id = read_device_id()
print(f"[TEST] Device ID read: {device_id:#04x}")

if device_id == 0xE5:
	print("[TEST] ADXL345 detected successfully!")
else:
	print("[TEST] ADXL345 not detected. Check wiring and SPI pins!")
