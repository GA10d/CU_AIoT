import network
import time
import urequests


class LocationWeatherDisplay:
    """Look up IP-based location and current weather on a shared OLED."""

    def __init__(self, display, ssid, password="", weather_api_key="", wifi_timeout=30):
        self.display = display
        self.ssid = ssid
        self.password = password
        self.weather_api_key = weather_api_key
        self.wifi_timeout = wifi_timeout
        self._wlan = network.WLAN(network.STA_IF)

    def _show_lines(self, lines):
        self.display.fill(0)
        for row, line in enumerate(lines[:4]):
            self.display.text(str(line)[:16], 0, row * 8)
        self.display.show()

    def _connect_wifi(self):
        if self._wlan.isconnected():
            return

        self._show_lines(["Connecting WiFi"])
        self._wlan.active(True)
        self._wlan.connect(self.ssid, self.password)

        for _ in range(self.wifi_timeout):
            if self._wlan.isconnected():
                break
            time.sleep(1)

        if not self._wlan.isconnected():
            raise OSError("WiFi timeout")

        print("WiFi connected:", self._wlan.ifconfig())

    def connect_wifi(self):
        """Connect once and return the IP for main.py's command server."""
        self._connect_wifi()
        return self._wlan.ifconfig()[0]

    def _get_json(self, url):
        response = None
        try:
            response = urequests.get(url)
            if response.status_code != 200:
                raise OSError("HTTP {}".format(response.status_code))
            return response.json()
        finally:
            if response is not None:
                response.close()

    def _get_location(self):
        self._connect_wifi()
        data = self._get_json("http://ip-api.com/json")
        if data.get("status") != "success":
            raise OSError("Location lookup failed")
        return {
            "latitude": data["lat"],
            "longitude": data["lon"],
            "city": data.get("city", "Unknown"),
        }

    def display_location(self):
        """Show latitude/longitude and return the location dictionary."""
        try:
            location = self._get_location()
            self._show_lines([
                "Location:",
                "Lat: {}".format(location["latitude"]),
                "Lon: {}".format(location["longitude"]),
            ])
            print("Location:", location)
            return location
        except Exception as error:
            self._show_lines(["Location failed", str(error)])
            raise

    def display_weather(self):
        """Show local weather in Celsius and return its dictionary."""
        try:
            if not self.weather_api_key:
                raise ValueError("Missing API key")

            location = self._get_location()
            weather_url = (
                "https://api.openweathermap.org/data/2.5/weather"
                "?lat={}&lon={}&appid={}&units=metric"
            ).format(
                location["latitude"], location["longitude"], self.weather_api_key
            )
            data = self._get_json(weather_url)
            weather = {
                "city": location["city"],
                "temperature": data["main"]["temp"],
                "humidity": data["main"]["humidity"],
                "condition": data["weather"][0]["main"],
            }
            self._show_lines([
                weather["city"],
                "Temp: {:.1f} C".format(weather["temperature"]),
                "Humidity: {}%".format(weather["humidity"]),
                weather["condition"],
            ])
            print("Weather:", weather)
            return weather
        except Exception as error:
            self._show_lines(["Weather failed", str(error)])
            raise
