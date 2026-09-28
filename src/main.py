import os
from pathlib import Path
from google import genai

API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

prompt = """
You are a scriptwriter for YouTube Shorts channel.

Themu of the channel:
history facts and interesting events from the past.

Create new YouTube short.

Video should be 45-60s long.

Write me this exact format:

TITLE:
[short interesting title]

HOOK:
[first words that grab attention]

SCRIPT:
[complete speech for video]

DESCRIPTION:
[short description of the video]

TAGS:
[tag1, tag2, tag3, tag4, tag5]

Rules:
- use simple and natural English language
- don't make up facts
- don't repeat well-known clichés
- don't use clickbait that is not related to the content
"""

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt
)

text = response.text

# Kreiraj folder za generisani sadržaj
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

# Sačuvaj Gemini rezultat
output_file = output_dir / "script.txt"
output_file.write_text(text, encoding="utf-8")

print("Gemini rezultat je uspješno sačuvan.")
print(f"Fajl: {output_file}")

# Ispiši ga i u log radi lakšeg testiranja
print("\n--- GENERATED SCRIPT ---")
print(text)
print("--- END ---")