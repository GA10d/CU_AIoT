"""JSON command contract shared by ESP32, the test client and Gradio."""

COMMAND_ARG_COUNTS = {
    "screen_on": 0,
    "screen_off": 0,
    "display_time": 0,
    "set_alarm": 2,
    "display_text": 1,
    "display_location": 0,
    "display_weather": 0,
}


class CommandError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def validate_command(command):
    if not isinstance(command, dict) or set(command) != {"name", "args"}:
        raise CommandError("invalid_command", "Expected a JSON object with name and args")
    name, args = command["name"], command["args"]
    if not isinstance(name, str) or name not in COMMAND_ARG_COUNTS:
        raise CommandError("unknown_command", "Unknown command: {}".format(name))
    if not isinstance(args, list) or len(args) != COMMAND_ARG_COUNTS[name]:
        raise CommandError("invalid_arguments", "{} requires {} arguments".format(
            name, COMMAND_ARG_COUNTS[name]))
    if name == "set_alarm":
        hour, minute = args
        if (type(hour) is not int or type(minute) is not int
                or not 0 <= hour < 24 or not 0 <= minute < 60):
            raise CommandError("invalid_arguments", "Alarm needs hour 0-23 and minute 0-59")
    elif name == "display_text":
        text = args[0]
        if not isinstance(text, str):
            raise CommandError("invalid_arguments", "Text must be a string")
        if any(c not in "\r\n\t" and not 32 <= ord(c) <= 126 for c in text):
            raise CommandError("invalid_arguments", "OLED font supports ASCII text only")
    return command
