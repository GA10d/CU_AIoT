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

BUTTON_RELEASE = 0

LAST_TIME_DEBOUNCE = -1

# Mode related
MODE = 0 # 0 - Normal, 1 - Time Setting, 2 - Alarm Setting, 3 - Alarm Triggered
ALARM_ON = False
ALARM_TRIGGERED = False
SETTING_FLAG = 0  # 0 - Second, 1 - Minute, 2 - Hour, 3 - Day, 4 - Month, 5 - Year
FROZEN_DISPLAY = False
# Light power LED
pwr = Pin(13, Pin.OUT)
pwr.value(1)

# Initialize I2C.
i2c = I2C(0, scl=Pin(20), sda=Pin(22), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

# Initialize RTC.
rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
CURRENT_TIME = [2026, 10, 1, 0, 12, 0, 0, 0]
ALARM_TIME = [2026, 10, 1, 0, 11, 0, 0, 0]  # Alarm time set to 10 seconds after boot
#
button_a = Pin(12, Pin.IN, Pin.PULL_UP)
button_b = Pin(15, Pin.IN, Pin.PULL_UP)
button_c = Pin(14, Pin.IN, Pin.PULL_UP)

def button_a_handler(pin):
    global last_time_a, PRESS_COUNT_A, MODE, ALARM_ON
    now = ticks_ms()
    if ticks_diff(now, last_time_a) < DEBOUNCE_MS:
        return
    last_time_a = now
    if ALARM_ON:
        ALARM_ON = False
    else:
        PRESS_COUNT_A += 1
        MODE = PRESS_COUNT_A
        MODE = MODE % 4
        if MODE == 1:
            rtc_hold()
        # print("Mode:", MODE)
        print("Button A pressed at {}:".format(now), PRESS_COUNT_A)


def button_b_handler(pin):
    global last_time_b, PRESS_COUNT_B, MODE, ALARM_ON, SETTING_FLAG
    now = ticks_ms()
    if ticks_diff(now, last_time_b) < DEBOUNCE_MS:
        return
    last_time_b = now
    if ALARM_ON:
        ALARM_ON = False
    else:
        PRESS_COUNT_B += 1
        print("Button B pressed at {}: {}".format(now, PRESS_COUNT_B))
        if MODE == 1:
            # Time setting mode
            SETTING_FLAG = (SETTING_FLAG + 1) % 6
            # print("Setting flag:", SETTING_FLAG)
        elif MODE == 2:
            # Alarm setting mode
            SETTING_FLAG = (SETTING_FLAG + 1) % 6
            # print("Setting flag:", SETTING_FLAG)

def check_leap_year(year):
    # Leap year is divisible by 4, but not by 100, except when it's divisible by 400
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        return True
    return False

def get_days_in_month(year, month):
    if month in [1, 3, 5, 7, 8, 10, 12]:
        return 31
    elif month in [4, 6, 9, 11]:
        return 30
    elif month == 2:
        if check_leap_year(year):
            return 29
        else:
            return 28
    return 0

def rtc_hold():
    global CURRENT_TIME
    CURRENT_TIME = list(rtc.datetime())

def button_c_handler(pin):
    global last_time_c, PRESS_COUNT_C, MODE, ALARM_ON, SETTING_FLAG, CURRENT_TIME, ALARM_TIME, ALARM_TRIGGERED
    now = ticks_ms()
    if ticks_diff(now, last_time_c) < DEBOUNCE_MS:
        return
    last_time_c = now
    print("Button C pressed at {}: {}".format(now, PRESS_COUNT_C))
    PRESS_COUNT_C += 1
    if ALARM_ON:
        ALARM_ON = False
    elif MODE == 1:
        if SETTING_FLAG == 0:
            # Second
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], (CURRENT_TIME[6] + 1)%60, 0]
        elif SETTING_FLAG == 1:
            # Minute
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], CURRENT_TIME[4], (CURRENT_TIME[5] + 1)%60, CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 2:
            # Hour
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], (CURRENT_TIME[4] + 1) % 24, CURRENT_TIME[5], CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 3:
            # Day
            day = (CURRENT_TIME[2] + 1) % get_days_in_month(CURRENT_TIME[0], CURRENT_TIME[1])
            if day == 0:
                day = get_days_in_month(CURRENT_TIME[0], CURRENT_TIME[1])
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], day, CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 4:
            # Month
            month = (CURRENT_TIME[1] + 1) % 12
            if month == 0:
                month = 12
            day = min(CURRENT_TIME[2], get_days_in_month(CURRENT_TIME[0], month))  # Adjust day if necessary
            CURRENT_TIME = [CURRENT_TIME[0], month, day, CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], CURRENT_TIME[6], 0]

        elif SETTING_FLAG == 5:
            # Year
            # !!! Implement year setting
            # rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
            pass
        rtc.datetime(CURRENT_TIME)
    elif MODE == 2:
        if SETTING_FLAG == 0:
            # Second
            ALARM_TIME[6] = (ALARM_TIME[6] + 1) % 60
        elif SETTING_FLAG == 1:
            # Minute
            ALARM_TIME[5] = (ALARM_TIME[5] + 1) % 60
        elif SETTING_FLAG == 2:
            # Hour
            ALARM_TIME[4] = (ALARM_TIME[4] + 1) % 24
        elif SETTING_FLAG == 3:
            # Day
            day = (ALARM_TIME[2] + 1) % get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            if day == 0:
                day = get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            ALARM_TIME[2] = day
        elif SETTING_FLAG == 4:
            # Month
            month = (ALARM_TIME[1] + 1) % 12
            if month == 0:
                month = 12
            ALARM_TIME[1] = month
            ALARM_TIME[2] = min(ALARM_TIME[2], get_days_in_month(ALARM_TIME[0], ALARM_TIME[1]))  # Adjust day if necessary
        elif SETTING_FLAG == 5:
            # Year
            # !!! Implement year setting
            # rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
            pass
    elif MODE == 3:
        ALARM_TRIGGERED = not ALARM_TRIGGERED

