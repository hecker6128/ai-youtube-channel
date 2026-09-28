import os
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

max_attempts = 5

for attempt in range(1, max_attempts + 1):
    try:
        print(f"Try {attempt}/{max_attempts}...")

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        print("\n===== GENERISANI VIDEO =====\n")
        print(response.text)
        print("\n===== KRAJ =====")

        break

    except Exception as e:
        error = str(e)

        print(f"Greška: {error}")

        if "503" in error or "UNAVAILABLE" in error:
            if attempt < max_attempts:
                wait_time = attempt * 15
                print(
                    f"Gemini je trenutno zauzet. "
                    f"Čekam {wait_time} sekundi prije novog pokušaja..."
                )
                time.sleep(wait_time)
            else:
                print("Gemini nije bio dostupan nakon svih pokušaja.")
                raise
        else:
            raise