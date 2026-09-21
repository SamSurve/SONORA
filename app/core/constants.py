"""Auralis Constants, Enumerations, and Audio Format Taxonomy.

This module formalizes supported audio formats, processing states, error codes,
and explicit acoustic semantics.
"""

from enum import Enum
from typing import NamedTuple


class AudioSemantics(NamedTuple):
    """Accurate description of audio quality and encoding properties."""

    display_name: str
    extension: str
    is_native: bool
    is_lossy_transcode: bool
    is_lossless_container: bool
    description: str


class AudioFormat(str, Enum):
    """Supported target audio format selections."""

    NATIVE_OPUS = "opus"
    NATIVE_M4A = "m4a"
    MP3_320 = "mp3_320"
    MP3_256 = "mp3_256"
    MP3_VBR = "mp3_vbr"
    FLAC = "flac"


# Formal acoustic taxonomy mapping
AUDIO_TAXONOMY: dict[AudioFormat, AudioSemantics] = {
    AudioFormat.NATIVE_OPUS: AudioSemantics(
        display_name="Direct Stream Copy (Opus)",
        extension="opus",
        is_native=True,
        is_lossy_transcode=False,
        is_lossless_container=False,
        description=(
            "Direct container extraction (~50-160 kbps Opus). Zero re-encoding; "
            "zero generational loss; fastest download."
        ),
    ),
    AudioFormat.NATIVE_M4A: AudioSemantics(
        display_name="Direct Stream Copy (M4A/AAC)",
        extension="m4a",
        is_native=True,
        is_lossy_transcode=False,
        is_lossless_container=False,
        description=(
            "Direct container extraction (~128-256 kbps AAC). Native stream copy; "
            "broad Apple device compatibility."
        ),
    ),
    AudioFormat.MP3_320: AudioSemantics(
        display_name="MP3 320 kbps (High Compatibility)",
        extension="mp3",
        is_native=False,
        is_lossy_transcode=True,
        is_lossless_container=False,
        description=(
            "Lossy-to-lossy transcode at 320 kbps CBR. Does not increase acoustic "
            "fidelity of lossy source, but provides universal compatibility."
        ),
    ),
    AudioFormat.MP3_256: AudioSemantics(
        display_name="MP3 256 kbps (Balanced)",
        extension="mp3",
        is_native=False,
        is_lossy_transcode=True,
        is_lossless_container=False,
        description="Lossy-to-lossy transcode at 256 kbps CBR. Balanced storage and quality.",
    ),
    AudioFormat.MP3_VBR: AudioSemantics(
        display_name="MP3 VBR V0 (Optimized)",
        extension="mp3",
        is_native=False,
        is_lossy_transcode=True,
        is_lossless_container=False,
        description="Variable bitrate (~245 kbps). High perceptual quality with reduced file size.",
    ),
    AudioFormat.FLAC: AudioSemantics(
        display_name="FLAC (Lossless Container)",
        extension="flac",
        is_native=False,
        is_lossy_transcode=False,
        is_lossless_container=True,
        description=(
            "Decodes source audio to PCM and encapsulates in FLAC. Does NOT restore "
            "frequencies discarded by source lossy compression, but prevents further "
            "codec compression artifacts."
        ),
    ),
}


class JobStatus(str, Enum):
    """Lifecycle states for download and conversion jobs."""

    QUEUED = "queued"
    FETCHING_METADATA = "fetching_metadata"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    TAGGING = "tagging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ErrorCode(str, Enum):
    """Standardized API and engine error codes."""

    INVALID_URL = "INVALID_URL"
    SSRF_VIOLATION = "SSRF_VIOLATION"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    STORAGE_LIMIT_EXCEEDED = "STORAGE_LIMIT_EXCEEDED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    FFMPEG_NOT_FOUND = "FFMPEG_NOT_FOUND"
    DOWNLOAD_CANCELLED = "DOWNLOAD_CANCELLED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
