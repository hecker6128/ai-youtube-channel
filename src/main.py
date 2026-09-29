import os
import re
import time
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

from google import genai
import edge_tts


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]

MODEL = "gemini-3.5-flash-lite"
VOICE = "en-US-GuyNeural"

OUTPUT_DIR = Path("output")
SCENES_DIR = OUTPUT_DIR / "scenes"

OUTPUT_DIR.mkdir(exist_ok=True)
SCENES_DIR.mkdir(exist_ok=True)

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# GEMINI PROMPT
# ============================================================

prompt = """
You are a professional writer for an automated YouTube Shorts
history channel.

Create ONE original historical YouTube Short.

The video must be:
- 45-60 seconds
- approximately 125-140 spoken words
- factual
- interesting from the first sentence
- written in simple natural English

IMPORTANT:
The visual scenes must be suitable for stock video searches.
Do NOT ask for historical footage that is extremely specific
or impossible to find.

Create exactly this format:

TITLE:
[short title]

HOOK:
[short hook]

SCRIPT:
[complete narration]

DESCRIPTION:
[short YouTube description]

TAGS:
[tag1, tag2, tag3, tag4, tag5]

SCENE1:
[5-8 word Pexels video search query]

SCENE2:
[5-8 word Pexels video search query]

SCENE3:
[5-8 word Pexels video search query]

SCENE4:
[5-8 word Pexels video search query]

SCENE5:
[5-8 word Pexels video search query]

SCENE6:
[5-8 word Pexels video search query]

Rules:
- use real historical facts
- do not invent dates, people, events or quotes
- do not use unsupported claims
- avoid unrelated clickbait
- the narration must sound natural when spoken
- SCRIPT must be one continuous narration
- do not put headings inside SCRIPT
- do not use bullet points inside SCRIPT
- scene searches should describe visually interesting footage
- prefer things like old buildings, cities, maps, crowds,
  soldiers, ships, trains, documents, landscapes, fire,
  factories, streets, monuments and similar subjects
- scene queries must be in English
- each scene query should be different
"""


# ============================================================
# GEMINI GENERATION
# ============================================================

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

    raise RuntimeError(
        "Gemini returned an empty response."
    )


text = response.text.strip()


# ============================================================
# SAVE GEMINI RESPONSE
# ============================================================

script_file = OUTPUT_DIR / "script.txt"

script_file.write_text(
    text,
    encoding="utf-8"
)


# ============================================================
# EXTRACT TITLE
# ============================================================

title_match = re.search(
    r"(?im)^TITLE:\s*(.+)$",
    text
)

if title_match:

    title = title_match.group(1).strip()

else:

    title = "History Fact"


title = re.sub(
    r"[\r\n]+",
    " ",
    title
)


# ============================================================
# EXTRACT SCRIPT
# ============================================================

script_match = re.search(
    r"(?is)SCRIPT:\s*(.*?)(?=\n\s*DESCRIPTION:|\Z)",
    text
)

if not script_match:

    raise RuntimeError(
        "Could not find SCRIPT section."
    )


script = script_match.group(1).strip()

script = script.replace("```", "").strip()


narration_file = OUTPUT_DIR / "narration.txt"

narration_file.write_text(
    script,
    encoding="utf-8"
)


# ============================================================
# EXTRACT SCENE SEARCH QUERIES
# ============================================================

scene_queries = []

for i in range(1, 7):

    match = re.search(
        rf"(?im)^SCENE{i}:\s*(.+)$",
        text
    )

    if match:

        query = match.group(1).strip()

        query = re.sub(
            r"[\r\n]+",
            " ",
            query
        )

        scene_queries.append(query)

    else:

        scene_queries.append(
            "historical city old buildings"
        )


print()
print("Scene queries:")

for i, query in enumerate(scene_queries, 1):

    print(
        f"Scene {i}: {query}"
    )


# ============================================================
# TEXT TO SPEECH
# ============================================================

audio_file = OUTPUT_DIR / "voice.mp3"

print()
print("Generating voice...")

communicate = edge_tts.Communicate(
    script,
    VOICE
)

communicate.save_sync(
    str(audio_file)
)

print(
    "Voice generated successfully."
)


# ============================================================
# CHECK FFMPEG
# ============================================================

print()
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
        "FFmpeg is not installed."
    )


# ============================================================
# AUDIO DURATION
# ============================================================

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

duration = float(
    probe.stdout.strip()
)

print(
    f"Audio duration: {duration:.2f} seconds"
)


if duration < 5:

    raise RuntimeError(
        "Narration is too short."
    )


# ============================================================
# CREATE SUBTITLES
# ============================================================

