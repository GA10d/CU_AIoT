"""Lab 5 Checkpoint 4 - ESP32 smartwatch server (MicroPython).

Receives one newline-terminated JSON command per TCP connection, e.g.
    {"name": "set_alarm", "args": [16, 30]}
executes it on the watch and replies with one JSON line:
    {"ok": true, "command": "set_alarm", "result": {...}}
    {"ok": false, "error": {"code": "...", "message": "..."}}

Upload to the board as main.py so it runs on boot (ssd1306.py must already be on the board):
    mpremote fs cp server.py :main.py
"""
import errno
import json
import socket
import time
from time import ticks_diff, ticks_ms

from machine import Pin, PWM, RTC, SoftI2C
import neopixel
import network
import ntptime
import ssd1306
import urequests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Fill these in before uploading. A device_config.py on the board, if present,
# overrides them so real credentials do not have to live in this file.
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"
WEATHER_API_KEY = "your_openweathermap_key"
SERVER_PORT = 8080
try:
    from device_config import WIFI_SSID, WIFI_PASSWORD, WEATHER_API_KEY, SERVER_PORT
except ImportError:
    pass

# Optional RTC tuple: (year, month, day, weekday, hour, minute, second, subseconds).
# None preserves the device's existing RTC instead of resetting it at every boot.
# When NTP_SYNC is on, the RTC is overwritten with real time after Wi-Fi connects.
RTC_START_TIME = None

# Real time from the internet. UTC_OFFSET_HOURS is the standard-time offset
# (New York = -5); USE_US_DST adds one hour during US daylight saving time.
NTP_SYNC = True
UTC_OFFSET_HOURS = -5
USE_US_DST = True
COMMAND_LIST = {}


# ---------------------------------------------------------------------------
# JSON command protocol (must match app.py)
# ---------------------------------------------------------------------------

COMMAND_ARG_COUNTS = {
    "screen_on": 0,
    "screen_off": 0,
    "display_time": 0,
    "set_alarm": 2,
    "display_text": 1,
    "display_location": 0,
    "display_weather": 0,
}


class CommandError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_command(command):
    if not isinstance(command, dict) or set(command) != {"name", "args"}:
        raise CommandError("invalid_command", "Expected a JSON object with name and args")
    name, args = command["name"], command["args"]
    if not isinstance(name, str) or name not in COMMAND_ARG_COUNTS:
        raise CommandError("unknown_command", "Unknown command: {}".format(name))
    if not isinstance(args, list) or len(args) != COMMAND_ARG_COUNTS[name]:
        raise CommandError("invalid_arguments", "{} requires {} arguments".format(
            name, COMMAND_ARG_COUNTS[name]))
    if name == "set_alarm":
        hour, minute = args
        if (type(hour) is not int or type(minute) is not int
                or not 0 <= hour < 24 or not 0 <= minute < 60):
            raise CommandError("invalid_arguments", "Alarm needs hour 0-23 and minute 0-59")
    elif name == "display_text":
        text = args[0]
        if not isinstance(text, str):
            raise CommandError("invalid_arguments", "Text must be a string")
        if any(c not in "\r\n\t" and not 32 <= ord(c) <= 126 for c in text):
            raise CommandError("invalid_arguments", "OLED font supports ASCII text only")
    return command


# ---------------------------------------------------------------------------
# NTP time sync
# ---------------------------------------------------------------------------
# ntptime gives UTC. Add a fixed UTC offset plus, optionally, US daylight saving
# time (second Sunday of March to first Sunday of November, switching at 02:00
# local), so the clock shows e.g. New York time.

def _weekday(year, month, day):
    """0 = Monday ... 6 = Sunday (same convention as time.gmtime)."""
    offsets = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if month < 3:
        year -= 1
    sunday_based = (year + year // 4 - year // 100 + year // 400
                    + offsets[month - 1] + day) % 7
    return (sunday_based + 6) % 7


def _nth_sunday(year, month, n):
    first = _weekday(year, month, 1)
    first_sunday = 1 + (6 - first) % 7
    return first_sunday + 7 * (n - 1)


