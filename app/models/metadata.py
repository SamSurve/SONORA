"""SONORA Metadata and Artwork Override Models.

Provides strongly validated representations for user-supplied metadata overrides,
safe base64 artwork decoding, MIME validation, and job-isolated temporary storage.
"""

import base64
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Maximum allowable base64 payload size: 15 MB string (~11 MB binary)
MAX_ARTWORK_PAYLOAD_CHARS = 15 * 1024 * 1024
# Maximum allowable decoded binary image size: 10 MB
MAX_ARTWORK_BYTES = 10 * 1024 * 1024

SUPPORTED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def strip_control_characters(s: str | None) -> str | None:
    """Strips dangerous non-printable ASCII control characters.

    Preserves standard whitespace (space, tab, newline) and all valid Unicode characters.
    """
    if s is None:
        return None
    # Remove ASCII control characters C0 (0x00-0x1F except 0x09, 0x0A, 0x0D) and DEL (0x7F)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", s)
    cleaned = cleaned.strip()
    return cleaned if cleaned else None


def validate_and_decode_artwork(artwork_input: str) -> tuple[bytes, str]:
    """Validates and decodes base64 or data URL artwork payloads.

    Args:
        artwork_input: Base64 string or data URL (e.g. data:image/png;base64,...).

    Returns:
        tuple[bytes, str]: Decoded image bytes and file extension (e.g. '.jpg', '.png', '.webp').

    Raises:
        ValueError: If artwork payload exceeds size limits, has unsupported MIME type,
            contains invalid base64 encoding, or contains invalid image magic bytes.
    """
    if not artwork_input or not isinstance(artwork_input, str):
        raise ValueError("Artwork payload must be a non-empty string.")

    if len(artwork_input) > MAX_ARTWORK_PAYLOAD_CHARS:
        raise ValueError(
            f"Artwork payload exceeds maximum length limit of {MAX_ARTWORK_PAYLOAD_CHARS} chars."
        )

    mime_hint: str | None = None
    b64_data = artwork_input.strip()

    # Handle data URL scheme if present (e.g., data:image/jpeg;base64,....)
    if b64_data.startswith("data:"):
        match = re.match(r"^data:(image\/[a-zA-Z0-9\+\-\.]+);base64,(.+)$", b64_data, re.DOTALL)
        if not match:
            raise ValueError("Malformed artwork data URL format.")
        mime_hint = match.group(1).lower()
        b64_data = match.group(2)

    try:
        raw_bytes = base64.b64decode(b64_data, validate=True)
    except Exception as e:
        raise ValueError(f"Invalid base64 encoding for artwork: {e}") from e

    if len(raw_bytes) > MAX_ARTWORK_BYTES:
        raise ValueError(
            f"Decoded artwork size ({len(raw_bytes)} bytes) exceeds limit of "
            f"{MAX_ARTWORK_BYTES} bytes."
        )

    if len(raw_bytes) < 8:
        raise ValueError("Decoded artwork is too small to be a valid image file.")

    # Validate image magic bytes
    detected_ext: str | None = None
    if raw_bytes.startswith(b"\xff\xd8\xff") or raw_bytes.startswith(b"\xff\xd8"):
        detected_ext = ".jpg"
    elif raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_ext = ".png"
    elif raw_bytes.startswith(b"RIFF") and len(raw_bytes) >= 12 and raw_bytes[8:12] == b"WEBP":
        detected_ext = ".webp"
    else:
        raise ValueError("Unsupported or invalid image format. Supported formats: JPEG, PNG, WEBP.")

    if mime_hint and mime_hint in SUPPORTED_IMAGE_TYPES:
        expected_ext = SUPPORTED_IMAGE_TYPES[mime_hint]
        if expected_ext != detected_ext:
            logger.warning(
                "MIME hint '%s' does not match detected magic bytes extension '%s'. Using detected.",
                mime_hint,
                detected_ext,
            )

    return raw_bytes, detected_ext


class MetadataOverride(BaseModel):
    """User-supplied metadata overrides for a single track or global playlist default."""

    title: str | None = Field(
        default=None,
        max_length=500,
        description="Custom track title override",
    )
    artist: str | None = Field(
        default=None,
        max_length=500,
        description="Custom artist override",
    )
    album: str | None = Field(
        default=None,
        max_length=500,
        description="Custom album override",
    )
    year: int | None = Field(
        default=None,
        ge=1000,
        le=2100,
        description="Release year override between 1000 and 2100",
    )
    artwork: str | None = Field(
        default=None,
        description="Custom artwork in base64 or data URL format",
    )

    @field_validator("title", "artist", "album", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return strip_control_characters(v)
        return strip_control_characters(str(v))

    @field_validator("year", mode="before")
    @classmethod
    def validate_year_input(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            if v < 1000 or v > 2100:
                raise ValueError("Year must be between 1000 and 2100.")
            return v
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return None
            try:
                year_int = int(val)
                if year_int < 1000 or year_int > 2100:
                    raise ValueError("Year must be between 1000 and 2100.")
                return year_int
            except ValueError:
                raise ValueError(f"Invalid release year: '{v}'. Must be a 4-digit number.") from None
        raise ValueError(f"Invalid year type: {type(v).__name__}")

    @field_validator("artwork", mode="before")
    @classmethod
    def validate_artwork_payload(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ValueError("Artwork must be a valid base64 or data URL string.")
        # Pre-validate base64 and magic bytes
        validate_and_decode_artwork(v)
        return v


def save_artwork_to_isolated_temp(
    artwork_input: str,
    target_dir: Path,
    file_prefix: str = "custom_artwork",
) -> Path:
    """Decodes and writes custom artwork into a job-isolated temporary directory.

    Args:
        artwork_input: Validated base64/data URL string.
        target_dir: Isolated job temporary directory.
        file_prefix: Destination file prefix.

    Returns:
        Path: Absolute path to the created image file in the isolated temp dir.
    """
    raw_bytes, ext = validate_and_decode_artwork(artwork_input)
    target_dir.mkdir(parents=True, exist_ok=True)
    artwork_path = target_dir / f"{file_prefix}{ext}"
    artwork_path.write_bytes(raw_bytes)
    return artwork_path