def format_srt_time(seconds):

    milliseconds = int(
        (seconds - int(seconds)) * 1000
    )

    total_seconds = int(seconds)

    hours = total_seconds // 3600

    minutes = (
        total_seconds % 3600
    ) // 60

    secs = total_seconds % 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def create_subtitles(text, duration):

    words = text.split()

    if not words:

        return

    # About 3-5 words per subtitle.
    chunk_size = 4

    chunks = []

    for i in range(
        0,
        len(words),
        chunk_size
    ):

        chunks.append(
            " ".join(
                words[i:i + chunk_size]
            )
        )

    total_characters = sum(
        len(chunk)
        for chunk in chunks
    )

    current_time = 0.0

    srt_lines = []

    for index, chunk in enumerate(
        chunks,
        start=1
    ):

        if total_characters > 0:

            chunk_duration = (
                len(chunk)
                / total_characters
            ) * duration

        else:

            chunk_duration = (
                duration / len(chunks)
            )

        start = current_time

        end = min(
            duration,
            current_time + chunk_duration
        )

        srt_lines.append(
            str(index)
        )

        srt_lines.append(
            f"{format_srt_time(start)} --> "
            f"{format_srt_time(end)}"
        )

        srt_lines.append(
            chunk.upper()
        )

        srt_lines.append("")

        current_time = end

    subtitles_file = (
        OUTPUT_DIR / "subtitles.srt"
    )

    subtitles_file.write_text(
        "\n".join(srt_lines),
        encoding="utf-8"
    )

    return subtitles_file


print()
print("Creating subtitles...")

subtitles_file = create_subtitles(
    script,
    duration
)

print(
    f"Subtitles created: {subtitles_file}"
)


# ============================================================
# DOWNLOAD PEXELS VIDEO
# ============================================================

def search_pexels(query):

    url = (
        "https://api.pexels.com/v1/videos/search"
        f"?query={quote(query)}"
        "&orientation=portrait"
        "&size=medium"
        "&per_page=10"
        "&page=1"
    )

    request = Request(
        url,
        headers={
            "Authorization": PEXELS_API_KEY
        }
    )

    with urlopen(
        request,
        timeout=30
    ) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

    return data.get(
        "videos",
        []
    )


def choose_video(videos):

    candidates = []

    for video in videos:

        files = video.get(
            "video_files",
            []
        )

        for file in files:

            width = file.get(
                "width",
                0
            )

            height = file.get(
                "height",
                0
            )

            link = file.get(
                "link"
            )

            if not link:
                continue

            if width < 720:
                continue

            # Prefer portrait footage.
            ratio = (
                height / width
                if width
                else 0
            )

            candidates.append(
                (
                    ratio,
                    width,
                    height,
                    link,
                    video
                )
            )

    if not candidates:

        return None

    # Prefer portrait video.
    portrait = [
        item
        for item in candidates
        if item[0] >= 1.2
    ]

    if portrait:

        candidates = portrait

    # Prefer reasonably high resolution.
    candidates.sort(
        key=lambda item: item[1] * item[2],
        reverse=True
    )

    return candidates[0]


def download_file(
    url,
    destination
):

    request = Request(
        url,
        headers={
            "User-Agent":
                "Mozilla/5.0"
        }
    )

    with urlopen(
        request,
        timeout=60
    ) as response:

        data = response.read()

    destination.write_bytes(
        data
    )


# ============================================================
# SEARCH AND DOWNLOAD SCENES
# ============================================================

scene_files = []
attributions = []

print()
print("Searching Pexels for video scenes...")


for index, query in enumerate(
    scene_queries,
    start=1
):

    print()
    print(
        f"Searching scene {index}: {query}"
    )

    try:

        videos = search_pexels(
            query
        )

        selected = choose_video(
            videos
        )

        if not selected:

            print(
                "No suitable Pexels video found."
            )

            continue

        (
            ratio,
            width,
            height,
            video_url,
            video_info
        ) = selected

        scene_file = (
            SCENES_DIR
            / f"scene_{index:02d}.mp4"
        )

        print(
            f"Downloading Pexels video "
            f"{video_info.get('id')}"
        )

        download_file(
            video_url,
            scene_file
        )

        scene_files.append(
            scene_file
        )

        creator = video_info.get(
            "user",
            {}
        )

        creator_name = creator.get(
            "name",
            "Unknown"
        )

        creator_url = creator.get(
            "url",
            ""
        )

        pexels_url = video_info.get(
            "url",
            "https://www.pexels.com/"
        )

        attributions.append(
            f"Scene {index}: "
            f"Video by {creator_name} on Pexels\n"
            f"{pexels_url}\n"
            f"Creator: {creator_url}"
        )

        print(
            f"Scene {index} downloaded."
        )

    except Exception as error:

        print(
            f"Scene {index} failed: {error}"
        )


# ============================================================
# REQUIRE AT LEAST ONE VIDEO
# ============================================================

if not scene_files:

    raise RuntimeError(
        "Pexels did not provide any usable videos."
    )


print()
print(
    f"Downloaded {len(scene_files)} "
    f"video scenes."
)


# ============================================================
# SAVE ATTRIBUTION
# ============================================================

attribution_file = (
    OUTPUT_DIR / "pexels_attribution.txt"
)

