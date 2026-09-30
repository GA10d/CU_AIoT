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

# Light power LED
pwr = Pin(13, Pin.OUT)
pwr.value(1)

# Initialize I2C.
i2c = I2C(0, scl=Pin(20), sda=Pin(22), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

# Initialize RTC.
rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
ALARM_TIME = (2026, 9, 1, 0, 12, 0, 10, 0)  # Alarm time set to 10 seconds after boot
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
        print("Button pressed:", PRESS_COUNT_B)
        if MODE == 1:
            # Time setting mode
            SETTING_FLAG = (SETTING_FLAG + 1) % 6
            print("Setting flag:", SETTING_FLAG)
            pass
        elif MODE == 2:
            # Alarm setting mode
            pass
        elif MODE == 3:
            # Alarm triggered mode
            pass


def button_c_handler(pin):
    global last_time_c, PRESS_COUNT_C
    now = ticks_ms()
    if ticks_diff(now, last_time_c) < DEBOUNCE_MS:
        return
    last_time_c = now
    PRESS_COUNT_C += 1
    # print(button.value())
    print("Button pressed:", PRESS_COUNT_C)

button_a.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_a_handler
)

button_b.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_b_handler
)

button_c.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_c_handler
)

def reset_rtc_time():
    rtc.datetime(BOOT_TIME)

def read_rtc_time():
    return rtc.datetime()

# 用来记录上一次显示的秒。
last_second = -1

reset_rtc_time()
while True:
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

    # 每 100 毫秒检查一次。
    time.sleep_ms(100)