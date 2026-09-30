from machine import RTC
import time

def reset_rtc_time():
    rtc.datetime(BOOT_TIME)

# Create an object representing the ESP32 internal RTC.
rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)

reset_rtc_time()
print("RTC time has been reset to:", rtc.datetime())