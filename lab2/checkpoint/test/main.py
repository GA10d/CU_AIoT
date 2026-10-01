import time
from machine import Pin, I2C, RTC
import ssd1306


# -------------------- Hardware setup --------------------

# OLED/shield power.
pwr = Pin(13, Pin.OUT)
pwr.value(1)

# Keep these pins if the OLED is already working with your wiring.
i2c = I2C(0, scl=Pin(20), sda=Pin(22), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

rtc = RTC()
BOOT_TIME = (2026, 10, 1, 0, 12, 0, 0, 0)
rtc.datetime(BOOT_TIME)


# -------------------- Program states --------------------

MODE_NORMAL = 0
MODE_SET_TIME = 1
MODE_SET_ALARM = 2
MODE_ALARM_TRIGGERED = 3

MODE = MODE_NORMAL

# 0 second, 1 minute, 2 hour, 3 day, 4 month, 5 year.
SETTING_FLAG = 2

# Lists are used because tuple elements cannot be changed individually.
CURRENT_TIME = list(rtc.datetime())
ALARM_TIME = [2026, 10, 1, 0, 12, 0, 10, 0]

ALARM_ENABLED = False
ALARM_TRIGGERED = False


# -------------------- Debounced buttons --------------------

class Button:
    def __init__(self, pin_number, debounce_ms=50):
        self.pin = Pin(pin_number, Pin.IN, Pin.PULL_UP)
        self.debounce_ms = debounce_ms
        self.last_raw = self.pin.value()
        self.stable = self.last_raw
        self.changed_at = time.ticks_ms()

    def was_pressed(self):
        now = time.ticks_ms()
        raw = self.pin.value()

        if raw != self.last_raw:
            self.last_raw = raw
            self.changed_at = now

        if time.ticks_diff(now, self.changed_at) >= self.debounce_ms:
            if raw != self.stable:
                self.stable = raw

                # Buttons use pull-ups, so 0 means pressed.
                if self.stable == 0:
                    return True

        return False


button_a = Button(15)
button_b = Button(32)
button_c = Button(14)


# -------------------- Date/time helpers --------------------

def is_leap_year(year):
    return (
        (year % 4 == 0 and year % 100 != 0)
        or year % 400 == 0
    )


def days_in_month(year, month):
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31

    if month in (4, 6, 9, 11):
        return 30

    if month == 2:
        return 29 if is_leap_year(year) else 28

    return 30


def clamp_day(value):
    maximum = days_in_month(value[0], value[1])

    if value[2] > maximum:
        value[2] = maximum


def increment_selected_field(value, field):
    if field == 0:
        value[6] = (value[6] + 1) % 60

    elif field == 1:
        value[5] = (value[5] + 1) % 60

    elif field == 2:
        value[4] = (value[4] + 1) % 24

    elif field == 3:
        maximum = days_in_month(value[0], value[1])
        value[2] = value[2] % maximum + 1

    elif field == 4:
        value[1] = value[1] % 12 + 1
        clamp_day(value)

    elif field == 5:
        value[0] = 2020 if value[0] >= 2099 else value[0] + 1
        clamp_day(value)

    value[7] = 0


# -------------------- Button actions --------------------

def handle_button_a():
    global MODE
    global SETTING_FLAG
    global CURRENT_TIME
    global ALARM_ENABLED
    global ALARM_TRIGGERED

    if MODE == MODE_ALARM_TRIGGERED:
        ALARM_TRIGGERED = False
        MODE = MODE_NORMAL
        return

    if MODE == MODE_NORMAL:
        # Freeze a copy for editing; the real RTC continues running.
        CURRENT_TIME = list(rtc.datetime())
        CURRENT_TIME[7] = 0
        SETTING_FLAG = 2
        MODE = MODE_SET_TIME

    elif MODE == MODE_SET_TIME:
        # Save the edited time before entering alarm setting.
        rtc.datetime(tuple(CURRENT_TIME))
        SETTING_FLAG = 2
        MODE = MODE_SET_ALARM

    elif MODE == MODE_SET_ALARM:
        # Leaving alarm setting enables the alarm.
        ALARM_ENABLED = True
        MODE = MODE_NORMAL

    print("Mode:", MODE)


def handle_button_b():
    global SETTING_FLAG

    if MODE in (MODE_SET_TIME, MODE_SET_ALARM):
        SETTING_FLAG = (SETTING_FLAG + 1) % 6
        print("Setting field:", SETTING_FLAG)


def handle_button_c():
    if MODE == MODE_SET_TIME:
        increment_selected_field(CURRENT_TIME, SETTING_FLAG)

    elif MODE == MODE_SET_ALARM:
        increment_selected_field(ALARM_TIME, SETTING_FLAG)


# -------------------- Alarm check --------------------

def alarm_matches(now, alarm):
    return (
        now[0] == alarm[0]
        and now[1] == alarm[1]
        and now[2] == alarm[2]
        and now[4] == alarm[4]
        and now[5] == alarm[5]
        and now[6] == alarm[6]
    )


def check_alarm():
    global MODE
    global ALARM_ENABLED
    global ALARM_TRIGGERED

    if ALARM_ENABLED and alarm_matches(rtc.datetime(), ALARM_TIME):
        ALARM_ENABLED = False
        ALARM_TRIGGERED = True
        MODE = MODE_ALARM_TRIGGERED


# -------------------- OLED drawing --------------------

def format_date(value):
    return "{:04d}/{:02d}/{:02d}".format(
        value[0], value[1], value[2]
    )


def format_clock(value):
    return "{:02d}:{:02d}:{:02d}".format(
        value[4], value[5], value[6]
    )


def draw_selected_field(value, field):
    # Position and width of each editable field.
    positions = {
        0: (80, 22, 16, "{:02d}".format(value[6])),
        1: (56, 22, 16, "{:02d}".format(value[5])),
        2: (32, 22, 16, "{:02d}".format(value[4])),
        3: (88, 11, 16, "{:02d}".format(value[2])),
        4: (64, 11, 16, "{:02d}".format(value[1])),
        5: (24, 11, 32, "{:04d}".format(value[0])),
    }

    x, y, width, text = positions[field]
    display.fill_rect(x, y, width, 8, 1)
    display.text(text, x, y, 0)


def draw_datetime_screen(title, value, selected_field=None):
    display.fill(0)

    title_x = max(0, (128 - len(title) * 8) // 2)
    display.text(title, title_x, 0, 1)
    display.text(format_date(value), 24, 11, 1)
    display.text(format_clock(value), 32, 22, 1)

    if selected_field is not None:
        draw_selected_field(value, selected_field)

    display.show()


def execute_mode0():
    title = "RTC+ALARM" if ALARM_ENABLED else "RTC"
    draw_datetime_screen(title, rtc.datetime())


def execute_mode1():
    draw_datetime_screen("TIME SET", CURRENT_TIME, SETTING_FLAG)


def execute_mode2():
    draw_datetime_screen("ALARM SET", ALARM_TIME, SETTING_FLAG)


def execute_mode3():
    display.fill(0)
    display.text("ALARM!", 40, 2, 1)
    display.text("PRESS A TO STOP", 4, 18, 1)
    display.show()


# -------------------- Main loop --------------------

while True:
    if button_a.was_pressed():
        handle_button_a()

    if button_b.was_pressed():
        handle_button_b()

    if button_c.was_pressed():
        handle_button_c()

    check_alarm()

    if MODE == MODE_NORMAL:
        execute_mode0()
    elif MODE == MODE_SET_TIME:
        execute_mode1()
    elif MODE == MODE_SET_ALARM:
        execute_mode2()
    elif MODE == MODE_ALARM_TRIGGERED:
        execute_mode3()

    time.sleep_ms(50)
