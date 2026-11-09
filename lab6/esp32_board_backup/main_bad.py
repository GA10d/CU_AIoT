from machine import Pin, I2C
import ssd1306

pwr = Pin(2, Pin.OUT)
pwr.value(1)

i2c = I2C(0, scl=Pin(22), sda=Pin(23))
display = ssd1306.SSD1306_I2C(128, 32, i2c)

display.text("Hello, World!", 0, 0, 1)
display.show()