def us_dst_active(utc, std_offset_hours):
    """True if US DST is in effect at the given UTC time tuple (Y, M, D, h, ...)."""
    year, month, day, hour = utc[0], utc[1], utc[2], utc[3]
    if month < 3 or month > 11:
        return False
    if 3 < month < 11:
        return True
    if month == 3:
        # 02:00 standard time -> UTC
        start_day, start_hour = _nth_sunday(year, 3, 2), 2 - std_offset_hours
        return (day, hour) >= (start_day, start_hour)
    # November: 02:00 daylight time -> UTC
    end_day, end_hour = _nth_sunday(year, 11, 1), 2 - (std_offset_hours + 1)
    return (day, hour) < (end_day, end_hour)


def local_offset_seconds(utc, std_offset_hours, use_us_dst):
    hours = std_offset_hours
    if use_us_dst and us_dst_active(utc, std_offset_hours):
        hours += 1
    return int(hours * 3600)


def sync_rtc(rtc, std_offset_hours=-5, use_us_dst=True, host="pool.ntp.org", attempts=3):
    """Set rtc to local time. Returns the local time tuple, or None if NTP failed.

    Never raises on network errors, so a missing NTP reply does not stop the
    command server from starting; the RTC just keeps its previous value.
    """
    ntptime.host = host
    for attempt in range(attempts):
        try:
            utc_seconds = ntptime.time()
            break
        except Exception as error:
            print("NTP attempt {} failed: {}".format(attempt + 1, error))
            time.sleep(1)
    else:
        print("NTP sync failed; keeping the current RTC time")
        return None

    utc = time.gmtime(utc_seconds)
    local = time.gmtime(utc_seconds + local_offset_seconds(utc, std_offset_hours, use_us_dst))
    # gmtime: (Y, M, D, h, m, s, weekday, yearday); RTC: (Y, M, D, weekday, h, m, s, subsec)
    rtc.datetime((local[0], local[1], local[2], local[6], local[3], local[4], local[5], 0))
    print("RTC synced from NTP: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*local[:6]))
    return local


# ---------------------------------------------------------------------------
# Clock and alarm
# ---------------------------------------------------------------------------

class TimeAlarmDisplay:
    """Command-driven clock and one-shot alarm; hardware comes from hardware_init()."""

    def __init__(self, display, rtc, alarm_led, buzzer_pwm, alarm_duration_ms=10000):
        if alarm_duration_ms <= 0:
            raise ValueError("Alarm duration must be positive")
        self.display = display
        self.rtc = rtc
        self.alarm_led = alarm_led
        self.buzzer_pwm = buzzer_pwm
        self.alarm_duration_ms = alarm_duration_ms
        self._view = None
        self._last_frame = None
        self._alarm_time = None
        self._enabled = False
        self._ringing = False
        self._triggered = False
        self._ring_started_ms = None
        self._confirmation_started_ms = None

    @staticmethod
    def _datetime_key(value):
        return (value[0], value[1], value[2], value[4], value[5], value[6])

    @staticmethod
    def _days_in_month(year, month):
        if month == 2:
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            return 29 if leap else 28
        return 30 if month in (4, 6, 9, 11) else 31

    def _next_day(self, value):
        value[2] += 1
        value[3] = (value[3] + 1) % 7
        if value[2] > self._days_in_month(value[0], value[1]):
            value[2] = 1
            value[1] += 1
            if value[1] > 12:
                value[1] = 1
                value[0] += 1

    @staticmethod
    def _date_text(value):
        return "{:04d}-{:02d}-{:02d}".format(*value[:3])

    @staticmethod
    def _time_text(value):
        return "{:02d}:{:02d}:{:02d}".format(*value[4:7])

    def display_time(self):
        """Select the clock view. main() must keep calling update()."""
        self._view = "time"
        self._confirmation_started_ms = None
        self._last_frame = None
        now = self.rtc.datetime()
        self._service_alarm(now)
        self._render(now)
        return {"date": self._date_text(now), "time": self._time_text(now)}

    def set_alarm(self, hour, minute):
        """Set an HH:MM alarm; show confirmation for 3 seconds, then the clock."""
        for value, limit in ((hour, 24), (minute, 60)):
            if type(value) is not int or not 0 <= value < limit:
                raise ValueError("Invalid alarm time")

        now = self.rtc.datetime()
        alarm = list(now)
        alarm[4], alarm[5], alarm[6], alarm[7] = hour, minute, 0, 0
        if self._datetime_key(alarm) <= self._datetime_key(now):
            self._next_day(alarm)

        self._set_ringing(False)
        self._alarm_time = alarm
        self._enabled = True
        self._triggered = False
        self._ring_started_ms = None
        self._view = "alarm_confirmation"
        self._confirmation_started_ms = ticks_ms()
        self._last_frame = None
        self._render(now)
        return {
            "enabled": self._enabled,
            "ringing": self._ringing,
            "triggered": self._triggered,
            "date": self._date_text(self._alarm_time) if self._alarm_time else None,
            "time": self._time_text(self._alarm_time) if self._alarm_time else None,
        }

    def pause_display(self):
        """Give weather/location/text control of the OLED while alarm checks continue."""
        self._view = None
        self._confirmation_started_ms = None

    def _set_ringing(self, active):
        if active == self._ringing:
            return
        self._ringing = active
        self.alarm_led[0] = (100, 100, 100) if active else (0, 0, 0)
        self.alarm_led.write()
        self.buzzer_pwm.duty_u16(10768 if active else 0)

    def _service_alarm(self, now):
        # >= catches an alarm even if a synchronous request delayed update().
        if self._enabled and self._datetime_key(now) >= self._datetime_key(self._alarm_time):
            self._enabled = False
            self._triggered = True
            self._ring_started_ms = ticks_ms()
            self._set_ringing(True)
        if (self._ringing and ticks_diff(ticks_ms(), self._ring_started_ms)
                >= self.alarm_duration_ms):
            self._set_ringing(False)

    def _render(self, now):
        if self._view == "time":
            frame = ("time", self._datetime_key(now))
        elif self._view == "alarm_confirmation":
            frame = ("alarm_confirmation", self._date_text(self._alarm_time),
                     self._time_text(self._alarm_time))
        else:
            return
        if frame == self._last_frame:
            return
        self._last_frame = frame

        self.display.fill(0)
        if self._view == "time":
            self.display.text("Time Display", 10, 0, 1)
            self.display.text(self._date_text(now).replace("-", "/"), 24, 11, 1)
            self.display.text(self._time_text(now), 32, 22, 1)
        else:
            self.display.text("Alarm enabled", 0, 0)
            self.display.text(self._date_text(self._alarm_time), 0, 8)
            self.display.text(self._time_text(self._alarm_time), 0, 16)
        self.display.show()

    def update(self):
        """Poll alarm and refresh the selected view; call every ~10 ms."""
        now = self.rtc.datetime()
        self._service_alarm(now)
        if (self._view == "alarm_confirmation"
                and ticks_diff(ticks_ms(), self._confirmation_started_ms) >= 3000):
            self._view = "time"
            self._confirmation_started_ms = None
            self._last_frame = None
        self._render(now)

    def close(self):
        """Silence the buzzer/LED when main exits."""
        self._enabled = False
        self.pause_display()
        self._set_ringing(False)


# ---------------------------------------------------------------------------
# Location and weather
# ---------------------------------------------------------------------------

class LocationWeatherDisplay:
    """Look up IP-based location and current weather on a shared OLED."""

    def __init__(self, display, ssid, password="", weather_api_key="", wifi_timeout=30):
        self.display = display
        self.ssid = ssid
        self.password = password
        self.weather_api_key = weather_api_key
        self.wifi_timeout = wifi_timeout
        self._wlan = network.WLAN(network.STA_IF)

    def _show_lines(self, lines):
        self.display.fill(0)
        for row, line in enumerate(lines[:4]):
            self.display.text(str(line)[:16], 0, row * 8)
        self.display.show()

    def _connect_wifi(self):
        if self._wlan.isconnected():
            return

        self._show_lines(["Connecting WiFi"])
        self._wlan.active(True)
        self._wlan.connect(self.ssid, self.password)

        for _ in range(self.wifi_timeout):
            if self._wlan.isconnected():
                break
            time.sleep(1)

        if not self._wlan.isconnected():
            raise OSError("WiFi timeout")

        print("WiFi connected:", self._wlan.ifconfig())

    def connect_wifi(self):
        """Connect once and return the IP for the command server."""
        self._connect_wifi()
        return self._wlan.ifconfig()[0]

    def _get_json(self, url):
        response = None
        try:
            response = urequests.get(url)
            if response.status_code != 200:
                raise OSError("HTTP {}".format(response.status_code))
            return response.json()
        finally:
            if response is not None:
                response.close()

    def _get_location(self):
        self._connect_wifi()
        data = self._get_json("http://ip-api.com/json")
        if data.get("status") != "success":
            raise OSError("Location lookup failed")
        return {
            "latitude": data["lat"],
            "longitude": data["lon"],
            "city": data.get("city", "Unknown"),
        }

    def display_location(self):
        """Show latitude/longitude and return the location dictionary."""
        try:
            location = self._get_location()
            self._show_lines([
                "Location:",
                "Lat: {}".format(location["latitude"]),
                "Lon: {}".format(location["longitude"]),
            ])
            print("Location:", location)
            return location
        except Exception as error:
            self._show_lines(["Location failed", str(error)])
            raise

    def display_weather(self):
        """Show local weather in Celsius and return its dictionary."""
        try:
            if not self.weather_api_key:
                raise ValueError("Missing API key")

            location = self._get_location()
            weather_url = (
                "https://api.openweathermap.org/data/2.5/weather"
                "?lat={}&lon={}&appid={}&units=metric"
            ).format(
                location["latitude"], location["longitude"], self.weather_api_key
            )
            data = self._get_json(weather_url)
            weather = {
                "city": location["city"],
                "temperature": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "condition": data["weather"][0]["main"],
            }
            self._show_lines([
                weather["city"],
                "Temp: {:.1f} C".format(weather["temperature"]),
                "Humidity: {}%".format(weather["humidity"]),
                weather["condition"],
            ])
            print("Weather:", weather)
            return weather
        except Exception as error:
            self._show_lines(["Weather failed", str(error)])
            raise


# ---------------------------------------------------------------------------
# Text messages
# ---------------------------------------------------------------------------

class TextDisplay:
    """Display ASCII text using the OLED's built-in 8x8 font."""

    def __init__(self, display):
        self.display = display
        self.columns = display.width // 8
        self.rows = display.height // 8
        if self.columns < 3 or self.rows < 1:
            raise ValueError("Display is too small for text")

    def display_text(self, text):
        """Replace the OLED contents, wrapping text and clipping excess lines."""
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        if any(char != "\n" and not 32 <= ord(char) <= 126 for char in text):
            raise ValueError("OLED font supports ASCII text only")

        lines = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
            else:
                for start in range(0, len(paragraph), self.columns):
                    lines.append(paragraph[start:start + self.columns])

        truncated = len(lines) > self.rows
        visible = lines[:self.rows]
        if truncated:
            visible[-1] = visible[-1][:self.columns - 3] + "..."

        self.display.fill(0)
        for row, line in enumerate(visible):
            self.display.text(line, 0, row * 8, 1)
        self.display.show()
        return {"text": "\n".join(visible), "truncated": truncated}


# ---------------------------------------------------------------------------
# TCP command server
# ---------------------------------------------------------------------------

class CommandServer:
    """One newline-terminated JSON command/reply per connection.

    Call poll() from main's loop. Idle clients and partial packets do not block
    the clock. Command handlers themselves run synchronously.
    """

    def __init__(self, execute_command, host="0.0.0.0", port=8080,
                 client_timeout_ms=5000, max_request_bytes=1024):
        self.execute_command = execute_command
        self.host = host
        self.port = port
        self.client_timeout_ms = client_timeout_ms
        self.max_request_bytes = max_request_bytes
        self._listener = None
        self._client = None
        self._received = bytearray()
        self._outgoing = None
        self._sent = 0
        self._last_activity = 0

    @staticmethod
    def _would_block(error):
        return bool(error.args) and error.args[0] in (
            errno.EAGAIN, getattr(errno, "EWOULDBLOCK", errno.EAGAIN))

    def start(self):
        if self._listener is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            address = socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                                         socket.SOCK_STREAM)[0][-1]
            listener.bind(address)
            listener.listen(2)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self._listener = listener

    def _close_client(self):
        if self._client is not None:
            self._client.close()
        self._client = None
        self._received = bytearray()
        self._outgoing = None
        self._sent = 0

    def close(self):
        self._close_client()
        if self._listener is not None:
            self._listener.close()
            self._listener = None

    def _reply(self, payload):
        try:
            self._outgoing = json.dumps(payload).encode() + b"\n"
        except (TypeError, ValueError):
            self._outgoing = json.dumps({"ok": False, "error": {
                "code": "execution_failed", "message": "Result is not JSON serializable"
            }}).encode() + b"\n"
        self._sent = 0
        self._last_activity = ticks_ms()

    def _error(self, code, message):
        self._reply({"ok": False, "error": {"code": code, "message": message}})

    def _read_request(self):
        try:
            chunk = self._client.recv(256)
        except OSError as error:
            if not self._would_block(error):
                self._close_client()
            return
        if chunk is None:
            return
        if not chunk:
            self._close_client()
            return
        self._last_activity = ticks_ms()
        self._received.extend(chunk)
        end = self._received.find(b"\n")
        if end < 0:
            if len(self._received) > self.max_request_bytes:
                self._error("request_too_large", "Command exceeds size limit")
            return
        if end > self.max_request_bytes:
            self._error("request_too_large", "Command exceeds size limit")
            return
        try:
            command = json.loads(bytes(self._received[:end]).decode())
        except ValueError:
            self._error("invalid_json", "Request must contain valid UTF-8 JSON")
            return
        try:
            validate_command(command)
            result = self.execute_command(command)
        except CommandError as error:
            self._error(error.code, str(error))
        except (TypeError, ValueError) as error:
            self._error("invalid_arguments", str(error))
        except Exception as error:
            self._error("execution_failed", str(error))
        else:
            self._reply({"ok": True, "command": command["name"], "result": result})

    def _send_response(self):
        try:
            sent = self._client.send(self._outgoing[self._sent:self._sent + 256])
        except OSError as error:
            if not self._would_block(error):
                self._close_client()
            return
        if sent is None:
            return
        if sent == 0:
            self._close_client()
            return
        self._sent += sent
        self._last_activity = ticks_ms()
        if self._sent == len(self._outgoing):
            self._close_client()

    def poll(self):
        if self._listener is None:
            raise RuntimeError("Server has not started")
        if self._client is None:
            try:
                client, _ = self._listener.accept()
            except OSError as error:
                if self._would_block(error):
                    return
                raise
            try:
                client.setblocking(False)
            except Exception:
                client.close()
                return
            self._client = client
            self._last_activity = ticks_ms()
        if ticks_diff(ticks_ms(), self._last_activity) >= self.client_timeout_ms:
            if self._outgoing is None:
                self._error("request_timeout", "No complete command received before timeout")
            else:
                self._close_client()
            return
        if self._outgoing is None:
            self._read_request()
        else:
            self._send_response()


