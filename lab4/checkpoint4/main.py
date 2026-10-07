import network
import time
import urequests
from machine import Pin, SoftI2C
import ssd1306

SSID = "Columbia University"
PASSWORD = ""
TOPIC = "zg2567" 
WEATHER_API = "640bdd03fa4bc5eeff41cfdbe18e9d4c"

def wifi_connect(ssid = SSID, password = PASSWORD):
    # 连接 Wi-Fi
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    if not wifi.isconnected():
        wifi.connect(ssid, password)
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

def push2ntfy(topic = TOPIC, message = "Hello from ESP32! Lab4 Checkpoint 4", title = "Lab4 Checkpoint 4"):
    url = "https://ntfy.sh/" + topic
    response = None

    try:
        response = urequests.post(
            url,
            data=message,
            headers={
                "Title": title,
            }
        )

        print("HTTP status:", response.status_code)
        print("Response:", response.text)

    finally:
        if response is not None:
            response.close()

def get_json(url):
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

# main
wifi_connect()
lat, lon, city = get_location()
location_message = "you are at Lat {}, Lon {}, City {}".format(lat, lon, city)
push2ntfy(message=location_message, title="Location Update")
temperature, humidity, description = get_weather(lat=lat, lon=lon)
push2ntfy(message="Temperature: {} C, Humidity: {} %, Condition: {}".format(temperature, humidity, description), title="Weather Update")