button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_a_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_b_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_c_handler)

def reset_rtc_time():
    rtc.datetime(BOOT_TIME)

# 用来记录上一次显示的秒。
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

    # 只有秒数变化时才刷新 OLED。
    if second != last_displayed_second:
        last_displayed_second = second

        # 先把日期组合成一个字符串。
        date_text = "{:04d}/{:02d}/{:02d}".format(
            year,
            month,
            day
        )

        # 再把时间组合成一个字符串。
        time_text = "{:02d}:{:02d}:{:02d}".format(
            hour,
            minute,
            second
        )

        # 清空上一帧。
        display.fill(0)

        # 第一行：标题。
        display.text("Time Display", 10, 0, 1)

        # 第二行：日期。
        display.text(date_text, 24, 11, 1)

        # 第三行：时间。
        display.text(time_text, 32, 22, 1)

        # 更新屏幕。
        display.show()

def format_blinking_value(value, width, field_flag, blink_visible):
    # 只有 SETTING_FLAG 当前选中的字段闪烁，其他字段始终显示。
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


    # 先把日期组合成一个字符串。
    date_text = "{}/{}/{}".format(
        year,
        month,
        day
    )

    # 再把时间组合成一个字符串。
    time_text = "{}:{}:{}".format(
        hour,
        minute,
        second
    )

    # 清空上一帧。
    display.fill(0)

    # 第一行：标题。
    display.text("Time Setting", 10, 0, 1)

    # 第二行：日期。
    display.text(date_text, 24, 11, 1)

    # 第三行：时间。
    display.text(time_text, 32, 22, 1)

    # 更新屏幕。
    display.show()

    # 同时输出到串口，方便调试。

def execute_mode2():
    now = ALARM_TIME
    blink_visible = (ticks_ms() // 500) % 2 == 0
    year = format_blinking_value(now[0], 4, 5, blink_visible)
    month = format_blinking_value(now[1], 2, 4, blink_visible)
    day = format_blinking_value(now[2], 2, 3, blink_visible)
    hour = format_blinking_value(now[4], 2, 2, blink_visible)
    minute = format_blinking_value(now[5], 2, 1, blink_visible)
    second = format_blinking_value(now[6], 2, 0, blink_visible)


    # 先把日期组合成一个字符串。
    date_text = "{}/{}/{}".format(
        year,
        month,
        day
    )

    # 再把时间组合成一个字符串。
    time_text = "{}:{}:{}".format(
        hour,
        minute,
        second
    )

    # 清空上一帧。
    display.fill(0)

    # 第一行：标题。
    display.text("Alarm Set", 10, 0, 1)

    # 第二行：日期。
    display.text(date_text, 24, 11, 1)

    # 第三行：时间。
    display.text(time_text, 32, 22, 1)

    # 更新屏幕。
    display.show()

def execute_mode3():
    display.fill(0)
    if ALARM_TRIGGERED:
        display.text("ALARM TRIGGERED", 24, 11, 1)
    else:
        display.text("NO ALARM", 24, 11, 1)
    display.show()

while True:
    if MODE == 0:
        execute_mode0()
    elif MODE == 1:
        execute_mode1()        
    elif MODE == 2:
        execute_mode2()   
        # Alarm setting mode
    elif MODE == 3:
        # Alarm triggered mode
        execute_mode3()

    # 每 100 毫秒检查一次。
    time.sleep(0.01)