# ---------------------------------------------------------------------------
# Hardware / command registry / main loop
# ---------------------------------------------------------------------------

def hardware_init():
    # init power control
    pwr_light = Pin(13, Pin.OUT)
    pwr_light.value(1)
    pwr = Pin(2, Pin.OUT)
    pwr.value(1)

    # init i2c and display
    i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
    display = ssd1306.SSD1306_I2C(128, 32, i2c)
    rtc = RTC()
    if RTC_START_TIME is not None:
        rtc.datetime(RTC_START_TIME)

    # init alarm led and buzzer
    alarm_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)
    alarm_led[0] = (0, 0, 0)
    alarm_led.write()
    buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=0)

    return {
        "display": display,
        "rtc": rtc,
        "alarm_led": alarm_led,
        "buzzer_pwm": buzzer_pwm,
        "pwr_light": pwr_light,
        "pwr": pwr,
    }


def init_screen_system(hardware):
    display = hardware["display"]

    def screen_on():
        # The installed SSD1306_I2C.poweron() is a no-op.
        # Send Display ON directly, preserving the current framebuffer.
        display.write_cmd(0xAF)
        display.show()
        return {"screen": "on"}

    def screen_off():
        display.poweroff()
        return {"screen": "off"}

    COMMAND_LIST.update({
        "screen_on": screen_on,
        "screen_off": screen_off,
    })


