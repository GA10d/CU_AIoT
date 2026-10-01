from time import sleep
from machine import ADC, Pin, PWM
from machine import SoftI2C
import ssd1306

i2c = SoftI2C(sda=Pin(22), scl=Pin(20), freq=100000)
display = ssd1306.SSD1306_I2C(128, 32, i2c)

light = ADC(Pin(34))
raw = light.read_u16()

led_pwm = PWM(Pin(26), freq=1000, duty_u16=0)
buzzer_pwm = PWM(Pin(25), freq=1000, duty_u16=10768)

display.text("Light test", 0, 0)
display.show()
while True:
    raw = light.read_u16()
    contrast = max(15, raw * 255 // 65535)
    display.contrast(contrast)
    display.show()
    led_pwm.duty_u16(raw)
    frequency = int(raw / 65535 * 2000 + 100)
    buzzer_pwm.freq(frequency)
    sleep(0.1)  # 10 Hz
    raw = raw % 65536