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


def dot():
    np_led[0] = (10, 10, 10)
    np_led.write()
    utime.sleep(0.1)
    np_led[0] = (0, 0, 0)
    np_led.write()
    utime.sleep(0.1)

def string():
    np_led[0] = (10, 10, 10)
    np_led.write()
    utime.sleep(0.5)
    np_led[0] = (0, 0, 0)
    np_led.write()
    utime.sleep(0.1)

while True:
    builtin_led.value(not builtin_led.value())

    dot()
    dot()
    dot()
    string()
    string()
    string()
    dot()
    dot()
    dot()
    utime.sleep(1)