attribution_text = (
    "Visuals provided by Pexels.\n"
    "https://www.pexels.com/\n\n"
    + "\n\n".join(attributions)
)

attribution_file.write_text(
    attribution_text,
    encoding="utf-8"
)


# ============================================================
# CREATE NORMALIZED SCENE VIDEOS
# ============================================================

scene_duration = duration / len(
    scene_files
)

normalized_files = []


print()
print("Preparing vertical scenes...")


for index, source in enumerate(
    scene_files,
    start=1
):

    normalized = (
        SCENES_DIR
        / f"normalized_{index:02d}.mp4"
    )

    # Scale and crop every video to 1080x1920.
    #
    # The slight zoom is created by making
    # the source a little larger than the
    # final frame before cropping.

    vf = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1,"
        "fps=30"
    )

    command = [
        "ffmpeg",
        "-y",

        "-stream_loop",
        "-1",

        "-i",
        str(source),

        "-t",
        str(scene_duration),

        "-vf",
        vf,

        "-an",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "24",

        "-pix_fmt",
        "yuv420p",

        str(normalized)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print(
            result.stderr
        )

        continue

    normalized_files.append(
        normalized
    )

    print(
        f"Prepared scene {index}."
    )


if not normalized_files:

    raise RuntimeError(
        "Could not normalize any scene videos."
    )


# ============================================================
# CREATE CONCAT FILE
# ============================================================

concat_file = (
    SCENES_DIR / "concat.txt"
)

with concat_file.open(
    "w",
    encoding="utf-8"
) as file:

    for scene in normalized_files:

        absolute_path = (
            scene.resolve()
        )

        safe_path = str(
            absolute_path
        ).replace(
            "'",
            "'\\''"
        )

        file.write(
            f"file '{safe_path}'\n"
        )


# ============================================================
# CONCAT VIDEO SCENES
# ============================================================

background_video = (
    OUTPUT_DIR
    / "background.mp4"
)

print()
print("Combining video scenes...")


concat_command = [
    "ffmpeg",
    "-y",

    "-f",
    "concat",

    "-safe",
    "0",

    "-i",
    str(concat_file),

    "-c",
    "copy",

    str(background_video)
]


concat_result = subprocess.run(
    concat_command,
    capture_output=True,
    text=True
)

if concat_result.returncode != 0:

    print(
        concat_result.stderr
    )

    raise RuntimeError(
        "Could not combine scene videos."
    )


# ============================================================
# FINAL VIDEO
# ============================================================

video_file = (
    OUTPUT_DIR / "video.mp4"
)


# Escape subtitles path for FFmpeg filter.
subtitle_path = str(
    subtitles_file.resolve()
)

subtitle_path = subtitle_path.replace(
    "\\",
    "/"
)

subtitle_path = subtitle_path.replace(
    ":",
    r"\:"
)


# Subtitle styling.
#
# Large white text,
# black outline,
# centered near bottom.
#
# Alignment 2 = bottom center.

subtitle_filter = (
    "subtitles="
    + subtitle_path
    + ":"
    "force_style="
    "'FontName=DejaVu Sans,"
    "FontSize=18,"
    "Bold=1,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BorderStyle=1,"
    "Outline=4,"
    "Shadow=1,"
    "Alignment=2,"
    "MarginV=220'"
)


# ============================================================
# FINAL FFMPEG
# ============================================================

print()
print(
    "Creating final YouTube Short..."
)


final_command = [
    "ffmpeg",
    "-y",

    "-i",
    str(background_video),

    "-i",
    str(audio_file),

    "-vf",
    subtitle_filter,

    "-map",
    "0:v:0",

    "-map",
    "1:a:0",

    "-t",
    str(duration),

    "-c:v",
    "libx264",

    "-preset",
    "medium",

    "-crf",
    "22",

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


final_result = subprocess.run(
    final_command,
    capture_output=True,
    text=True
)


if final_result.returncode != 0:

    print()
    print(
        "FFmpeg final output:"
    )

    print(
        final_result.stderr
    )

    raise RuntimeError(
        "FFmpeg failed to create final video."
    )


# ============================================================
# VERIFY
# ============================================================

if not video_file.exists():

    raise RuntimeError(
        "video.mp4 was not created."
    )


video_size = (
    video_file.stat().st_size
)


if video_size < 10000:

    raise RuntimeError(
        "Generated video appears invalid."
    )


# ============================================================
# DONE
# ============================================================

print()
print("======================================")
print("      YOUTUBE SHORT GENERATED")
print("======================================")

print(
    f"Title:       {title}"
)

print(
    f"Duration:    {duration:.2f} seconds"
)

print(
    "Resolution:  1080x1920"
)

print(
    f"Scenes:      {len(normalized_files)}"
)

print(
    f"Video:       {video_file}"
)

print(
    f"Subtitles:   {subtitles_file}"
)

print(
    f"Attribution: {attribution_file}"
)

print()
print("======================================")
print("NARRATION")
print("======================================")

print(script)

print()
print("======================================")
print("DONE")
print("======================================")