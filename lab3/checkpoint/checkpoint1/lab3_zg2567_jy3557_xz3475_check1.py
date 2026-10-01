import time
from time import ticks_ms, ticks_diff
from machine import Pin, I2C, RTC
import ssd1306

last_time_a = 0
last_time_b = 0
last_time_c = 0
last_displayed_second = -1
DEBOUNCE_MS = 250
PRESS_COUNT_A = 0
PRESS_COUNT_B = 0
PRESS_COUNT_C = 0

MODE = 0
SETTING_FLAG = 0  # 0 - Second, 1 - Minute, 2 - Hour, 3 - Day, 4 - Month, 5 - Year

pwr = Pin(13, Pin.OUT)
pwr.value(1)

i2c = I2C(0, scl=Pin(20), sda=Pin(22), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
CURRENT_TIME = list(BOOT_TIME)

button_a = Pin(12, Pin.IN, Pin.PULL_UP)
button_b = Pin(15, Pin.IN, Pin.PULL_UP)
button_c = Pin(14, Pin.IN, Pin.PULL_UP)


def button_a_handler(pin):
    global last_time_a, PRESS_COUNT_A, MODE
    now = ticks_ms()
    if ticks_diff(now, last_time_a) < DEBOUNCE_MS:
        return
    last_time_a = now
    PRESS_COUNT_A += 1
    MODE = PRESS_COUNT_A % 2
    if MODE == 1:
        rtc_hold()
    print("Button A pressed at {}: {}".format(now, PRESS_COUNT_A))


def button_b_handler(pin):
    global last_time_b, PRESS_COUNT_B, SETTING_FLAG
    now = ticks_ms()
    if ticks_diff(now, last_time_b) < DEBOUNCE_MS:
        return
    last_time_b = now
    PRESS_COUNT_B += 1
    print("Button B pressed at {}: {}".format(now, PRESS_COUNT_B))
    if MODE == 1:
        SETTING_FLAG = (SETTING_FLAG + 1) % 6


def check_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


def get_days_in_month(year, month):
    if month in [1, 3, 5, 7, 8, 10, 12]:
        return 31
    if month in [4, 6, 9, 11]:
        return 30
    if month == 2:
        return 29 if check_leap_year(year) else 28
    return 0


def rtc_hold():
    global CURRENT_TIME
    CURRENT_TIME = list(rtc.datetime())


def button_c_handler(pin):
    global last_time_c, PRESS_COUNT_C, CURRENT_TIME
    now = ticks_ms()
    if ticks_diff(now, last_time_c) < DEBOUNCE_MS:
        return
    last_time_c = now
    PRESS_COUNT_C += 1
    print("Button C pressed at {}: {}".format(now, PRESS_COUNT_C))

    if MODE != 1:
        return

    year, month, day, weekday, hour, minute, second, subseconds = CURRENT_TIME
    if SETTING_FLAG == 0:
        second = (second + 1) % 60
    elif SETTING_FLAG == 1:
        minute = (minute + 1) % 60
    elif SETTING_FLAG == 2:
        hour = (hour + 1) % 24
    elif SETTING_FLAG == 3:
        day = day % get_days_in_month(year, month) + 1
    elif SETTING_FLAG == 4:
        month = month % 12 + 1
        day = min(day, get_days_in_month(year, month))
    elif SETTING_FLAG == 5:
        year += 1
        day = min(day, get_days_in_month(year, month))

    CURRENT_TIME = [year, month, day, weekday, hour, minute, second, 0]
    rtc.datetime(CURRENT_TIME)


button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_a_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_b_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_c_handler)


def reset_rtc_time():
    rtc.datetime(BOOT_TIME)


reset_rtc_time()


def execute_mode0():
    global last_displayed_second
    now = rtc.datetime()
    year = now[0]
    month = now[1]
    day = now[2]
    hour = now[4]
    minute = now[5]
    second = now[6]

    if second != last_displayed_second:
        last_displayed_second = second
        date_text = "{:04d}/{:02d}/{:02d}".format(year, month, day)
        time_text = "{:02d}:{:02d}:{:02d}".format(hour, minute, second)
        display.fill(0)
        display.text("Time Display", 10, 0, 1)
        display.text(date_text, 24, 11, 1)
        display.text(time_text, 32, 22, 1)
        display.show()


def format_blinking_value(value, width, field_flag, blink_visible):
    if SETTING_FLAG == field_flag and not blink_visible:
        return " " * width
    if width == 4:
        return "{:04d}".format(value)
    return "{:02d}".format(value)


def execute_mode1():
    now = CURRENT_TIME
    blink_visible = (ticks_ms() // 500) % 2 == 0
    year = format_blinking_value(now[0], 4, 5, blink_visible)
    month = format_blinking_value(now[1], 2, 4, blink_visible)
    day = format_blinking_value(now[2], 2, 3, blink_visible)
    hour = format_blinking_value(now[4], 2, 2, blink_visible)
    minute = format_blinking_value(now[5], 2, 1, blink_visible)
    second = format_blinking_value(now[6], 2, 0, blink_visible)

    date_text = "{}/{}/{}".format(year, month, day)
    time_text = "{}:{}:{}".format(hour, minute, second)
    display.fill(0)
    display.text("Time Setting", 10, 0, 1)
    display.text(date_text, 24, 11, 1)
    display.text(time_text, 32, 22, 1)
    display.show()


while True:
    if MODE == 0:
        execute_mode0()
    else:
        execute_mode1()
    time.sleep(0.01)