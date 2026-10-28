# Copy to board_config.py on the ESP32 and fill in your Wi-Fi credentials.
SSID = "Columbia University"
PASSWORD = ""  # Leave empty for open Wi-Fi; fill in for a secured network
PORT = 8080

# From Lab5/checkpoints/checkpoint2/server.py. Verify against your wiring.
OLED_SDA = 22
OLED_SCL = 20

# From Lab4/checkpoint1/Checkpoint1.py. GPIO numbers, not board silk labels.
SPI_ID = 2
ADXL_SCK = 5
ADXL_MOSI = 19
ADXL_MISO = 21
ADXL_CS = 4

# Optional: only needed for the existing Lab 5 weather command.
WEATHER_API = ""
