import time
from time import ticks_ms, ticks_diff
from machine import Pin, I2C, RTC, ADC, PWM, SPI
import neopixel
import ssd1306

cs=Pin(4, Pin.OUT,value=1)

spi=SPI(
    2,
    baudrate=1000000,
    polarity=1,
    phase=1,
    bits=8,
    firstbit=SPI.MSB,
    sck=Pin(5),
    mosi=Pin(19),
    miso=Pin(21)
)

DEBOUNCE_MS = 250
MODE = 0  # 0 - Normal, 1 - Time Setting, 2 - Alarm Setting, 3 - Alarm Status
ALARM_ON = False
ALARM_TRIGGERED = True
SETTING_FLAG = 0  # 0 - Second, 1 - Minute, 2 - Hour, 3 - Day, 4 - Month, 5 - Year

last_time_a = 0
last_time_b = 0
last_time_c = 0
last_displayed_second = -1
press_count_a = 0
press_count_b = 0
press_count_c = 0
alarm_output_active = False

pwr_light = Pin(13, Pin.OUT)
pwr_light.value(1)
pwr = Pin(2, Pin.OUT)
pwr.value(1)

i2c = I2C(0, scl=Pin(20), sda=Pin(22), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
CURRENT_TIME = list(BOOT_TIME)
ALARM_TIME = [2026, 10, 1, 0, 12, 0, 9, 0]

button_a = Pin(12, Pin.IN, Pin.PULL_UP)
button_b = Pin(15, Pin.IN, Pin.PULL_UP)
button_c = Pin(14, Pin.IN, Pin.PULL_UP)

alarm_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)
alarm_led[0] = (0, 0, 0)
alarm_led.write()
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=0)

offset_x = 0
offset_y = 0

TILT_THRESHOLD = 0.2
SCROLL_STEP = 2

last_accel_print = ticks_ms()

def button_a_handler(pin):
    global last_time_a, press_count_a, MODE, ALARM_ON
    now = ticks_ms()
    if ticks_diff(now, last_time_a) < DEBOUNCE_MS:
        return
    last_time_a = now

    if ALARM_ON:
        ALARM_ON = False
    else:
        press_count_a += 1
        MODE = press_count_a % 4
        if MODE == 1:
            rtc_hold()
    print("Button A pressed at {}: {}".format(now, press_count_a))


