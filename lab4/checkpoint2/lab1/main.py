import network
import time

ssid = "Columbia University"
password = ""

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

while not wlan.isconnected():
    print("Connecting...")
    time.sleep(1)

print("Connected!")
print(wlan.ifconfig())