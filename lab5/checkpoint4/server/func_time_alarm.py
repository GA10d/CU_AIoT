from time import ticks_diff, ticks_ms


class TimeAlarmDisplay:
    """Command-driven clock and one-shot alarm; hardware comes from main.py."""

    def __init__(self, display, rtc, alarm_led, buzzer_pwm, alarm_duration_ms=10000):
        if alarm_duration_ms <= 0:
            raise ValueError("Alarm duration must be positive")
        self.display = display
        self.rtc = rtc
        self.alarm_led = alarm_led
        self.buzzer_pwm = buzzer_pwm
        self.alarm_duration_ms = alarm_duration_ms
        self._view = None
        self._last_frame = None
        self._alarm_time = None
        self._enabled = False
        self._ringing = False
        self._triggered = False
        self._ring_started_ms = None
        self._confirmation_started_ms = None

    @staticmethod
    def _datetime_key(value):
        return (value[0], value[1], value[2], value[4], value[5], value[6])

    @staticmethod
    def _days_in_month(year, month):
        if month == 2:
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            return 29 if leap else 28
        return 30 if month in (4, 6, 9, 11) else 31

    def _next_day(self, value):
        value[2] += 1
        value[3] = (value[3] + 1) % 7
        if value[2] > self._days_in_month(value[0], value[1]):
            value[2] = 1
            value[1] += 1
            if value[1] > 12:
                value[1] = 1
                value[0] += 1

    @staticmethod
    def _date_text(value):
        return "{:04d}-{:02d}-{:02d}".format(*value[:3])

    @staticmethod
    def _time_text(value):
        return "{:02d}:{:02d}:{:02d}".format(*value[4:7])

    def display_time(self):
        """Select the clock view. main.py must keep calling update()."""
        self._view = "time"
        self._confirmation_started_ms = None
        self._last_frame = None
        now = self.rtc.datetime()
        self._service_alarm(now)
        self._render(now)
        return {"date": self._date_text(now), "time": self._time_text(now)}

    def set_alarm(self, hour, minute):
        """Set an HH:MM alarm; show confirmation for 3 seconds, then the clock."""
        for value, limit in ((hour, 24), (minute, 60)):
            if type(value) is not int or not 0 <= value < limit:
                raise ValueError("Invalid alarm time")

        now = self.rtc.datetime()
        alarm = list(now)
        alarm[4], alarm[5], alarm[6], alarm[7] = hour, minute, 0, 0
        if self._datetime_key(alarm) <= self._datetime_key(now):
            self._next_day(alarm)

        self._set_ringing(False)
        self._alarm_time = alarm
        self._enabled = True
        self._triggered = False
        self._ring_started_ms = None
        self._view = "alarm_confirmation"
        self._confirmation_started_ms = ticks_ms()
        self._last_frame = None
        self._render(now)
        return {
            "enabled": self._enabled,
            "ringing": self._ringing,
            "triggered": self._triggered,
            "date": self._date_text(self._alarm_time) if self._alarm_time else None,
            "time": self._time_text(self._alarm_time) if self._alarm_time else None,
        }

    def pause_display(self):
        """Give weather/location control of the OLED while alarm checks continue."""
        self._view = None
        self._confirmation_started_ms = None

    def _set_ringing(self, active):
        if active == self._ringing:
            return
        self._ringing = active
        self.alarm_led[0] = (100, 100, 100) if active else (0, 0, 0)
        self.alarm_led.write()
        self.buzzer_pwm.duty_u16(10768 if active else 0)

    def _service_alarm(self, now):
        # >= catches an alarm even if a synchronous request delayed update().
        if self._enabled and self._datetime_key(now) >= self._datetime_key(self._alarm_time):
            self._enabled = False
            self._triggered = True
            self._ring_started_ms = ticks_ms()
            self._set_ringing(True)
        if (self._ringing and ticks_diff(ticks_ms(), self._ring_started_ms)
                >= self.alarm_duration_ms):
            self._set_ringing(False)

    def _render(self, now):
        if self._view == "time":
            frame = ("time", self._datetime_key(now))
        elif self._view == "alarm_confirmation":
            frame = ("alarm_confirmation", self._date_text(self._alarm_time),
                     self._time_text(self._alarm_time))
        else:
            return
        if frame == self._last_frame:
            return
        self._last_frame = frame

        self.display.fill(0)
        if self._view == "time":
            self.display.text("Time Display", 10, 0, 1)
            self.display.text(self._date_text(now).replace("-", "/"), 24, 11, 1)
            self.display.text(self._time_text(now), 32, 22, 1)
        else:
            self.display.text("Alarm enabled", 0, 0)
            self.display.text(self._date_text(self._alarm_time), 0, 8)
            self.display.text(self._time_text(self._alarm_time), 0, 16)
        self.display.show()

    def update(self):
        """Poll alarm and refresh the selected view; call every ~10 ms."""
        now = self.rtc.datetime()
        self._service_alarm(now)
        if (self._view == "alarm_confirmation"
                and ticks_diff(ticks_ms(), self._confirmation_started_ms) >= 3000):
            self._view = "time"
            self._confirmation_started_ms = None
            self._last_frame = None
        self._render(now)

    def close(self):
        """Silence the buzzer/LED when main exits."""
        self._enabled = False
        self.pause_display()
        self._set_ringing(False)
