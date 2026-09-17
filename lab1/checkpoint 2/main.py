from machine import Pin
import utime
import neopixel

# Enable power for the NeoPixel
pwr = Pin(2, Pin.OUT)
pwr.value(1)

# Configure the two built-in LEDs
builtin_led = Pin(13, Pin.OUT)
np_led = neopixel.NeoPixel(Pin(0, Pin.OUT), 1)

builtin_led.value(1)
np_led[0] = (0, 0, 0)
np_led.write()

x = 0

def reverse_13():
    if np_led[0] == (0, 0, 0):
        np_led[0] = (255, 255, 255)
    else:
        np_led[0] = (0, 0, 0)
    np_led.write()

while True:
    utime.sleep_ms(100)
    x+=1
    builtin_led.value(not builtin_led.value())
    if(x % 5 == 0):
        reverse_13()
        x = 0