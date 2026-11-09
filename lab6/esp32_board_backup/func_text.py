class TextDisplay:
    """Display ASCII text using the OLED's built-in 8x8 font."""

    def __init__(self, display):
        self.display = display
        self.columns = display.width // 8
        self.rows = display.height // 8
        if self.columns < 3 or self.rows < 1:
            raise ValueError("Display is too small for text")

    def display_text(self, text):
        """Replace the OLED contents, wrapping text and clipping excess lines."""
        if not isinstance(text, str):
            raise ValueError("Text must be a string")
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        if any(char != "\n" and not 32 <= ord(char) <= 126 for char in text):
            raise ValueError("OLED font supports ASCII text only")

        lines = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
            else:
                for start in range(0, len(paragraph), self.columns):
                    lines.append(paragraph[start:start + self.columns])

        truncated = len(lines) > self.rows
        visible = lines[:self.rows]
        if truncated:
            visible[-1] = visible[-1][:self.columns - 3] + "..."

        self.display.fill(0)
        for row, line in enumerate(visible):
            self.display.text(line, 0, row * 8, 1)
        self.display.show()
        return {"text": "\n".join(visible), "truncated": truncated}
