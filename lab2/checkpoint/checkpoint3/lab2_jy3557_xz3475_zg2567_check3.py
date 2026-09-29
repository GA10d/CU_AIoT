from time import ticks_ms, ticks_diff, sleep
from machine import ADC, Pin, PWM

button = Pin(39, Pin.IN)

last_time = 0
DEBOUNCE_MS = 50
SYSTEM_ON = False
COUNT = 0

def button_handler(pin):
    global last_time, SYSTEM_ON, COUNT
    now = ticks_ms()
    if ticks_diff(now, last_time) < DEBOUNCE_MS:
        return
    last_time = now
    SYSTEM_ON = not SYSTEM_ON
    COUNT += 1
    if SYSTEM_ON:
        print("System turned ON")
    else:
        print("System turned OFF")
    print("Button pressed:", COUNT)

button.irq(
    trigger=Pin.IRQ_FALLING,
    handler=button_handler
)

light = ADC(Pin(34))
raw = light.read_u16()

led_pwm = PWM(Pin(26), freq=1000, duty_u16=0)
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=0)

while True:
    if not SYSTEM_ON:
        buzzer_pwm.duty_u16(0)
        led_pwm.duty_u16(0)
        continue
    buzzer_pwm.duty_u16(32768)
    raw = light.read_u16()
    # 更新 LED 和 piezo
    led_pwm.duty_u16(raw)
    frequency = int(raw / 65535 * 2000 + 100)
    buzzer_pwm.freq(frequency)  # 将频率映射到 100-2100 Hz 范围
    sleep(0.001)  # 1 kHz