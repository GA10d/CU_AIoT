import network
import time
import urequests

SSID = "Columbia University"
PASSWORD = ""
TOPIC = "zg2567"  # 改成浏览器订阅的 topic

# 连接 Wi-Fi
wifi = network.WLAN(network.STA_IF)
wifi.active(True)

if not wifi.isconnected():
    wifi.connect(SSID, PASSWORD)

    start = time.ticks_ms()
    while not wifi.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > 20000:
            raise RuntimeError("WiFi connection timed out")
        time.sleep(0.5)

print("WiFi connected:", wifi.ifconfig())

# 向 ntfy 发布一条消息
url = "https://ntfy.sh/" + TOPIC
response = None

try:
    response = urequests.post(
        url,
        data="Hello from ESP32! Lab4 Checkpoint 4",
        headers={
            "Title": "Lab4 Checkpoint 4",
            "Content-Type": "text/plain"
        }
    )

    print("HTTP status:", response.status_code)
    print("Response:", response.text)

finally:
    if response is not None:
        response.close()