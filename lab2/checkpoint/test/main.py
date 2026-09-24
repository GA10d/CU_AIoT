from time import ticks_ms, ticks_diff, sleep_ms
from machine import ADC, Pin, PWM

DEBOUNCE_MS = 30

# GPIO39 必须使用外部下拉电阻
button = Pin(39, Pin.IN)

light = ADC(Pin(34))

led_pwm = PWM(Pin(26), freq=1000, duty_u16=0)
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=0)

SYSTEM_ON = False
last_time = 0


def button_handler(pin):
    global last_time, SYSTEM_ON

    now = ticks_ms()

    if ticks_diff(now, last_time) < DEBOUNCE_MS:
        return

    last_time = now

    # 外部下拉接法：按下为 1，松开为 0
    SYSTEM_ON = bool(pin.value())

    if SYSTEM_ON:
        print("Button pressed: system ON")
    else:
        print("Button released: system OFF")


button.irq(
    trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
    handler=button_handler
)

while True:
    if not SYSTEM_ON:
        led_pwm.duty_u16(0)
        buzzer_pwm.duty_u16(0)
        sleep_ms(10)
        continue

    raw = light.read_u16()

    led_pwm.duty_u16(raw)

    frequency = 100 + raw * 2000 // 65535
    buzzer_pwm.freq(frequency)
    buzzer_pwm.duty_u16(32768)

    sleep_ms(50)