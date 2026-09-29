import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_credentials():
    return Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def get_next_publish_time():
    timezone = ZoneInfo("Europe/Sarajevo")
    now = datetime.now(timezone)

    publish_hour = int(os.environ.get("YOUTUBE_PUBLISH_HOUR", "20"))
    publish_minute = int(os.environ.get("YOUTUBE_PUBLISH_MINUTE", "0"))

    publish_time = now.replace(
        hour=publish_hour,
        minute=publish_minute,
        second=0,
        microsecond=0,
    )

    if publish_time <= now:
        publish_time += timedelta(days=1)

    return publish_time


def upload_video(video_path, title, description, tags=None):
    video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video ne postoji: {video_path}")

    credentials = get_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
    )

    publish_time = get_next_publish_time()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "categoryId": "28",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_time.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
            "selfDeclaredMadeForKids": False,
        },
    }

    if tags:
        body["snippet"]["tags"] = tags[:500]

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = request.execute()

    video_id = response["id"]

    print("")
    print("========================================")
    print("YOUTUBE UPLOAD USPJEŠAN")
    print("========================================")
    print("Video ID:", video_id)
    print("Zakazano za:", publish_time.isoformat())
    print("URL: https://www.youtube.com/watch?v=" + video_id)
    print("========================================")

    return video_id