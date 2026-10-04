import os
import re
import json
import time
import subprocess
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from google import genai
import edge_tts
from youtube_upload import upload_video


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing")

if not PIXABAY_API_KEY:
    raise RuntimeError("PIXABAY_API_KEY is missing")

MODEL = "gemini-3.5-flash-lite"
VOICE = "en-US-GuyNeural"

OUTPUT_DIR = Path("output")
SCENES_DIR = OUTPUT_DIR / "scenes"

# Persistent topic history.
# This file should NOT be deleted between runs.
TOPIC_HISTORY_FILE = Path("used_topics.json")

MAX_TOPIC_HISTORY = 100


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command):
    print("RUN:", " ".join(map(str, command)))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result.stdout


def download_file(url, output_path):
    output_path = Path(output_path)

    print("Downloading:", url)

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(request, timeout=60) as response:
        data = response.read()

    output_path.write_bytes(data)

    print(
        "Downloaded:",
        output_path,
        f"({len(data) / 1024 / 1024:.2f} MB)"
    )


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_field(text, field):
    pattern = rf"(?im)^{re.escape(field)}\s*:\s*(.+)$"

    match = re.search(pattern, text)

    if not match:
        return ""

    return clean_text(match.group(1))


def extract_multiline_field(text, field, next_fields):
    pattern = (
        rf"(?is)"
        rf"^{re.escape(field)}\s*:\s*"
        rf"(.*?)"
        rf"(?=^({'|'.join(map(re.escape, next_fields))})\s*:|\Z)"
    )

    match = re.search(pattern, text, re.MULTILINE)

    if not match:
        return ""

    return clean_text(match.group(1))


# ============================================================
# TOPIC HISTORY
# ============================================================

def load_used_topics():
    """
    Loads previously generated topics.

    The history is intentionally stored outside output/
    so clean-up of generated files cannot delete it.
    """

    if not TOPIC_HISTORY_FILE.exists():
        return []

    try:
        data = json.loads(
            TOPIC_HISTORY_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, list):
            return []

        return data

    except Exception as e:
        print(
            "WARNING: Could not read topic history:",
            e
        )

        return []


