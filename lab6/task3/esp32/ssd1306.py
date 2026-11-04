"""Minimal SSD1306 I2C framebuffer driver for the lab's 128x32 OLED.

Supports the fill/text/show/poweron/poweroff API used by the Lab 5 program.
"""
import framebuf


class SSD1306_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        if width != 128 or height not in (32, 64):
            raise ValueError("Supported OLED sizes: 128x32 and 128x64")
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.buffer = bytearray(width * height // 8)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        commands = (
            0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, height - 1, 0xC8,
            0xD3, 0x00, 0xDA, 0x02 if height == 32 else 0x12,
            0xD5, 0x80, 0xD9, 0xF1, 0xDB, 0x30,
            0x81, 0xFF, 0xA4, 0xA6, 0x8D, 0x14, 0xAF,
        )
        for command in commands:
            self.write_cmd(command)
        self.fill(0)
        self.show()

    def write_cmd(self, command):
        self.i2c.writeto(self.addr, bytes([0x80, command]))

    def show(self):
        for command in (0x21, 0, self.width - 1, 0x22, 0, self.height // 8 - 1):
            self.write_cmd(command)
        self.i2c.writeto(self.addr, b"\x40" + self.buffer)

    def poweron(self):
        self.write_cmd(0xAF)

    def poweroff(self):
        self.write_cmd(0xAE)
