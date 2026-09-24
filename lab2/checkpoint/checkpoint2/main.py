from time import ticks_ms, ticks_diff
from machine import Pin

button = Pin(39, Pin.IN)

last_time = 0
DEBOUNCE_MS = 50
PRESS_COUNT = 0

def button_handler(pin):
    global last_time, PRESS_COUNT
    now = ticks_ms()
    if ticks_diff(now, last_time) < DEBOUNCE_MS:
        return
    last_time = now
    PRESS_COUNT += 1
    # print(button.value())
    print("Button pressed:", PRESS_COUNT)


button.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_handler
)