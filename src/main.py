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


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

if not PIXABAY_API_KEY:
    raise RuntimeError("PIXABAY_API_KEY is missing.")

MODEL = "gemini-3.5-flash-lite"
VOICE = "en-US-GuyNeural"

OUTPUT_DIR = Path("output")
SCENES_DIR = OUTPUT_DIR / "scenes"

OUTPUT_DIR.mkdir(exist_ok=True)
SCENES_DIR.mkdir(exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def run_command(command, check=True):
    print("Running:", " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if check and result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def download_file(url, destination, timeout=120):
    print(f"Downloading: {url}")

    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(req, timeout=timeout) as response:
        data = response.read()

    Path(destination).write_bytes(data)

    if not Path(destination).exists() or Path(destination).stat().st_size < 1000:
        raise RuntimeError(f"Downloaded file is invalid: {destination}")

    return destination


def clean_text(text):
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def extract_field(text, field):
    pattern = rf"(?im)^\s*{re.escape(field)}\s*:\s*(.+?)\s*$"
    match = re.search(pattern, text)

    if match:
        return clean_text(match.group(1))

    return ""


def extract_multiline_field(text, field, next_fields):
    pattern = (
        rf"(?is)"
        rf"{re.escape(field)}\s*:\s*"
        rf"(.*?)"
        rf"(?=\n\s*(?:{'|'.join(map(re.escape, next_fields))})\s*:|\Z)"
    )

    match = re.search(pattern, text)

    if not match:
        return ""

    return clean_text(match.group(1))


# ============================================================
# GEMINI
# ============================================================

def generate_content():
    print("Generating history short with Gemini...")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = """
Create one highly engaging English YouTube Short about a real historical
event, person, invention, mystery, disaster, or surprising historical fact.

The video should be approximately 40-60 seconds long.

Use simple but interesting spoken English.

Return EXACTLY this structure:

TITLE: ...
HOOK: ...
SCRIPT: ...
DESCRIPTION: ...
TAGS: ...

SCENE1: ...
SCENE2: ...
SCENE3: ...
SCENE4: ...
SCENE5: ...
SCENE6: ...

Rules:

- SCRIPT should be approximately 100-135 spoken words.
- The first sentence must be a strong hook.
- Do not use fake historical facts.
- Do not invent quotes.
- Make the story easy to understand without prior knowledge.
- The ending should contain an interesting final fact or twist.
- SCENE1 through SCENE6 must each contain 3 alternative stock-media search queries.
- Separate the 3 queries with " | ".
- Each query should contain only 3-8 simple English words.
- Queries should describe things that could realistically exist as stock footage
  or historical-looking imagery.
- Do NOT use exact names of copyrighted films or television shows.
- Prefer visual concepts over abstract concepts.

Example:

SCENE1: ancient roman city fire | old city burning | historical city fire
"""

    last_error = None

    for attempt in range(1, 6):
        try:
            print(f"Gemini attempt {attempt}/5...")

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt
            )

            text = response.text

            if not text or len(text.strip()) < 100:
                raise RuntimeError("Gemini returned an empty or very short response.")

            print("Gemini response received.")

            return text

        except Exception as exc:
            last_error = exc

            print(f"Gemini attempt failed: {exc}")

            if attempt < 5:
                wait_time = attempt * 15
                print(f"Waiting {wait_time} seconds...")
                time.sleep(wait_time)

    raise RuntimeError(
        f"Gemini failed after 5 attempts: {last_error}"
    )


# ============================================================
# PARSE GEMINI
# ============================================================

def parse_gemini(text):
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

    description = extract_field(text, "DESCRIPTION")
    tags = extract_field(text, "TAGS")

    scenes = {}

    for i in range(1, 7):
        scenes[i] = extract_field(text, f"SCENE{i}")

    if not script:
        raise RuntimeError("Gemini did not return a usable SCRIPT.")

    if not title:
        title = "Amazing Historical Fact"

    for i in range(1, 7):
        if not scenes[i]:
            scenes[i] = "historical scene | old city | history"

    return {
        "title": title,
        "hook": hook,
        "script": script,
        "description": description,
        "tags": tags,
        "scenes": scenes
    }


# ============================================================
# SAVE SCRIPT
# ============================================================

def save_script(data, raw_response):
    script_file = OUTPUT_DIR / "script.txt"

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(raw_response)

    narration_file = OUTPUT_DIR / "narration.txt"

    with open(narration_file, "w", encoding="utf-8") as f:
        f.write(data["script"])

    metadata_file = OUTPUT_DIR / "metadata.txt"

    with open(metadata_file, "w", encoding="utf-8") as f:
        f.write(f"TITLE: {data['title']}\n\n")
        f.write(f"DESCRIPTION: {data['description']}\n\n")
        f.write(f"TAGS: {data['tags']}\n\n")

        for i in range(1, 7):
            f.write(f"SCENE{i}: {data['scenes'][i]}\n")

    print("Script and metadata saved.")


# ============================================================
# TEXT TO SPEECH
# ============================================================

async def generate_voice(script):
    print("Generating voice...")

    output = OUTPUT_DIR / "voice.mp3"

    communicate = edge_tts.Communicate(
        script,
        VOICE
    )

    await communicate.save(str(output))

    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("Voice generation failed.")

    print("Voice generated successfully.")

    return output


# ============================================================
# FFMPEG CHECK
# ============================================================

def check_ffmpeg():
    print("Checking FFmpeg...")

    result = subprocess.run(
        ["ffmpeg", "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError("FFmpeg is not available.")

    print("FFmpeg available.")


def get_audio_duration(audio_file):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_file)
        ]
    )

    return float(result.stdout.strip())


