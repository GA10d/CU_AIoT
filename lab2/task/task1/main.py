from machine import Pin,PWM
from time import sleep

led_pwm = PWM(Pin(26), freq=1000, duty_u16=0)
while True:
    led_pwm.duty_u16(32768)  # 大约 50% 亮度
    sleep(1)
    led_pwm.duty_u16(65535)  # 最大
    sleep(1)
    led_pwm.duty_u16(0)      # 关闭
    sleep(1)