def save_used_topic(title, script):
    """
    Saves the generated topic so future runs can avoid it.
    """

    history = load_used_topics()

    record = {
        "title": clean_text(title),
        "script": clean_text(script)[:800],
        "timestamp": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.gmtime()
        )
    }

    history.append(record)

    # Keep only the newest entries.
    history = history[-MAX_TOPIC_HISTORY:]

    TOPIC_HISTORY_FILE.write_text(
        json.dumps(
            history,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"Saved topic history: {record['title']}"
    )


def format_topic_history(history):
    """
    Creates a compact list for Gemini.
    """

    if not history:
        return "No previous topics."

    lines = []

    for item in history[-MAX_TOPIC_HISTORY:]:
        title = clean_text(
            item.get("title", "")
        )

        if title:
            lines.append(
                f"- {title}"
            )

    return "\n".join(lines)


# ============================================================
# GEMINI CONTENT GENERATION
# ============================================================

def generate_content():
    print("Generating content with Gemini...")

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    history = load_used_topics()
    history_text = format_topic_history(history)

    prompt = f"""
Create ONE highly engaging English YouTube Short about a REAL historical event,
historical discovery, unusual true event, strange moment in history,
important invention, disaster, exploration event, war event, scientific event,
or surprising historical fact.

The video must be approximately 40–60 seconds.

IMPORTANT TOPIC RULE:
Do NOT reuse a previous topic.
Do NOT create a topic that is essentially the same event, person, invention,
disaster, war, discovery, or historical episode as a previous topic.

For example, if "atomic bomb" or Hiroshima/Nagasaki has already been used,
do NOT make another video about:
- atomic bombs
- nuclear bombs
- Hiroshima
- Nagasaki
- the Manhattan Project
- the first atomic bomb
- nuclear weapons
or another closely related version.

Choose something substantially different.

PREVIOUS TOPICS:
{history_text}

VISUAL STYLE:
The video must be visually active and exciting.

Avoid scenes that are only:
- a person standing still
- a static building
- a portrait
- a document
- a map
- an empty landscape
- a generic object sitting on a table

Prefer scenes containing visible movement such as:
- people moving
- crowds
- soldiers marching
- vehicles
- trains
- ships
- aircraft
- machinery
- construction
- destruction
- explosions
- smoke
- fire
- storms
- waves
- factories
- workers
- running
- streets
- movement through cities
- historical reenactment-like footage
- dramatic environmental movement
- camera movement
- action

The opening scene is especially important.
SCENE1 must have the strongest and most visually interesting footage possible.

The video will use Pixabay stock footage and images,
so scene descriptions must be practical search queries.

Do not request copyrighted movie or TV footage.

CONTENT RULES:
- Everything must be factually real.
- Do not invent quotes.
- Do not invent statistics.
- Do not exaggerate facts as if they were true.
- Make the hook immediately interesting.
- The first 2–3 seconds should create curiosity.
- Keep the story easy to understand.
- Use natural spoken English.
- End with a surprising or memorable fact.

SCRIPT:
Write approximately 100–135 spoken words.

OUTPUT FORMAT:

TITLE:
One short YouTube title.

HOOK:
One short sentence that immediately creates curiosity.

SCRIPT:
The complete narration.

DESCRIPTION:
Write a short, engaging description related to the video topic.

After the video description, ALWAYS add exactly this fixed promotional section,
with one blank line before each paragraph:

Start trading crypto, forex and indices with low fees on PrimeXBT: https://bit.ly/4y41bl8

You want to become partner? Sign up on: https://bit.ly/3TkBSgt.

Do NOT modify, rewrite, remove, or replace these two promotional paragraphs.
Do NOT add any other promotional links.
Do NOT put hashtags after the promotional section.

TAGS:
5–10 relevant tags separated by commas.

SCENE1:
query 1 | query 2 | query 3

SCENE2:
query 1 | query 2 | query 3

SCENE3:
query 1 | query 2 | query 3

SCENE4:
query 1 | query 2 | query 3

SCENE5:
query 1 | query 2 | query 3

SCENE6:
query 1 | query 2 | query 3

IMPORTANT:
Each scene must contain exactly 3 short Pixabay search queries.

Each query should contain approximately 3–8 simple English words.

Queries should describe visible things that can actually appear in footage.

Make SCENE1 the most dramatic and visually interesting.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    text = response.text.strip()

    print("\n========== GEMINI OUTPUT ==========\n")
    print(text)
    print("\n===================================\n")

    return text


# ============================================================
# PARSE GEMINI
# ============================================================

def parse_gemini(text):
    next_fields = [
        "TITLE",
        "HOOK",
        "SCRIPT",
        "DESCRIPTION",
        "TAGS",
        "SCENE1",
        "SCENE2",
        "SCENE3",
        "SCENE4",
        "SCENE5",
        "SCENE6"
    ]

    title = extract_field(text, "TITLE")
    hook = extract_field(text, "HOOK")

    script = extract_multiline_field(
        text,
        "SCRIPT",
        [
            "DESCRIPTION",
            "TAGS",
            "SCENE1"
        ]
    )

    description = extract_field(
        text,
        "DESCRIPTION"
    )

    tags = extract_field(
        text,
        "TAGS"
    )

    scenes = []

    for i in range(1, 7):
        scene = extract_field(
            text,
            f"SCENE{i}"
        )

        queries = [
            clean_text(x)
            for x in scene.split("|")
            if clean_text(x)
        ]

        scenes.append(
            queries[:3]
        )

    if not title:
        title = "Interesting Historical Event"

    if not script:
        raise RuntimeError(
            "Gemini did not return a usable SCRIPT."
        )

    if not hook:
        hook = script[:120]

    return {
        "title": title,
        "hook": hook,
        "script": script,
        "description": description,
        "tags": tags,
        "scenes": scenes
    }


# ============================================================
# TEXT TO SPEECH
# ============================================================

async def create_voice(script, output_path):
    print("Generating voice...")

    communicate = edge_tts.Communicate(
        script,
        VOICE
    )

    await communicate.save(
        str(output_path)
    )

    print(
        "Voice saved:",
        output_path
    )


def create_voice_sync(script, output_path):
    import asyncio

    asyncio.run(
        create_voice(
            script,
            output_path
        )
    )


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not determine media duration."
        )

    return float(
        result.stdout.strip()
    )


# ============================================================
# PIXABAY API
# ============================================================

def pixabay_video_search(query):
    print(
        "Pixabay video search:",
        query
    )

    encoded_query = quote(query)

    url = (
        "https://pixabay.com/api/videos/"
        f"?key={PIXABAY_API_KEY}"
        f"&q={encoded_query}"
        "&per_page=20"
        "&safesearch=true"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:
        with urlopen(
            request,
            timeout=30
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as e:
        print(
            "Pixabay video HTTP error:",
            e.code
        )
        return []

    except URLError as e:
        print(
            "Pixabay video URL error:",
            e
        )
        return []

    except Exception as e:
        print(
            "Pixabay video error:",
            e
        )
        return []

    return data.get(
        "hits",
        []
    )


def score_video(video):
    """
    Scores videos primarily for vertical-video usefulness,
    resolution and visual activity.
    """

    score = 0

    videos = video.get(
        "videos",
        {}
    )

    for quality in [
        "large",
        "medium",
        "small"
    ]:
        item = videos.get(
            quality
        )

        if not item:
            continue

        width = item.get(
            "width",
            0
        )

        height = item.get(
            "height",
            0
        )

        size = item.get(
            "size",
            0
        )

        score += width * height * 0.000001
        score += min(
            size / 1_000_000,
            20
        )

    score += min(
        video.get("views", 0) / 1000,
        20
    )

    score += min(
        video.get("downloads", 0) / 1000,
        20
    )

    score += min(
        video.get("likes", 0) / 100,
        20
    )

    return score


def choose_best_video(results):
    if not results:
        return None

    ranked = sorted(
        results,
        key=score_video,
        reverse=True
    )

    for video in ranked:
        videos = video.get(
            "videos",
            {}
        )

        candidates = []

        for quality in [
            "large",
            "medium",
            "small"
        ]:
            item = videos.get(
                quality
            )

            if item and item.get("url"):
                candidates.append(
                    item
                )

        if not candidates:
            continue

        # Prefer the highest resolution available.
        candidates.sort(
            key=lambda x:
            x.get("width", 0) *
            x.get("height", 0),
            reverse=True
        )

        return candidates[0]["url"]

    return None


def pixabay_image_search(query):
    print(
        "Pixabay image search:",
        query
    )

    encoded_query = quote(query)

    url = (
        "https://pixabay.com/api/"
        f"?key={PIXABAY_API_KEY}"
        f"&q={encoded_query}"
        "&image_type=photo"
        "&orientation=vertical"
        "&per_page=20"
        "&safesearch=true"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:
        with urlopen(
            request,
            timeout=30
        ) as response:
            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as e:
        print(
            "Pixabay image HTTP error:",
            e.code
        )
        return []

    except URLError as e:
        print(
            "Pixabay image URL error:",
            e
        )
        return []

    except Exception as e:
        print(
            "Pixabay image error:",
            e
        )
        return []

    return data.get(
        "hits",
        []
    )


def choose_best_image(results):
    if not results:
        return None

    ranked = sorted(
        results,
        key=lambda x:
        (
            x.get("imageWidth", 0) *
            x.get("imageHeight", 0)
        ),
        reverse=True
    )

    for item in ranked:
        url = item.get(
            "largeImageURL"
        )

        if url:
            return url

    return None


# ============================================================
# FALLBACK BACKGROUND
# ============================================================

def create_fallback_background(output_path):
    print(
        "Creating fallback background..."
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x111111:s=1080x1920:d=5",
            "-frames:v",
            "1",
            str(output_path)
        ]
    )


# ============================================================
# VIDEO NORMALIZATION
# ============================================================

def normalize_video(
    input_path,
    output_path,
    duration
):
    """
    Converts horizontal/vertical stock footage into
    1080x1920 with a subtle moving crop.
    """

    filter_complex = (
        "scale=1200:2134:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920:"
        "x='(iw-1080)/2 + "
        "min(max(sin(t*0.45)*(iw-1080)/4,"
        "-(iw-1080)/4),"
        "(iw-1080)/4)':"
        "y='(ih-1920)/2',"
        "fps=30,"
        f"trim=duration={duration:.3f},"
        "setpts=PTS-STARTPTS"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            filter_complex,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{duration:.3f}",
            str(output_path)
        ]
    )


# ============================================================
# IMAGE SCENE
# ============================================================

def create_image_scene(
    image_path,
    output_path,
    duration
):
    print(
        "Creating animated image scene..."
    )

    frames = max(
        int(duration * 30),
        1
    )

    filter_complex = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"zoompan="
        f"z='min(zoom+0.0008,1.12)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={frames}:"
        f"s=1080x1920:"
        f"fps=30"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-vf",
            filter_complex,
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            str(output_path)
        ]
    )


# ============================================================
# CREATE SCENE
# ============================================================

def create_scene(
    scene_number,
    queries,
    duration
):
    scene_dir = SCENES_DIR

    scene_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    video_source = (
        scene_dir /
        f"scene_{scene_number}_source.mp4"
    )

    image_source = (
        scene_dir /
        f"scene_{scene_number}_source.jpg"
    )

    final_scene = (
        scene_dir /
        f"scene_{scene_number}.mp4"
    )

    # Scene 1 gets an extra push toward active footage.
    modified_queries = list(queries)

    if scene_number == 1:
        modified_queries = [
            f"dramatic action {q}"
            for q in modified_queries
        ]

    # --------------------------------------------------------
    # Try videos first.
    # --------------------------------------------------------

    for query in modified_queries:

        results = pixabay_video_search(
            query
        )

        url = choose_best_video(
            results
        )

        if not url:
            continue

        try:
            download_file(
                url,
                video_source
            )

            normalize_video(
                video_source,
                final_scene,
                duration
            )

            if final_scene.exists():
                return final_scene

        except Exception as e:
            print(
                "Video processing failed:",
                e
            )

    # --------------------------------------------------------
    # If video failed, try images.
    # --------------------------------------------------------

    for query in modified_queries:

        results = pixabay_image_search(
            query
        )

        url = choose_best_image(
            results
        )

        if not url:
            continue

        try:
            download_file(
                url,
                image_source
            )

            create_image_scene(
                image_source,
                final_scene,
                duration
            )

            if final_scene.exists():
                return final_scene

        except Exception as e:
            print(
                "Image processing failed:",
                e
            )

    # --------------------------------------------------------
    # Final fallback.
    # --------------------------------------------------------

    create_fallback_background(
        final_scene
    )

    return final_scene


# ============================================================
# SUBTITLES
# ============================================================

def split_into_subtitle_chunks(script):
    """
    Creates readable subtitle chunks.

    These are intentionally short so subtitles remain
    easy to read on a phone.
    """

    words = script.split()

    chunks = []

    current = []

    for word in words:
        current.append(word)

        clean_word = word.rstrip(
            ".,!?;:"
        )

        if (
            len(current) >= 4
            or word.endswith((".", "!", "?"))
        ):
            chunks.append(
                " ".join(current)
            )
            current = []

    if current:
        chunks.append(
            " ".join(current)
        )

    return chunks


def format_srt_time(seconds):
    hours = int(seconds // 3600)

    minutes = int(
        (seconds % 3600) // 60
    )

    secs = int(
        seconds % 60
    )

    millis = int(
        round(
            (seconds - int(seconds))
            * 1000
        )
    )

    if millis >= 1000:
        millis -= 1000
        secs += 1

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{millis:03d}"
    )


def create_subtitles(
    script,
    duration,
    output_path
):
    chunks = split_into_subtitle_chunks(
        script
    )

    if not chunks:
        return

    total_words = sum(
        len(chunk.split())
        for chunk in chunks
    )

    current_time = 0.0
    subtitle_lines = []

    for index, chunk in enumerate(chunks, 1):

        word_count = len(
            chunk.split()
        )

        chunk_duration = (
            duration *
            word_count /
            total_words
        )

        start = current_time
        end = min(
            current_time +
            chunk_duration,
            duration
        )

        subtitle_lines.append(
            f"{index}\n"
            f"{format_srt_time(start)} --> "
            f"{format_srt_time(end)}\n"
            f"{chunk}\n"
        )

        current_time = end

    output_path.write_text(
        "\n".join(subtitle_lines),
        encoding="utf-8"
    )


# ============================================================
# FINAL VIDEO
# ============================================================

def create_final_video(
    scene_paths,
    voice_path,
    subtitle_path,
    output_path,
    duration
):
    print(
        "Combining scenes..."
    )

    concat_file = (
        SCENES_DIR /
        "concat.txt"
    )

    lines = []

    for scene in scene_paths:
        absolute = scene.resolve()

        lines.append(
            f"file '{str(absolute).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'"
        )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    combined_video = (
        SCENES_DIR /
        "combined.mp4"
    )

    run_command(
        [
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
            str(combined_video)
        ]
    )

    subtitle_filter = (
        "subtitles="
        f"'{str(subtitle_path).replace(':', '\\:')}'"
        ":force_style="
        "'FontName=DejaVu Sans,"
        "FontSize=20,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=125'"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(combined_video),
            "-i",
            str(voice_path),
            "-vf",
            subtitle_filter,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt",
            "yuv420p",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(output_path)
        ]
    )


# ============================================================
# ATTRIBUTION
# ============================================================

def create_attribution(
    title,
    description,
    tags
):
    attribution_file = (
        OUTPUT_DIR /
        "attribution.txt"
    )

    text = f"""TITLE
{title}

DESCRIPTION
{description}

TAGS
{tags}

VISUAL SOURCE
Pixabay

VOICE
Microsoft Edge TTS

VIDEO GENERATION
Gemini + FFmpeg
"""

    attribution_file.write_text(
        text,
        encoding="utf-8"
    )


# ============================================================
# CLEAN OLD GENERATED FILES
# ============================================================

def clean_old_files():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SCENES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    files_to_remove = [
        OUTPUT_DIR / "voice.mp3",
        OUTPUT_DIR / "subtitles.srt",
        OUTPUT_DIR / "final.mp4",
        OUTPUT_DIR / "script.txt",
        OUTPUT_DIR / "metadata.json",
        OUTPUT_DIR / "attribution.txt"
    ]

    for path in files_to_remove:
        if path.exists():
            path.unlink()

    if SCENES_DIR.exists():
        for path in SCENES_DIR.iterdir():
            if path.is_file():
                path.unlink()


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n==============================")
    print("AI HISTORY SHORT GENERATOR")
    print("==============================\n")

    clean_old_files()

    # --------------------------------------------------------
    # Generate content.
    # --------------------------------------------------------

    raw_content = generate_content()

    data = parse_gemini(
        raw_content
    )

    print("\nTITLE:")
    print(data["title"])

    print("\nHOOK:")
    print(data["hook"])

    print("\nSCRIPT:")
    print(data["script"])

    # --------------------------------------------------------
    # Save topic BEFORE finishing.
    # This makes the next run aware of it.
    # --------------------------------------------------------

    save_used_topic(
        data["title"],
        data["script"]
    )

    # --------------------------------------------------------
    # Save script.
    # --------------------------------------------------------

    script_file = (
        OUTPUT_DIR /
        "script.txt"
    )

    script_file.write_text(
        data["script"],
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Save metadata.
    # --------------------------------------------------------

    metadata_file = (
        OUTPUT_DIR /
        "metadata.json"
    )

    metadata_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Generate voice.
    # --------------------------------------------------------

    voice_path = (
        OUTPUT_DIR /
        "voice.mp3"
    )

    create_voice_sync(
        data["script"],
        voice_path
    )

    # --------------------------------------------------------
    # Determine exact voice duration.
    # --------------------------------------------------------

    duration = get_media_duration(
        voice_path
    )

    print(
        f"Voice duration: {duration:.2f}s"
    )

    # Make sure video remains within Shorts range.
    duration = max(
        1.0,
        min(
            duration,
            60.0
        )
    )

    # --------------------------------------------------------
    # Create subtitles.
    # --------------------------------------------------------

    subtitle_path = (
        OUTPUT_DIR /
        "subtitles.srt"
    )

    create_subtitles(
        data["script"],
        duration,
        subtitle_path
    )

    # --------------------------------------------------------
    # Create scenes.
    # --------------------------------------------------------

    scene_count = 6

    scene_duration = (
        duration /
        scene_count
    )

    scene_paths = []

    for index in range(scene_count):

        queries = []

        if index < len(
            data["scenes"]
        ):
            queries = data["scenes"][index]

        if not queries:
            queries = [
                "historical event",
                "people history",
                "dramatic history"
            ]

        print(
            f"\nCreating scene {index + 1}/{scene_count}"
        )

        scene = create_scene(
            index + 1,
            queries,
            scene_duration
        )

        scene_paths.append(
            scene
        )

    # --------------------------------------------------------
    # Final video.
    # --------------------------------------------------------

    final_video = (
        OUTPUT_DIR /
        "final.mp4"
    )

    create_final_video(
        scene_paths,
        voice_path,
        subtitle_path,
        final_video,
        duration
    )

    # --------------------------------------------------------
    # Attribution.
    # --------------------------------------------------------

    create_attribution(
        data["title"],
        data["description"],
        data["tags"]
    )

    # --------------------------------------------------------
    # Final checks.
    # --------------------------------------------------------

    if not final_video.exists():
        raise RuntimeError(
            "Final video was not created."
        )

    final_size = (
        final_video.stat().st_size /
        1024 /
        1024
    )

    print("\n==============================")
    print("GENERATION COMPLETE")
    print("==============================")
    print(
        f"Video: {final_video}"
    )
    print(
        f"Size: {final_size:.2f} MB"
    )
    print(
        f"Duration: {duration:.2f}s"
    )
    print(
        f"Topic history: {TOPIC_HISTORY_FILE}"
    )
    print("==============================\n")
    # --------------------------------------------------------
    # Upload and schedule YouTube video.
    # --------------------------------------------------------

    print("\n==============================")
    print("UPLOADING TO YOUTUBE")
    print("==============================\n")

    tags = [
        tag.strip()
        for tag in data["tags"].split(",")
        if tag.strip()
    ]

    youtube_description = data["description"].strip()

    if not youtube_description:
        youtube_description = (
            "An interesting real historical event explained "
            "in a short and engaging video."
        )

    upload_video(
        video_path=final_video,
        title=data["title"],
        description=youtube_description,
        tags=tags
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
