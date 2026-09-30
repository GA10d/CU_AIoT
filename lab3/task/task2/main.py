from machine import RTC
import time

def reset_rtc_time():
    rtc.datetime(BOOT_TIME)

# Create an object representing the ESP32 internal RTC.
rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
reset_rtc_time()


while True:
    year = rtc.datetime()[0]
    month = rtc.datetime()[1]
    day = rtc.datetime()[2]
    week = rtc.datetime()[3]
    hour = rtc.datetime()[4]
    minute = rtc.datetime()[5]
    second = rtc.datetime()[6]
    print("Current RTC time is:", year, "/", month, "/", day, " ", hour, ":", minute, ":", second)
    time.sleep(1)