def init_time_alarm_system(hardware):
    clock = TimeAlarmDisplay(
        display=hardware["display"],
        rtc=hardware["rtc"],
        alarm_led=hardware["alarm_led"],
        buzzer_pwm=hardware["buzzer_pwm"],
        alarm_duration_ms=10000,
    )
    COMMAND_LIST.update({
        "display_time": clock.display_time,
        "set_alarm": clock.set_alarm,
    })
    return clock


def init_weather_location_system(hardware, clock):
    info = LocationWeatherDisplay(
        display=hardware["display"],
        ssid=WIFI_SSID,
        password=WIFI_PASSWORD,
        weather_api_key=WEATHER_API_KEY,
    )

    def display_weather():
        clock.pause_display()
        return info.display_weather()

    def display_location():
        clock.pause_display()
        return info.display_location()

    COMMAND_LIST.update({
        "display_weather": display_weather,
        "display_location": display_location,
    })
    return info


def init_text_system(hardware, clock):
    text_display = TextDisplay(hardware["display"])

    def display_text(text):
        result = text_display.display_text(text)
        clock.pause_display()
        return result

    COMMAND_LIST.update({"display_text": display_text})
    return text_display


def software_init(hardware):
    COMMAND_LIST.clear()
    init_screen_system(hardware)
    clock = init_time_alarm_system(hardware)
    info = init_weather_location_system(hardware, clock)
    text_display = init_text_system(hardware, clock)
    return {"time_alarm": clock, "weather_location": info, "text": text_display}


