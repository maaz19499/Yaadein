import io
import json
import os
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw

from src.services.images import resize_image_width


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def is_ffprobe_available() -> bool:
    """Check if ffprobe is available on the system PATH."""
    return shutil.which("ffprobe") is not None


def extract_video_metadata(
    video_bytes: bytes,
) -> tuple[int | None, int | None, int | None]:
    """
    Extracts (duration_seconds, width, height) from video bytes.
    Uses ffprobe if available, otherwise attempts basic container inspection or fallback.
    """
    if is_ffprobe_available():
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                tmp_path,
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = None
                width = None
                height = None

                format_data = data.get("format", {})
                if "duration" in format_data:
                    try:
                        duration = int(float(format_data["duration"]))
                    except (ValueError, TypeError):
                        pass

                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        width = stream.get("width")
                        height = stream.get("height")
                        if duration is None and "duration" in stream:
                            try:
                                duration = int(float(stream["duration"]))
                            except (ValueError, TypeError):
                                pass
                        break

                return duration, width, height
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # Fallback default metadata if ffprobe is not installed
    return None, 1920, 1080


def _generate_fallback_frame(width: int = 1920, height: int = 1080) -> bytes:
    """
    Generates a sleek dark poster image with a play indicator when ffmpeg is unavailable.
    """
    # Create dark slate background
    img = Image.new("RGB", (width, height), color=(20, 24, 33))
    draw = ImageDraw.Draw(img)

    # Draw centered play icon
    center_x = width // 2
    center_y = height // 2
    radius = min(width, height) // 8

    # Outer circle
    draw.ellipse(
        [
            (center_x - radius, center_y - radius),
            (center_x + radius, center_y + radius),
        ],
        fill=(37, 43, 58),
        outline=(99, 102, 241),
        width=4,
    )

    # Play triangle
    tri_len = radius // 2
    tri_points = [
        (center_x - tri_len // 2, center_y - tri_len),
        (center_x - tri_len // 2, center_y + tri_len),
        (center_x + tri_len, center_y),
    ]
    draw.polygon(tri_points, fill=(255, 255, 255))

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()


def generate_video_thumbnails(
    video_bytes: bytes, timestamp_seconds: float = 1.0
) -> tuple[bytes, bytes]:
    """
    Extracts a frame from the video at timestamp_seconds and produces:
    - thumbnail_webp: 400px width WebP
    - preview_webp: 1600px width WebP
    """
    frame_bytes = None

    if is_ffmpeg_available():
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_in:
            tmp_in.write(video_bytes)
            tmp_in_path = tmp_in.name

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_out:
            tmp_out_path = tmp_out.name

        try:
            # Seek timestamp and extract 1 single frame
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp_seconds),
                "-i",
                tmp_in_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                tmp_out_path,
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20
            )
            if result.returncode == 0 and os.path.exists(tmp_out_path):
                with open(tmp_out_path, "rb") as f:
                    frame_bytes = f.read()
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_in_path):
                try:
                    os.remove(tmp_in_path)
                except Exception:
                    pass
            if os.path.exists(tmp_out_path):
                try:
                    os.remove(tmp_out_path)
                except Exception:
                    pass

    if not frame_bytes:
        frame_bytes = _generate_fallback_frame()

    thumbnail_bytes = resize_image_width(frame_bytes, 400)
    preview_bytes = resize_image_width(frame_bytes, 1600)
    return thumbnail_bytes, preview_bytes
