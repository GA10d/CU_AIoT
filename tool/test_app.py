import unittest

import app


class FakeSerial:
    def __init__(self, banner=b"raw REPL; CTRL-B to exit\r\n>"):
        self.buffer = bytearray()
        self.commands = []
        self.banner = banner

    @property
    def in_waiting(self):
        return len(self.buffer)

    def write(self, data):
        if b"\x01" in data:
            self.buffer.extend(self.banner)
        elif data.endswith(b"\x04") and data != b"\x02\x04":
            self.commands.append(data[:-1].decode("utf-8"))
            self.buffer.extend(b"OK\x04\x04>")
        return len(data)

    def read(self, size=1):
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.buffer.clear()


class RawReplUploaderTests(unittest.TestCase):
    def test_uploads_and_renames_main(self):
        fake = FakeSerial()
        app.upload_bytes_with_raw_repl(fake, b"print('hello')\n")
        joined = "\n".join(fake.commands)
        self.assertIn("a2b_base64", joined)
        self.assertIn("f.close()", joined)
        self.assertIn("uos.rename('.main.py.upload','main.py')", joined)

    def test_accepts_silent_raw_repl_prompt(self):
        fake = FakeSerial(b"\r\n>")
        app.upload_bytes_with_raw_repl(fake, b"print('silent banner')\n")
        self.assertTrue(any("a2b_base64" in command for command in fake.commands))

    def test_rejects_friendly_repl_prompt(self):
        fake = FakeSerial(b"\r\n>>> ")
        with self.assertRaisesRegex(RuntimeError, "没有进入"):
            app.upload_bytes_with_raw_repl(fake, b"print('wrong prompt')\n")


if __name__ == "__main__":
    unittest.main()
