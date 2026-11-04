"""Task 3 firmware, extending the Lab 5 command server. Runs on ESP32."""
from board_config import (SSID, PASSWORD, PORT, OLED_SDA, OLED_SCL, WEATHER_API,
                          SPI_ID, ADXL_SCK, ADXL_MOSI, ADXL_MISO, ADXL_CS)
from har_sensor import ADXL345

import time
import gc
from time import ticks_ms, ticks_diff
from machine import Pin, I2C, RTC, ADC, PWM
import neopixel
import ssd1306
import network
import json
import socket
import select



rtc = RTC()
i2c = I2C(0, scl=Pin(OLED_SCL), sda=Pin(OLED_SDA), freq=400000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)
screen_enabled= True

showing_time = False
last_displayed_second = -1

ALARM_TIME = list(rtc.datetime())
ALARM_ON = False
ALARM_TRIGGERED = False
alarm_output_active = False

alarm_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)
alarm_led[0] = (0, 0, 0)
alarm_led.write()
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=0)

def show_lines(lines):
    display.fill(0)
    for row, line in enumerate(lines):
        display.text(str(line)[:16], 0, row * 8)
    if screen_enabled:
        display.show()
    display.show()

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

def wifi_connect(ssid = SSID, password = PASSWORD):

    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if not wifi.isconnected():
        if password:
            wifi.connect(ssid, password)
        else:
            wifi.connect(ssid)
        start = time.ticks_ms()
        while not wifi.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > 20000:
                raise RuntimeError("WiFi connection timed out")
            time.sleep(0.5)
    print("WiFi connected:", wifi.ifconfig())

def get_location():
    url = "http://ip-api.com/json"
    location = get_json(url)
    if location.get("status") != "success":
        raise OSError("Location lookup failed")

    lat = location["lat"]
    lon = location["lon"]
    city = location.get("city", "Unknown")
    print("City:", city)
    return lat, lon, city



def get_json(url):
    # Only the optional Lab 5 location/weather commands need this package.
    import urequests
    response = None
    try:
        response = urequests.get(url)
        print("HTTP status:", response.status_code)
        print("API response:", response.text)
        if response.status_code != 200:
            raise OSError("HTTP {}".format(response.status_code))
        return response.json()
    finally:
        if response is not None:
            response.close()

def get_weather(lat, lon, api = WEATHER_API):
    weather_url = (
        "https://api.openweathermap.org/data/2.5/weather"
        "?lat={}&lon={}&appid={}&units=metric"
    ).format(lat, lon, api)

    weather = get_json(weather_url)

    temperature = weather["main"]["temp"]
    humidity = weather["main"]["humidity"]
    description = weather["weather"][0]["main"]
    print("Temperature:", temperature, "C")
    print("Humidity:", humidity, "%")
    print("Condition:", description)
    return temperature, humidity, description



def screen_on():
    global display, screen_enabled, last_displayed_second

    if not screen_enabled:
        saved_frame = bytes(display.buffer)
        restored_display = ssd1306.SSD1306_I2C(128, 32, i2c)
        restored_display.buffer[:] = saved_frame
        display = restored_display
    else:
        display.poweron()

    screen_enabled = True

    if showing_time:
        last_displayed_second = -1
        update_time_display()
    else:
        display.show()
    display.poweron()
    display.show()
    return "Screen ON"

def screen_off():
    global screen_enabled
    display.poweroff()
    screen_enabled = False
    return "Screen OFF"

def display_text(text):
    global showing_time
    showing_time = False

    lines=text.split("\n")
    show_lines(lines[:4])

def display_time():
    global showing_time, last_displayed_second
    showing_time = True
    last_displayed_second = -1

    update_time_display()
    return "Time displayed"


