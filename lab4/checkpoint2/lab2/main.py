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

ssid = "Columbia University"
password = ""

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

show_lines(["Connecting WiFi"])
while not wlan.isconnected():
    print("Connecting...")
    time.sleep(1)

show_lines(["WiFi connected", "Getting location"])
print("Connected:", wlan.ifconfig())

url = "http://ip-api.com/json"
response = None

try:
    response = urequests.get(url)
    response_text = response.text
    data = response.json()

    lat = data["lat"]
    lon = data["lon"]

    print("URL:", url)
    print("Response:", response_text)
    print("Latitude:", lat)
    print("Longitude:", lon)

    show_lines([
        "Location:",
        "Lat: {}".format(lat),
        "Lon: {}".format(lon),
    ])
except Exception as error:
    print("Request failed:", error)
    show_lines(["Request failed"])
finally:
    if response is not None:
        response.close()