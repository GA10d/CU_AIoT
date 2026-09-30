import time
from time import ticks_ms, ticks_diff
from machine import Pin, I2C, RTC
import ssd1306

last_time_a = 0
last_time_b = 0
last_time_c = 0
DEBOUNCE_MS = 50
PRESS_COUNT_A = 0
PRESS_COUNT_B = 0
PRESS_COUNT_C = 0

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
CURRENT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
ALARM_TIME = (2026, 10, 1, 0, 11, 0, 0, 0)  # Alarm time set to 10 seconds after boot
#
button_a = Pin(15, Pin.IN)
button_b = Pin(32, Pin.IN)
button_c = Pin(14, Pin.IN)

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
        print("Mode:", MODE)

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
        print("Button B pressed:", PRESS_COUNT_B)
        if MODE == 1:
            # Time setting mode
            SETTING_FLAG = (SETTING_FLAG + 1) % 6
            print("Setting flag:", SETTING_FLAG)
        elif MODE == 2:
            # Alarm setting mode
            SETTING_FLAG = (SETTING_FLAG + 1) % 6
            print("Setting flag:", SETTING_FLAG)

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

def button_c_handler(pin):
    global last_time_c, PRESS_COUNT_C, MODE, ALARM_ON, SETTING_FLAG
    now = ticks_ms()
    if ticks_diff(now, last_time_c) < DEBOUNCE_MS:
        return
    last_time_c = now
    PRESS_COUNT_C += 1
    if ALARM_ON:
        ALARM_ON = False
    elif MODE == 1:
        if SETTING_FLAG == 0:
            # Second
            rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], (rtc.datetime()[6] + 1)%60, 0))
        elif SETTING_FLAG == 1:
            # Minute
            rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], (rtc.datetime()[5] + 1)%60, rtc.datetime()[6], 0))
        elif SETTING_FLAG == 2:
            # Hour
            rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], (rtc.datetime()[4] + 1)%24, rtc.datetime()[5], rtc.datetime()[6], 0))
        elif SETTING_FLAG == 3:
            # Day
            day = (rtc.datetime()[2] + 1) % get_days_in_month(rtc.datetime()[0], rtc.datetime()[1])
            if day == 0:
                day = get_days_in_month(rtc.datetime()[0], rtc.datetime()[1])
            rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], day, rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
        elif SETTING_FLAG == 4:
            # Month
            month = (rtc.datetime()[1] + 1) % 12
            if month == 0:
                month = 12
            rtc.datetime((rtc.datetime()[0], month, rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
        elif SETTING_FLAG == 5:
            # Year
            # !!! Implement year setting
            # rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
            pass
    elif MODE == 2:
        if SETTING_FLAG == 0:
            # Second
            ALARM_TIME[1] = (ALARM_TIME[1] + 1) % 60
        elif SETTING_FLAG == 1:
            # Minute
            ALARM_TIME[2] = (ALARM_TIME[2] + 1) % 60
        elif SETTING_FLAG == 2:
            # Hour
            ALARM_TIME[3] = (ALARM_TIME[3] + 1) % 24
        elif SETTING_FLAG == 3:
            # Day
            day = (ALARM_TIME[4] + 1) % get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            if day == 0:
                day = get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            ALARM_TIME[4] = day
        elif SETTING_FLAG == 4:
            # Month
            month = (ALARM_TIME[1] + 1) % 12
            if month == 0:
                month = 12
            ALARM_TIME[1] = month
        elif SETTING_FLAG == 5:
            # Year
            # !!! Implement year setting
            # rtc.datetime((rtc.datetime()[0], rtc.datetime()[1], rtc.datetime()[2], rtc.datetime()[3], rtc.datetime()[4], rtc.datetime()[5], rtc.datetime()[6], 0))
            pass

button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_a_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_b_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_c_handler)

def reset_rtc_time():
    rtc.datetime(BOOT_TIME)

# 用来记录上一次显示的秒。
last_second = -1
reset_rtc_time()

def execute_mode0():
    now = rtc.datetime()
    year = now[0]
    month = now[1]
    day = now[2]
    hour = now[4]
    minute = now[5]
    second = now[6]

    # 只有秒数变化时才刷新 OLED。
    if second != last_second:
        last_second = second

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
        display.text("RTC", 52, 0, 1)

        # 第二行：日期。
        display.text(date_text, 24, 11, 1)

        # 第三行：时间。
        display.text(time_text, 32, 22, 1)

        # 更新屏幕。
        display.show()

        # 同时输出到串口，方便调试。
        print("Current RTC time:", date_text, time_text)

while True:
    if MODE == 0:
        FROZEN_DISPLAY = False
        execute_mode0()
    elif MODE == 1:
        if FROZEN_DISPLAY == False:
            now = rtc.datetime()
            FROZEN_DISPLAY = True
        else:
            # Time setting mode
            pass
        execute_mode1(now)        
    elif MODE == 2:
        # Alarm setting mode
        pass
    elif MODE == 3:
        # Alarm triggered mode
        pass

    # 每 100 毫秒检查一次。
    time.sleep_ms(100)