def update_time_display():
    global last_displayed_second
    now = rtc.datetime()
    second = now[6]
    if second == last_displayed_second:
        return

    last_displayed_second = second
    date_text = "{:04d}/{:02d}/{:02d}".format(now[0], now[1], now[2])
    time_text = "{:02d}:{:02d}:{:02d}".format(now[4], now[5], second)
    display.fill(0)
    display.text("Time Display", 10, 0, 1)
    display.text(date_text, 24, 11, 1)
    display.text(time_text, 32, 22, 1)
    display.show()

def set_alarm(h,m,s):
    global ALARM_TIME, ALARM_ON, ALARM_TRIGGERED,showing_time
    ALARM_TIME= list(rtc.datetime())
    ALARM_TIME[4] = h
    ALARM_TIME[5] = m
    ALARM_TIME[6] = s
    ALARM_TIME[7] = 0

    ALARM_ON = False
    update_alarm_output(False)
    ALARM_TRIGGERED = True

    showing_time = False
    screen_on()
    show_lines([
        "Alarm set:",
        "{:02d}:{:02d}:{:02d}".format(
            ALARM_TIME[4],
            ALARM_TIME[5],
            ALARM_TIME[6]
        )
    ])
    return "Alarm set to {:02d}:{:02d}:{:02d}".format(h, m, s)

def display_location():
    global showing_time
    showing_time = False

    lat, lon, city = get_location()

    show_lines([
        "Location:",
        "Lat: {:.4f}".format(lat),
        "Lon: {:.4f}".format(lon),
        city
    ])

    return "Location displayed"

def display_weather():
    global showing_time
    showing_time = False

    lat, lon, city = get_location()
    temperature, humidity, description = get_weather(lat, lon)

    show_lines([
        city,
        "Temp: {:.1f} C".format(temperature),
        "Humidity: {}%".format(humidity),
        description
    ])

    return "Weather displayed"

def stop_alarm():
    global ALARM_ON, ALARM_TRIGGERED

    ALARM_ON = False
    ALARM_TRIGGERED = False
    update_alarm_output(False)

def check_alarm():
    global ALARM_ON, ALARM_TRIGGERED

    if not ALARM_TRIGGERED:
        return

    now = rtc.datetime()

    current = now[:3] + now[4:7]
    target = tuple(ALARM_TIME[:3] + ALARM_TIME[4:7])

    if current >= target:
        ALARM_ON = True
        ALARM_TRIGGERED = False
def run_watch():
    try:
        while True:
            if showing_time:
                update_time_display()

            check_alarm()
            update_alarm_output(ALARM_ON)

            time.sleep(0.01)
    finally:
        stop_alarm()


har_sensor = None


def capture_har():
    global har_sensor
    screen_on()
    display_text("HAR recording...\n50 Hz, 128 points")
    try:
        if har_sensor is None:
            har_sensor = ADXL345(SPI_ID, ADXL_SCK, ADXL_MOSI, ADXL_MISO, ADXL_CS)
        window = har_sensor.capture()
        display_text("HAR captured\nWaiting for PC")
        return window
    except Exception:
        display_text("HAR capture error\nCheck sensor")
        raise


COMMANDS = {
    "capture_HAR": (capture_har, 0),
    "screen_on": (screen_on, 0),
    "screen_off": (screen_off, 0),
    "display_text": (display_text, 1),
    "display_time": (display_time, 0),
    "set_alarm": (set_alarm, 3),
    "display_location": (display_location, 0),
    "display_weather": (display_weather, 0),
    "stop_alarm": (stop_alarm, 0),
}
def handle_command(command):
    try:
        if not isinstance(command, dict):
            raise ValueError("Command must be an object")

        name = command.get("name")
        args = command.get("args")

        if not isinstance(name, str):
            raise ValueError("name must be a string")

        if name not in COMMANDS:
            raise ValueError("Unknown command: " + name)

        if not isinstance(args, list):
            raise ValueError("args must be a list")

        function, argument_count = COMMANDS[name]

        if len(args) != argument_count:
            raise ValueError(
                "{} requires {} arguments".format(
                    name, argument_count
                )
            )

        if name == "display_text" and not isinstance(args[0], str):
            raise ValueError("Text must be a string")

        message = function(*args)

        if name == "capture_HAR":
            return {"ok": True, "data": message}

        return {
            "ok": True,
            "message": message or "Command executed"
        }

    except Exception as error:
        return {
            "ok": False,
            "message": str(error)
        }


