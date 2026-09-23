from machine import Pin,PWM
from time import sleep

led=PWM(Pin(13))

led.freq(1000)

while True:
    led.duty(0)
    sleep(1)
    led.duty(256)
    sleep(1)
    led.duty(512)
    sleep(1)
    led.duty(768)
    sleep(1)
    led.duty(1023)
    sleep(1)