# ============================================================
# SUBTITLES
# ============================================================

def format_srt_time(seconds):
    milliseconds = int(round((seconds % 1) * 1000))
    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{secs:02d},"
        f"{milliseconds:03d}"
    )


def create_subtitles(script, duration):
    print("Creating subtitles...")

    words = script.split()

    if not words:
        raise RuntimeError("No words available for subtitles.")

    # Around 4 words per subtitle
    chunks = []

    current = []

    for word in words:
        current.append(word)

        if len(current) >= 4:
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)

    total_chars = sum(
        len(" ".join(chunk))
        for chunk in chunks
    )

    current_time = 0.0

    subtitle_file = OUTPUT_DIR / "subtitles.srt"

    with open(subtitle_file, "w", encoding="utf-8") as f:

        for index, chunk in enumerate(chunks, start=1):
            text = " ".join(chunk).upper()

            chars = len(" ".join(chunk))

            chunk_duration = (
                duration * chars / total_chars
            )

            start = current_time
            end = min(
                duration,
                current_time + chunk_duration
            )

            f.write(f"{index}\n")
            f.write(
                f"{format_srt_time(start)} --> "
                f"{format_srt_time(end)}\n"
            )
            f.write(text)
            f.write("\n\n")

            current_time = end

    print(f"Subtitles created: {subtitle_file}")

    return subtitle_file


# ============================================================
# PIXABAY API
# ============================================================

def pixabay_request(endpoint, params):
    params = dict(params)

    params["key"] = PIXABAY_API_KEY

    query = "&".join(
        f"{quote(str(key))}={quote(str(value))}"
        for key, value in params.items()
    )

    url = f"{endpoint}?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()

        return json.loads(raw.decode("utf-8"))

    except HTTPError as exc:
        body = ""

        try:
            body = exc.read().decode(
                "utf-8",
                errors="replace"
            )
        except Exception:
            pass

        print(
            f"Pixabay HTTP error {exc.code}: {body[:500]}"
        )

        return None

    except URLError as exc:
        print(f"Pixabay connection error: {exc}")

        return None

    except Exception as exc:
        print(f"Pixabay request error: {exc}")

        return None


def split_queries(scene_query):
    parts = [
        clean_text(x)
        for x in scene_query.split("|")
        if clean_text(x)
    ]

    if not parts:
        parts = [scene_query]

    return parts[:3]


# ============================================================
# PIXABAY VIDEO SEARCH
# ============================================================

def search_pixabay_video(query):
    print(f"  Searching Pixabay videos: {query}")

    data = pixabay_request(
        "https://pixabay.com/api/videos/",
        {
            "q": query,
            "lang": "en",
            "video_type": "all",
            "safesearch": "true",
            "order": "popular",
            "per_page": 10,
            "page": 1
        }
    )

    if not data:
        return None

    hits = data.get("hits", [])

    if not hits:
        print("  No video results.")
        return None

    candidates = []

    for hit in hits:
        videos = hit.get("videos", {})

        # Prefer large, then medium, then small
        for quality in ["large", "medium", "small"]:
            item = videos.get(quality)

            if not item:
                continue

            url = item.get("url")
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            size = int(item.get("size") or 0)

            if not url:
                continue

            if width < 640 or height < 360:
                continue

            if size <= 0:
                continue

            ratio = width / height if height else 0

            # Prefer videos that are not extremely wide.
            # Landscape is fine because FFmpeg will crop it.
            crop_penalty = abs(ratio - (9 / 16))

            score = (
                min(width, 1920) / 100
                + min(height, 1080) / 100
                + min(size / 1_000_000, 20)
                - crop_penalty * 5
            )

            candidates.append({
                "url": url,
                "width": width,
                "height": height,
                "size": size,
                "score": score,
                "page_url": hit.get("pageURL", ""),
                "user": hit.get("user", ""),
                "id": hit.get("id")
            })

            break

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    best = candidates[0]

    print(
        f"  Video found: "
        f"{best['width']}x{best['height']} "
        f"by {best['user']}"
    )

    return best