def handle_json(raw_text):
    try:
        command = json.loads(raw_text)
    except ValueError:
        return {
            "ok": False,
            "message": "Invalid JSON"
        }

    return handle_command(command)

# PORT comes from board_config.py

def update_watch():
    if showing_time:
        update_time_display()

    check_alarm()
    update_alarm_output(ALARM_ON)

def receive_line(conn):
    poller = select.poll()
    poller.register(conn, select.POLLIN)

    data = b""
    start = time.ticks_ms()

    while True:
        update_watch()

        if time.ticks_diff(time.ticks_ms(), start) > 5000:
            raise ValueError("Request timed out")

        if not poller.poll(20):
            continue

        chunk = conn.recv(256)

        if not chunk:
            raise ValueError("Connection closed before newline")

        data += chunk

        if len(data) > 1024:
            raise ValueError("Command too long")

        if b"\n" in data:
            return data.split(b"\n", 1)[0].decode("utf-8")

class JSONSocketWriter:
    """Buffer only 512 bytes; never construct the complete response string."""
    def __init__(self, conn):
        self.conn = conn
        self.buffer = bytearray(512)
        self.view = memoryview(self.buffer)
        self.used = 0

    def write(self, data):
        for value in data:
            self.buffer[self.used] = value
            self.used += 1
            if self.used == len(self.buffer):
                self.flush()

    def flush(self):
        offset = 0
        while offset < self.used:
            sent = self.conn.send(self.view[offset:self.used])
            if not sent:
                raise OSError("Connection closed while sending response")
            offset += sent
        self.used = 0


def write_json_value(value, writer):
    # Serialize containers incrementally; json.dumps sees only individual scalars.
    if isinstance(value, dict):
        writer.write(b"{")
        first = True
        for key in value:
            if not first:
                writer.write(b",")
            first = False
            writer.write(json.dumps(key).encode("utf-8"))
            writer.write(b":")
            write_json_value(value[key], writer)
        writer.write(b"}")
    elif isinstance(value, (list, tuple)):
        writer.write(b"[")
        first = True
        for item in value:
            if not first:
                writer.write(b",")
            first = False
            write_json_value(item, writer)
        writer.write(b"]")
    else:
        writer.write(json.dumps(value).encode("utf-8"))


def send_json_line(conn, response):
    writer = JSONSocketWriter(conn)
    write_json_value(response, writer)
    writer.write(b"\n")
    writer.flush()


def handle_client(conn):
    # Isolate each request so the previous sensor window cannot stay live while
    # the next one is being allocated. A failed client must not kill the listener.
    raw_text = None
    response = None
    gc.collect()
    try:
        conn.settimeout(10)
        try:
            raw_text = receive_line(conn)
            response = handle_json(raw_text)
        except MemoryError:
            raise
        except Exception as error:
            response = {"ok": False, "message": str(error)}
        gc.collect()
        send_json_line(conn, response)
    except (OSError, MemoryError) as error:
        print("Client connection error:", error)
    finally:
        try:
            conn.close()
        finally:
            response = None
            raw_text = None
            gc.collect()


def run_server():
    wifi_connect()

    wifi = network.WLAN(network.STA_IF)
    ip = wifi.ifconfig()[0]

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        listener.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )
        listener.bind(("0.0.0.0", PORT))
        listener.listen(2)

        poller = select.poll()
        poller.register(listener, select.POLLIN)

        print("Server ready: {}:{}".format(ip, PORT))

        while True:
            update_watch()

            if not poller.poll(20):
                continue

            conn, address = listener.accept()
            handle_client(conn)
            conn = None

    finally:
        listener.close()
        stop_alarm()


if __name__ == "__main__":
    run_server()