def button_b_handler(pin):
    global last_time_b, press_count_b, ALARM_ON, SETTING_FLAG
    now = ticks_ms()
    if ticks_diff(now, last_time_b) < DEBOUNCE_MS:
        return
    last_time_b = now

    if ALARM_ON:
        ALARM_ON = False
    else:
        press_count_b += 1
        print("Button B pressed at {}: {}".format(now, press_count_b))
        if MODE in (1, 2):
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
    global last_time_c, press_count_c, ALARM_ON, ALARM_TRIGGERED
    global SETTING_FLAG, CURRENT_TIME, ALARM_TIME
    now = ticks_ms()
    if ticks_diff(now, last_time_c) < DEBOUNCE_MS:
        return
    last_time_c = now
    print("Button C pressed at {}: {}".format(now, press_count_c))
    press_count_c += 1

    if ALARM_ON:
        ALARM_ON = False
    elif MODE == 1:
        if SETTING_FLAG == 0:
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], (CURRENT_TIME[6] + 1) % 60, 0]
        elif SETTING_FLAG == 1:
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], CURRENT_TIME[4], (CURRENT_TIME[5] + 1) % 60, CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 2:
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], CURRENT_TIME[2], CURRENT_TIME[3], (CURRENT_TIME[4] + 1) % 24, CURRENT_TIME[5], CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 3:
            day = (CURRENT_TIME[2] + 1) % get_days_in_month(CURRENT_TIME[0], CURRENT_TIME[1])
            if day == 0:
                day = get_days_in_month(CURRENT_TIME[0], CURRENT_TIME[1])
            CURRENT_TIME = [CURRENT_TIME[0], CURRENT_TIME[1], day, CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 4:
            month = CURRENT_TIME[1] % 12 + 1
            day = min(CURRENT_TIME[2], get_days_in_month(CURRENT_TIME[0], month))
            CURRENT_TIME = [CURRENT_TIME[0], month, day, CURRENT_TIME[3], CURRENT_TIME[4], CURRENT_TIME[5], CURRENT_TIME[6], 0]
        elif SETTING_FLAG == 5:
            pass
        rtc.datetime(CURRENT_TIME)
    elif MODE == 2:
        if SETTING_FLAG == 0:
            ALARM_TIME[6] = (ALARM_TIME[6] + 1) % 60
        elif SETTING_FLAG == 1:
            ALARM_TIME[5] = (ALARM_TIME[5] + 1) % 60
        elif SETTING_FLAG == 2:
            ALARM_TIME[4] = (ALARM_TIME[4] + 1) % 24
        elif SETTING_FLAG == 3:
            day = (ALARM_TIME[2] + 1) % get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            if day == 0:
                day = get_days_in_month(ALARM_TIME[0], ALARM_TIME[1])
            ALARM_TIME[2] = day
        elif SETTING_FLAG == 4:
            month = ALARM_TIME[1] % 12 + 1
            ALARM_TIME[1] = month
            ALARM_TIME[2] = min(ALARM_TIME[2], get_days_in_month(ALARM_TIME[0], month))
        elif SETTING_FLAG == 5:
            pass
    elif MODE == 3:
        ALARM_TRIGGERED = not ALARM_TRIGGERED


button_a.irq(trigger=Pin.IRQ_FALLING, handler=button_a_handler)
button_b.irq(trigger=Pin.IRQ_FALLING, handler=button_b_handler)
button_c.irq(trigger=Pin.IRQ_FALLING, handler=button_c_handler)


def reset_rtc_time():
    rtc.datetime(BOOT_TIME)


def execute_mode0():
    global last_displayed_second
    now = rtc.datetime()
    second = now[6]
    # if second == last_displayed_second:
    #     return

    last_displayed_second = second
    date_text = "{:04d}/{:02d}/{:02d}".format(now[0], now[1], now[2])
    time_text = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], second)
    display.fill(0)
    draw_text("Time Display", 10, 0, 1)
    draw_text(date_text, 24, 11, 1)
    draw_text(time_text, 32, 22, 1)
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
    draw_text("Time Setting", 10, 0, 1)
    draw_text(date_text, 24, 11, 1)
    draw_text(time_text, 32, 22, 1)
    display.show()


def execute_mode2():
    now = ALARM_TIME
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
    draw_text("Alarm Set", 10, 0, 1)
    draw_text(date_text, 24, 11, 1)
    draw_text(time_text, 32, 22, 1)
    display.show()


def execute_mode3():
    display.fill(0)
    if ALARM_TRIGGERED:
        draw_text("ALARM TRIGGERED", 24, 11, 1)
    else:
        draw_text("NO ALARM", 24, 11, 1)
    display.show()


def check_alarm():
    global ALARM_TRIGGERED, ALARM_ON
    if (
        ALARM_TIME[0] == rtc.datetime()[0]
        and ALARM_TIME[1] == rtc.datetime()[1]
        and ALARM_TIME[2] == rtc.datetime()[2]
        and ALARM_TIME[4] == rtc.datetime()[4]
        and ALARM_TIME[5] == rtc.datetime()[5]
        and ALARM_TIME[6] == rtc.datetime()[6]
        and ALARM_TRIGGERED
    ):
        ALARM_ON = True


def update_alarm_output(active):
    global alarm_output_active
    if active == alarm_output_active:
        return

    alarm_output_active = active
    if active:
        print("Alarm is ON")
        alarm_led[0] = (100, 100, 100)
        buzzer_pwm.duty_u16(10768)
    else:
        print("Alarm is OFF")
        alarm_led[0] = (0, 0, 0)
        buzzer_pwm.duty_u16(0)
    alarm_led.write()


