import os

from google import genai

API_KEY = ""
MODEL = "gemini-3.5-flash-lite"  

client = genai.Client(api_key=API_KEY)

try:
    response = client.models.generate_content(
        model=MODEL,
        contents="Reply with exactly: API connection successful",
    )
    print("API return：")
    print(response.text)

except Exception as error:
    print("API call failed:")
    print(error)