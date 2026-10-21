"""Set the ESP32 RTC to real local time from NTP once Wi-Fi is up.

ntptime gives UTC. This module adds a fixed UTC offset plus, optionally,
US daylight saving time (second Sunday of March to first Sunday of November,
switching at 02:00 local), so the clock shows e.g. New York time.
"""
import time

try:
    import ntptime
except ImportError:  # CPython, for testing the DST maths on a computer
    ntptime = None


def _weekday(year, month, day):
    """0 = Monday ... 6 = Sunday (same convention as time.gmtime)."""
    offsets = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if month < 3:
        year -= 1
    sunday_based = (year + year // 4 - year // 100 + year // 400
                    + offsets[month - 1] + day) % 7
    return (sunday_based + 6) % 7


def _nth_sunday(year, month, n):
    first = _weekday(year, month, 1)
    first_sunday = 1 + (6 - first) % 7
    return first_sunday + 7 * (n - 1)


def us_dst_active(utc, std_offset_hours):
    """True if US DST is in effect at the given UTC time tuple (Y, M, D, h, ...)."""
    year, month, day, hour = utc[0], utc[1], utc[2], utc[3]
    if month < 3 or month > 11:
        return False
    if 3 < month < 11:
        return True
    if month == 3:
        # 02:00 standard time -> UTC
        start_day, start_hour = _nth_sunday(year, 3, 2), 2 - std_offset_hours
        return (day, hour) >= (start_day, start_hour)
    # November: 02:00 daylight time -> UTC
    end_day, end_hour = _nth_sunday(year, 11, 1), 2 - (std_offset_hours + 1)
    return (day, hour) < (end_day, end_hour)


def local_offset_seconds(utc, std_offset_hours, use_us_dst):
    hours = std_offset_hours
    if use_us_dst and us_dst_active(utc, std_offset_hours):
        hours += 1
    return int(hours * 3600)


def sync_rtc(rtc, std_offset_hours=-5, use_us_dst=True, host="pool.ntp.org", attempts=3):
    """Set rtc to local time. Returns the local time tuple, or None if NTP failed.

    Never raises on network errors, so a missing NTP reply does not stop the
    command server from starting; the RTC just keeps its previous value.
    """
    if ntptime is None:
        raise RuntimeError("ntptime is only available on MicroPython")
    ntptime.host = host
    for attempt in range(attempts):
        try:
            utc_seconds = ntptime.time()
            break
        except Exception as error:
            print("NTP attempt {} failed: {}".format(attempt + 1, error))
            time.sleep(1)
    else:
        print("NTP sync failed; keeping the current RTC time")
        return None

    utc = time.gmtime(utc_seconds)
    local = time.gmtime(utc_seconds + local_offset_seconds(utc, std_offset_hours, use_us_dst))
    # gmtime: (Y, M, D, h, m, s, weekday, yearday); RTC: (Y, M, D, weekday, h, m, s, subsec)
    rtc.datetime((local[0], local[1], local[2], local[6], local[3], local[4], local[5], 0))
    print("RTC synced from NTP: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*local[:6]))
    return local
