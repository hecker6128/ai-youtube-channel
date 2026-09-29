import os
import re
import time
import subprocess
from pathlib import Path

from google import genai
import edge_tts


# =========================
# GEMINI
# =========================

API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.5-flash-lite"

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

        wait_time = attempt * 15

        print(
            f"Waiting {wait_time} seconds before retry..."
        )

        time.sleep(wait_time)


if not response or not response.text:
    raise RuntimeError("Gemini returned an empty response.")


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
# EXTRACT TITLE
# =========================

title_match = re.search(
    r"(?im)^TITLE:\s*(.+)$",
    text
)

if title_match:
    title = title_match.group(1).strip()
else:
    title = "History Fact"


# Remove characters that can cause problems in FFmpeg text
title = re.sub(r"[\r\n]+", " ", title)
title = title.replace(":", " - ")


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

print("Voice generated successfully.")


# =========================
# CHECK FFMPEG
# =========================

print("Checking FFmpeg...")

try:
    subprocess.run(
        ["ffmpeg", "-version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )
except Exception:
    raise RuntimeError(
        "FFmpeg is not installed or could not be executed."
    )


# =========================
# GET AUDIO DURATION
# =========================

print("Reading audio duration...")

probe = subprocess.run(
    [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ],
    capture_output=True,
    text=True,
    check=True
)

duration = float(probe.stdout.strip())

print(f"Audio duration: {duration:.2f} seconds")


# =========================
# LIMIT / VALIDATE DURATION
# =========================

if duration < 5:
    raise RuntimeError(
        "Generated narration is too short."
    )

if duration > 90:
    print(
        "Warning: narration is longer than 90 seconds."
    )


# =========================
# CREATE VIDEO
# =========================

video_file = output_dir / "video.mp4"

print("Creating vertical YouTube Short...")


# FFmpeg filter:
#
# - 1080x1920 vertical video
# - dark animated background
# - subtle moving gradient
# - title at top
# - audio from Edge TTS
#
# The background is generated entirely by FFmpeg,
# so no external images are required.


filter_complex = (
    "color=c=0x080808:s=1080x1920:r=30,"
    "format=yuv420p,"
    "drawbox="
    "x=0:"
    "y=0:"
    "w=1080:"
    "h=1920:"
    "color=black@0.15:"
    "t=fill,"
    "drawtext="
    "fontcolor=white:"
    "fontsize=64:"
    "font='DejaVu Sans':"
    "x=(w-text_w)/2:"
    "y=500:"
    "text='"
    + title.replace("'", r"'\''")
    + "'"
    ":enable='between(t,0,8)':"
    "box=1:"
    "boxcolor=black@0.55:"
    "boxborderw=25"
)


command = [
    "ffmpeg",
    "-y",

    # Generate background
    "-f",
    "lavfi",
    "-i",
    f"{filter_complex}:d={duration}",

    # Audio
    "-i",
    str(audio_file),

    # Video settings
    "-map",
    "0:v:0",
    "-map",
    "1:a:0",

    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "23",

    "-c:a",
    "aac",
    "-b:a",
    "192k",

    "-pix_fmt",
    "yuv420p",

    "-r",
    "30",

    "-shortest",

    str(video_file)
]


print("Running FFmpeg...")

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)

if result.returncode != 0:

    print("FFmpeg stdout:")
    print(result.stdout)

    print("FFmpeg stderr:")
    print(result.stderr)

    raise RuntimeError(
        "FFmpeg failed to create the video."
    )


# =========================
# VERIFY VIDEO
# =========================

if not video_file.exists():
    raise RuntimeError(
        "FFmpeg finished but video.mp4 was not created."
    )

video_size = video_file.stat().st_size

if video_size < 10000:
    raise RuntimeError(
        "Generated video appears to be invalid or empty."
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
print(f"Video:       {video_file}")

print()
print("================================")
print("VIDEO INFORMATION")
print("================================")

print("Resolution: 1080x1920")
print("Format:     MP4")
print("Audio:      AAC")
print("Video:      H.264")
print(f"Duration:   {duration:.2f} seconds")

print()
print("================================")
print("NARRATION")
print("================================")

print(script)

print()
print("================================")
print("DONE")
print("================================")