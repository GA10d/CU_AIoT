from machine import Pin, I2C
import ssd1306

pwr = Pin(13, Pin.OUT)
pwr.value(1)

i2c = I2C(0, scl=Pin(20), sda=Pin(22))
display = ssd1306.SSD1306_I2C(128, 32, i2c)

display.text("Hello, World!", 0, 0, 1)
display.show()