def execute_command(command, args=None):
    if not isinstance(command, dict):
        if isinstance(args, tuple):
            args = list(args)
        command = {"name": command, "args": [] if args is None else args}
    validate_command(command)
    handler = COMMAND_LIST.get(command["name"])
    if handler is None:
        raise ValueError("Command is not initialized: {}".format(command["name"]))
    return handler(*command["args"])


def init_command_server(systems, hardware):
    ip = systems["weather_location"].connect_wifi()
    if NTP_SYNC:
        sync_rtc(hardware["rtc"], UTC_OFFSET_HOURS, USE_US_DST)
    server = CommandServer(execute_command, port=SERVER_PORT)
    server.start()
    print("Smartwatch server listening on {}:{}".format(ip, SERVER_PORT))
    print("Set WATCH_HOST={} in the computer's .env file".format(ip))
    return server


def main(command="display_time", args=None, serve=True):
    hardware = hardware_init()
    systems = None
    server = None
    try:
        systems = software_init(hardware)
        if serve:
            server = init_command_server(systems, hardware)
        print(execute_command(command, args))
        while True:
            systems["time_alarm"].update()
            if server is not None:
                server.poll()
            time.sleep_ms(10)
    finally:
        if server is not None:
            server.close()
        if systems is not None:
            systems["time_alarm"].close()
        hardware["buzzer_pwm"].deinit()


if __name__ == "__main__":
    main()