# ============================================================
# PIXABAY IMAGE SEARCH
# ============================================================

def search_pixabay_image(query):
    print(f"  Searching Pixabay images: {query}")

    data = pixabay_request(
        "https://pixabay.com/api/",
        {
            "q": query,
            "lang": "en",
            "image_type": "all",
            "orientation": "all",
            "safesearch": "true",
            "order": "popular",
            "per_page": 10,
            "page": 1
        }
    )

    if not data:
        return None

    hits = data.get("hits", [])

    if not hits:
        print("  No image results.")
        return None

    candidates = []

    for hit in hits:
        url = (
            hit.get("largeImageURL")
            or hit.get("fullHDURL")
            or hit.get("webformatURL")
        )

        if not url:
            continue

        width = int(hit.get("imageWidth") or 0)
        height = int(hit.get("imageHeight") or 0)

        if width < 640 or height < 360:
            continue

        ratio = width / height if height else 0

        score = (
            min(width, 1920) / 100
            + min(height, 1080) / 100
            - abs(ratio - (9 / 16)) * 5
            + min(int(hit.get("likes") or 0), 1000) / 1000
        )

        candidates.append({
            "url": url,
            "width": width,
            "height": height,
            "score": score,
            "page_url": hit.get("pageURL", ""),
            "user": hit.get("user", ""),
            "id": hit.get("id")
        })

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    best = candidates[0]

    print(
        f"  Image found: "
        f"{best['width']}x{best['height']} "
        f"by {best['user']}"
    )

    return best


# ============================================================
# GENERIC BACKGROUND
# ============================================================

def create_fallback_background(index, duration):
    """
    Last-resort background.

    This ensures that the workflow can still produce a video
    even when Pixabay has no usable media for a scene.
    """

    output = SCENES_DIR / f"scene_{index:02d}_fallback.mp4"

    # Slightly different movement for every scene.
    zoom_values = [
        "zoompan=z='min(zoom+0.0007,1.12)':d=1",
        "zoompan=z='min(zoom+0.0005,1.10)':d=1",
        "zoompan=z='max(zoom-0.0005,1.00)':d=1",
        "zoompan=z='min(zoom+0.0006,1.11)':d=1",
        "zoompan=z='max(zoom-0.0004,1.00)':d=1",
        "zoompan=z='min(zoom+0.0004,1.09)':d=1"
    ]

    zoom = zoom_values[(index - 1) % len(zoom_values)]

    filter_complex = (
        "color=c=0x101820:s=1080x1920:r=30,"
        "format=yuv420p,"
        f"{zoom}:s=1080x1920,"
        "setsar=1"
    )

    run_command([
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x101820:s=1080x1920:r=30",
        "-t",
        str(duration),
        "-vf",
        "format=yuv420p,"
        "drawbox=x=0:y=0:w=iw:h=ih:"
        "color=black@0.12:t=fill",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "25",
        str(output)
    ])

    return output


# ============================================================
# NORMALIZE VIDEO
# ============================================================

def normalize_video(input_file, output_file, duration, index):
    print(
        f"  Normalizing scene {index}: "
        f"{duration:.2f}s"
    )

    # Crop landscape footage into 9:16.
    # Add a tiny zoom so static-looking footage feels less flat.
    filter_complex = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1,"
        "fps=30,"
        "format=yuv420p"
    )

    run_command([
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(input_file),
        "-t",
        str(duration),
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
        str(output_file)
    ])

    return output_file


# ============================================================
# CREATE IMAGE SCENE
# ============================================================

def create_image_scene(
    image_file,
    output_file,
    duration,
    index
):
    print(
        f"  Creating animated image scene {index}..."
    )

    # Different movement direction for each scene.
    expressions = [
        "zoompan=z='min(zoom+0.0010,1.14)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920",

        "zoompan=z='min(zoom+0.0008,1.12)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920",

        "zoompan=z='max(zoom-0.0005,1.0)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920",

        "zoompan=z='min(zoom+0.0007,1.11)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920",

        "zoompan=z='max(zoom-0.0004,1.0)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920",

        "zoompan=z='min(zoom+0.0006,1.10)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920"
    ]

    expression = expressions[(index - 1) % len(expressions)]

    vf = (
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1,"
        f"{expression},"
        "fps=30,"
        "format=yuv420p"
    )

    # Number of frames needed.
    frames = max(1, int(duration * 30))

    run_command([
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_file),
        "-vf",
        vf,
        "-frames:v",
        str(frames),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
 