light = ADC(Pin(34))
reset_rtc_time()


def read_register(address):
    buf=bytearray(1)
    cs.value(0)
    try:
        spi.write(bytearray([0x80 | address]))
        spi.readinto(buf)
    finally:
        cs.value(1)
    return buf[0]

def write_register(address, value):
    cs.value(0)
    try:
        spi.write(bytearray([address,value]))
    finally:
        cs.value(1)

def read_xyzAcceleration(address):
    buf=bytearray(6)
    cs.value(0)
    try:
        spi.write(bytearray([0x80 | 0x40 | address]))
        spi.readinto(buf)
    finally:
        cs.value(1)
    return buf


def signed_int16(low, high):
    value = (high << 8) | low

    if value >= 32768:
        value -= 65536

    return value
#confirm connection
# device_id=read_register(0x00)
# print("DEVICE ID:",hex(device_id))
# if device_id != 0xE5:
#     raise RuntimeError("device ID incorrect")

write_register(0x2D, 0x00)
write_register(0x31, 0x08)
write_register(0x2C, 0x0A)
write_register(0x2E, 0x00)
write_register(0x38, 0x00)
write_register(0x2D, 0x08)

time.sleep_ms(20)

settings = (
    (0x31, 0x08),
    (0x2C, 0x0A),
    (0x2E, 0x00),
    (0x38, 0x00),
    (0x2D, 0x08),
)

for address, expected in settings:
    actual = read_register(address)

    print("Register 0x{:02X}: 0x{:02X}".format(address, actual))

    if actual != expected:
        raise RuntimeError(
            "Register 0x{:02X} verification failed".format(address)
        )

print("Initialization OK")

def draw_text(text, x, y, color=1):
    display.text(text, x + offset_x, y + offset_y, color)


def update_scroll(x_g, y_g):
    global offset_x, offset_y

    if x_g > TILT_THRESHOLD:
        offset_x += SCROLL_STEP
    elif x_g < -TILT_THRESHOLD:
        offset_x -= SCROLL_STEP

    if y_g > TILT_THRESHOLD:
        offset_y -= SCROLL_STEP
    elif y_g < -TILT_THRESHOLD:
        offset_y += SCROLL_STEP

    if MODE == 3:
        text = "ALARM TRIGGERED" if ALARM_TRIGGERED else "NO ALARM"
        left = 24
        right = left + len(text) * 8
        top = 11
        bottom = 19
    else:
        left = 10
        right = 106
        top = 0
        bottom = 30


    if x_g > TILT_THRESHOLD and left + offset_x >= 128:
        offset_x = -right
    elif x_g < -TILT_THRESHOLD and right + offset_x <= 0:
        offset_x = 128 - left

    if y_g > TILT_THRESHOLD and bottom + offset_y <= 0:
        offset_y = 32 - top
    elif y_g < -TILT_THRESHOLD and top + offset_y >= 32:
        offset_y = -bottom

while True:

    buf = read_xyzAcceleration(0x32)

    x_g = signed_int16(buf[0], buf[1]) / 256.0
    y_g = signed_int16(buf[2], buf[3]) / 256.0
    z_g = signed_int16(buf[4], buf[5]) / 256.0

    now_ms = ticks_ms()
    if ticks_diff(now_ms, last_accel_print) >= 100:
        print(
            "X: {:.3f} g | Y: {:.3f} g | Z: {:.3f} g".format(
                x_g, y_g, z_g
            )
        )
        last_accel_print = now_ms

    update_scroll(x_g, y_g)


    raw = light.read_u16()
    contrast = max(15, raw * 255 // 65535)
    display.contrast(contrast)


    if MODE == 0:
        execute_mode0()
    elif MODE == 1:
        execute_mode1()
    elif MODE == 2:
        execute_mode2()
    else:
        execute_mode3()

    # 保留闹钟功能
    check_alarm()
    update_alarm_output(ALARM_TRIGGERED and ALARM_ON)

    time.sleep_ms(50)
