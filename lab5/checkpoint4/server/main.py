import time

from machine import Pin, PWM, RTC, SoftI2C
import neopixel
import ssd1306

from func_location_weather import LocationWeatherDisplay
from func_time_alarm import TimeAlarmDisplay
from func_text import TextDisplay
from command_protocol import validate_command
from command_server import CommandServer
from device_config import WIFI_SSID, WIFI_PASSWORD, WEATHER_API_KEY, SERVER_PORT

ssid = WIFI_SSID
password = WIFI_PASSWORD
API_KEY = WEATHER_API_KEY





# Optional RTC tuple: (year, month, day, weekday, hour, minute, second, subseconds).
# None preserves the device's existing RTC instead of resetting it at every boot.
RTC_START_TIME = None
COMMAND_LIST = {}


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
        ssid=ssid,
        password=password,
        weather_api_key=API_KEY,
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


def init_command_server(systems):
    ip = systems["weather_location"].connect_wifi()
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
            server = init_command_server(systems)
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
