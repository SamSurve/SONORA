"""Auralis Media Processing and Audio Tagging Engine.

Provides metadata injection, cover artwork embedding across MP3, M4A, FLAC, and Opus,
and safe FFmpeg audio conversion without shell execution.
"""

import base64
import logging
import subprocess
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus

from app.core.constants import AudioFormat
from app.engine.ffmpeg_locator import get_ffmpeg_path

logger = logging.getLogger(__name__)


def convert_audio(
    input_file: Path,
    output_file: Path,
    target_format: AudioFormat | str,
    quality_kbps: str = "320",
) -> Path:
    """Transcodes an input audio/video file to the specified audio format using FFmpeg.

    Executes strictly with shell=False.

    Args:
        input_file: Source audio or video file.
        output_file: Target output audio file path.
        target_format: AudioFormat enum or string (e.g. 'mp3_320', 'flac', 'opus').
        quality_kbps: Bitrate in kbps for CBR audio.

    Returns:
        Path to the converted output file.

    Raises:
        subprocess.CalledProcessError: If FFmpeg transcode fails.
        FileNotFoundError: If input file is missing.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_file}")

    ffmpeg_bin = get_ffmpeg_path()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    format_str = (
        target_format.value if isinstance(target_format, AudioFormat) else str(target_format)
    )

    # Base command: overwrite output, no video stream
    cmd: list[str] = [ffmpeg_bin, "-y", "-i", str(input_file), "-vn"]

    if "mp3" in format_str:
        cmd.extend(["-c:a", "libmp3lame"])
        if "vbr" in format_str:
            cmd.extend(["-q:a", "0"])
        else:
            bitrate = "256k" if "256" in format_str else f"{quality_kbps}k"
            cmd.extend(["-b:a", bitrate])
    elif "flac" in format_str:
        cmd.extend(["-c:a", "flac"])
    elif "opus" in format_str:
        cmd.extend(["-c:a", "libopus", "-b:a", "160k"])
    elif "m4a" in format_str or "aac" in format_str:
        cmd.extend(["-c:a", "aac", "-b:a", "256k"])
    elif "wav" in format_str:
        cmd.extend(["-c:a", "pcm_s16le"])
    else:
        # Default MP3 320k
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])

    cmd.append(str(output_file))

    logger.debug("Executing FFmpeg conversion: %s", " ".join(cmd))
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=180,
    )

    if result.returncode != 0:
        logger.error("FFmpeg conversion failed: %s", result.stderr)
        raise RuntimeError(f"FFmpeg conversion failed: {result.stderr.strip()}")

    return output_file


def _detect_image_mime(image_path: Path) -> str:
    """Infers MIME type from image file extension."""
    ext = image_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    elif ext == ".png":
        return "image/png"
    elif ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def tag_audio_file(
    file_path: Path,
    title: str,
    artist: str = "Unknown Artist",
    album: str | None = None,
    track_number: int | None = None,
    artwork_path: Path | None = None,
) -> bool:
    """Injects metadata tags and embeds cover art into an audio file.

    Supports MP3 (ID3v2.4), M4A (MP4/AAC), FLAC, and Ogg/Opus.

    Returns:
        True if tagging succeeded or was partially applied; False on error.
    """
    if not file_path.exists():
        logger.warning("Tagging skipped; file not found: %s", file_path)
        return False

    album_title = album or title
    ext = file_path.suffix.lower()

    artwork_data: bytes | None = None
    mime_type = "image/jpeg"
    if artwork_path and artwork_path.exists():
        try:
            artwork_data = artwork_path.read_bytes()
            mime_type = _detect_image_mime(artwork_path)
        except Exception as e:
            logger.warning("Could not read artwork file '%s': %e", artwork_path, e)

    try:
        if ext == ".mp3":
            _tag_mp3(file_path, title, artist, album_title, track_number, artwork_data, mime_type)
        elif ext == ".m4a":
            _tag_m4a(file_path, title, artist, album_title, track_number, artwork_data)
        elif ext == ".flac":
            _tag_flac(file_path, title, artist, album_title, track_number, artwork_data, mime_type)
        elif ext == ".opus":
            _tag_opus(file_path, title, artist, album_title, track_number, artwork_data, mime_type)
        return True
    except Exception as e:
        logger.warning("Failed to tag audio file '%s': %s", file_path, e)
        return False


def _tag_mp3(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: int | None,
    artwork_data: bytes | None,
    mime_type: str,
) -> None:
    try:
        tags = ID3(str(file_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))

    if track_number is not None:
        tags.add(TRCK(encoding=3, text=str(track_number)))

    if artwork_data:
        tags.add(
            APIC(
                encoding=3,
                mime=mime_type,
                type=3,  # Front cover
                desc="Cover",
                data=artwork_data,
            )
        )

    tags.save(str(file_path), v2_version=4)


def _tag_m4a(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: int | None,
    artwork_data: bytes | None,
) -> None:
    audio = MP4(str(file_path))
    audio["\xa9nam"] = [title]
    audio["\xa9ART"] = [artist]
    audio["\xa9alb"] = [album]

    if track_number is not None:
        audio["trkn"] = [(track_number, 0)]

    if artwork_data:
        if artwork_data.startswith(b"\x89PNG"):
            image_format = MP4Cover.FORMAT_PNG
            audio["covr"] = [MP4Cover(artwork_data, imageformat=image_format)]
        elif artwork_data.startswith(b"\xff\xd8\xff") or artwork_data.startswith(b"\xff\xd8"):
            image_format = MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(artwork_data, imageformat=image_format)]
        else:
            logger.warning(
                "Unsupported image magic bytes for M4A cover tagging on '%s'.", file_path
            )

    audio.save()


def _tag_flac(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: int | None,
    artwork_data: bytes | None,
    mime_type: str,
) -> None:
    audio = FLAC(str(file_path))
    audio["title"] = [title]
    audio["artist"] = [artist]
    audio["album"] = [album]

    if track_number is not None:
        audio["tracknumber"] = [str(track_number)]

    if artwork_data:
        picture = Picture()
        picture.type = 3  # Front cover
        picture.mime = mime_type
        picture.desc = "Cover"
        picture.data = artwork_data
        audio.clear_pictures()
        audio.add_picture(picture)

    audio.save()


def _tag_opus(
    file_path: Path,
    title: str,
    artist: str,
    album: str,
    track_number: int | None,
    artwork_data: bytes | None,
    mime_type: str,
) -> None:
    audio = OggOpus(str(file_path))
    audio["title"] = [title]
    audio["artist"] = [artist]
    audio["album"] = [album]

    if track_number is not None:
        audio["tracknumber"] = [str(track_number)]

    if artwork_data:
        pic = Picture()
        pic.type = 3
        pic.mime = mime_type
        pic.desc = "Cover"
        pic.data = artwork_data
        # Ogg Opus uses METADATA_BLOCK_PICTURE base64 encoded
        encoded_pic = base64.b64encode(pic.write()).decode("ascii")
        audio["metadata_block_picture"] = [encoded_pic]

    audio.save()
