import os
import re
import time
from pathlib import Path

from google import genai
import edge_tts


# =========================
# GEMINI
# =========================

API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.8-flash"

prompt = """
You are a scriptwriter for a YouTube Shorts channel.

Theme of the channel:
history facts and interesting events from the past.

Create one original YouTube Short.

The video should be 45-60 seconds long.
The spoken script should contain approximately 125-140 words.

Write exactly this format:

TITLE:
[short interesting title]

HOOK:
[first words that grab attention]

SCRIPT:
[complete speech for the video]

DESCRIPTION:
[short description of the video]

TAGS:
[tag1, tag2, tag3, tag4, tag5]

Rules:
- use simple and natural English
- use factual historical information
- do not invent facts
- do not make up dates, numbers, quotes or events
- avoid well-known clichés when possible
- do not use unrelated clickbait
- make the story interesting from the first sentence
- the SCRIPT must sound natural when spoken aloud
- the SCRIPT must not contain headings or bullet points
- write the SCRIPT as one continuous narration
"""


# =========================
# GENERATE WITH RETRIES
# =========================

MAX_ATTEMPTS = 5

response = None

for attempt in range(1, MAX_ATTEMPTS + 1):

    print(f"Gemini attempt {attempt}/{MAX_ATTEMPTS}...")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        if response and response.text:
            print("Gemini response received.")
            break

    except Exception as error:

        print(f"Gemini request failed: {error}")

        if attempt == MAX_ATTEMPTS:
            raise RuntimeError(
                "Gemini could not generate the script after "
                f"{MAX_ATTEMPTS} attempts."
            )

        # Increasing delay:
        # 15s, 30s, 45s, 60s
        wait_time = attempt * 15

        print(
            f"Waiting {wait_time} seconds before retry..."
        )

        time.sleep(wait_time)


text = response.text.strip()


# =========================
# OUTPUT FOLDER
# =========================

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)


# =========================
# SAVE COMPLETE RESPONSE
# =========================

script_file = output_dir / "script.txt"

script_file.write_text(
    text,
    encoding="utf-8"
)


# =========================
# EXTRACT SCRIPT
# =========================

match = re.search(
    r"(?is)SCRIPT:\s*(.*?)(?=\n\s*DESCRIPTION:|\Z)",
    text
)

if not match:
    raise RuntimeError(
        "Could not find SCRIPT section in Gemini response."
    )

script = match.group(1).strip()

script = script.replace("```", "").strip()


# =========================
# SAVE NARRATION
# =========================

narration_file = output_dir / "narration.txt"

narration_file.write_text(
    script,
    encoding="utf-8"
)


# =========================
# TEXT TO SPEECH
# =========================

VOICE = "en-US-GuyNeural"

audio_file = output_dir / "voice.mp3"

print("Generating voice...")

communicate = edge_tts.Communicate(
    script,
    VOICE
)

communicate.save_sync(
    str(audio_file)
)


# =========================
# FINISHED
# =========================

print()
print("================================")
print("VIDEO CONTENT GENERATED")
print("================================")

print(f"Full script: {script_file}")
print(f"Narration:   {narration_file}")
print(f"Voice:       {audio_file}")

print()
print("================================")
print("NARRATION")
print("================================")
print(script)

print()
print("================================")
print("DONE")
print("================================")