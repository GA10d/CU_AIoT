import network
import time
import urequests
from machine import Pin, SoftI2C
import ssd1306

i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

def show_lines(lines):
    display.fill(0)
    for row, line in enumerate(lines):
        display.text(str(line)[:16], 0, row * 8)
    display.show()

def get_json(url):
    response = None
    try:
        response = urequests.get(url)
        if response.status_code != 200:
            raise OSError("HTTP {}".format(response.status_code))
        return response.json()
    finally:
        if response is not None:
            response.close()

ssid = "Columbia University"
password = ""
API_KEY = "替换成新的OpenWeatherMap_API_Key"

stage = "WiFi"

try:
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    for _ in range(30):
        if wlan.isconnected():
            break
        time.sleep(1)

    if not wlan.isconnected():
        raise OSError("WiFi connection timeout")

    print("WiFi connected:", wlan.ifconfig())

    stage = "Location API"
    location = get_json("http://ip-api.com/json")

    if location.get("status") != "success":
        raise OSError("Location lookup failed")

    lat = location["lat"]
    lon = location["lon"]
    city = location.get("city", "Unknown")

    stage = "Weather API"
    weather_url = (
        "https://api.openweathermap.org/data/2.5/weather"
        "?lat={}&lon={}&appid={}&units=metric"
    ).format(lat, lon, API_KEY)

    weather = get_json(weather_url)

    temperature = weather["main"]["temp"]
    humidity = weather["main"]["humidity"]
    description = weather["weather"][0]["main"]

    print("Weather URL: OpenWeatherMap current weather")
    print("Weather response:", weather)
    print("City:", city)
    print("Temperature:", temperature, "C")
    print("Humidity:", humidity, "%")
    print("Condition:", description)

    show_lines([
        city,
        "Temp: {:.1f} C".format(temperature),
        "Humidity: {}%".format(humidity),
        description,
    ])

except Exception as error:
    print(stage + " failed:", error)
    city = "Unknown"
    temperature = "N/A"
    humidity = "N/A"
    description = "N/A"

    print("City:", city)
    print("Temperature:", temperature)
    print("Humidity:", humidity)
    print("Condition:", description)

    show_lines([
        city,
        "Temp: " + temperature,
        "Humidity: " + humidity,
        description,
    ])