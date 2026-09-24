from time import sleep
from machine import ADC, Pin, PWM

light = ADC(Pin(34))
raw = light.read_u16()

led_pwm = PWM(Pin(26), freq=1000, duty_u16=0)
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=10768)

while True:
    raw = light.read_u16()
    # 更新 LED 和 piezo
    led_pwm.duty_u16(raw)
    frequency = int(raw / 65535 * 2000 + 100)
    buzzer_pwm.freq(frequency)  # 将频率映射到 100-2100 Hz 范围
    sleep(0.1)  # 10 Hz
    raw = raw % 65536  # 保持在 0-65535 范围内