import os

from machine import Pin, SoftI2C
import ssd1306

from func_location_weather import LocationWeatherDisplay


ssid = os.getenv("WIFI_SSID", "Columbia University")
password = os.getenv("WIFI_PASSWORD", "")
API_KEY = os.getenv("WEATHER_API_KEY", "640bdd03fa4bc5eeff41cfdbe18e9d4c")


def main(command="display_weather"):
    i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
    display = ssd1306.SSD1306_I2C(128, 32, i2c)
    info = LocationWeatherDisplay(
        display=display,
        ssid=ssid,
        password=password,
        weather_api_key=API_KEY,
    )
    handlers = {
        "display_weather": info.display_weather,
        "display_location": info.display_location,
    }
    if command not in handlers:
        raise ValueError("Unknown command: {}".format(command))

    try:
        return handlers[command]()
    except Exception as error:
        print(command + " failed:", error)
        return None


if __name__ == "__main__":
    main()
