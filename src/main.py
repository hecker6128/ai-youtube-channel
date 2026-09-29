import os
import re
from pathlib import Path

from google import genai
import edge_tts


# =========================
# GEMINI
# =========================

API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

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

response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt
)

text = (response.text or "").strip()

if not text:
    raise RuntimeError("Gemini returned an empty response.")


# =========================
# OUTPUT FOLDER
# =========================

output_dir = Path("output")
output_dir.mkdir(exist_ok=True)


# =========================
# SAVE COMPLETE GEMINI RESULT
# =========================

script_file = output_dir / "script.txt"

script_file.write_text(
    text,
    encoding="utf-8"
)


# =========================
# EXTRACT SCRIPT
# =========================

def extract_script(text):
    match = re.search(
        r"(?is)SCRIPT:\s*(.*?)(?=\n\s*DESCRIPTION:|\Z)",
        text
    )

    if not match:
        raise RuntimeError(
            "Could not find SCRIPT section in Gemini response."
        )

    return match.group(1).strip()


script = extract_script(text)


# Remove accidental markdown characters
script = script.replace("```", "")
script = script.strip()


# =========================
# SAVE NARRATION TEXT
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

communicate = edge_tts.Communicate(
    script,
    VOICE
)

communicate.save_sync(
    str(audio_file)
)


# =========================
# LOG
# =========================

print()
print("================================")
print("VIDEO CONTENT GENERATED")
print("================================")
print()

print(f"Full Gemini response:")
print(script_file)

print()

print(f"Narration:")
print(narration_file)

print()

print(f"Voice:")
print(audio_file)

print()
print("================================")
print("NARRATION")
print("================================")
print(script)
print()
print("================================")
print("DONE")
print("================================")