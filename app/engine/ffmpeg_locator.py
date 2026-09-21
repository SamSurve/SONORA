"""Auralis Dynamic Cross-Platform FFmpeg Discovery & Resolution.

Discovers, verifies, and selects the FFmpeg binary without hardcoding absolute paths
or relying on shell execution.
"""

import os
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings


class FFmpegNotFoundException(Exception):
    """Raised when no functional FFmpeg binary can be discovered on the system."""


def verify_ffmpeg(executable_path: str | Path) -> tuple[bool, str]:
    """Verifies that an executable is a valid, functioning FFmpeg binary.

    Executes '<path> -version' strictly with shell=False and a 5-second timeout.

    Returns:
        tuple (is_valid, version_string_or_error)
    """
    path_obj = Path(executable_path)
    if not path_obj.exists() or not path_obj.is_file():
        return False, f"File does not exist: {executable_path}"

    try:
        # Strictly shell=False to prevent command injection
        result = subprocess.run(  # noqa: S603
            [str(path_obj), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            shell=False,
        )
        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0] if result.stdout else "Unknown version"
            return True, first_line
        return (
            False,
            f"Process exited with non-zero code {result.returncode}: {result.stderr.strip()}",
        )
    except subprocess.TimeoutExpired:
        return False, "FFmpeg version verification timed out after 5 seconds."
    except Exception as e:
        return False, f"Failed to execute FFmpeg binary: {e}"


def get_ffmpeg_path(custom_path: str | Path | None = None) -> str:
    """Discovers and returns the path to a verified FFmpeg binary.

    Resolution Priority:
        1. Custom explicit path passed as argument.
        2. Config / Environment variable 'FFMPEG_PATH'.
        3. System PATH ('ffmpeg' or 'ffmpeg.exe').
        4. Local repository root fallback ('./ffmpeg.exe' or './ffmpeg').
        5. Local vendor directory ('vendor/ffmpeg/ffmpeg.exe').

    Returns:
        Verified canonical path string to the FFmpeg executable.

    Raises:
        FFmpegNotFoundException: If no valid FFmpeg binary could be found and verified.
    """
    candidates: list[Path] = []

    # 1. Custom path argument
    if custom_path:
        candidates.append(Path(custom_path))

    # 2. Config / Environment variable override
    env_override = settings.FFMPEG_PATH or os.getenv("FFMPEG_PATH")
    if env_override:
        candidates.append(Path(env_override))

    # 3. System PATH lookup
    binary_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    system_path = shutil.which(binary_name) or shutil.which("ffmpeg")
    if system_path:
        candidates.append(Path(system_path))

    # 4. Local repository root fallback (preserving legacy prototype compatibility)
    repo_root = Path(__file__).resolve().parents[2]
    root_binary = repo_root / binary_name
    if root_binary.exists():
        candidates.append(root_binary)

    # 5. Local vendor fallback
    vendor_binary = repo_root / "vendor" / "ffmpeg" / binary_name
    if vendor_binary.exists():
        candidates.append(vendor_binary)

    # Test candidates in order of priority
    failure_log: list[str] = []
    for candidate in candidates:
        is_valid, msg = verify_ffmpeg(candidate)
        if is_valid:
            return str(candidate.resolve())
        failure_log.append(f"Candidate '{candidate}': {msg}")

    # If all candidates fail or none exist
    error_details = "\n  - ".join(failure_log) if failure_log else "No candidates found."
    raise FFmpegNotFoundException(
        "Could not locate a functioning FFmpeg binary. Please ensure FFmpeg is installed "
        "on your system PATH or specify FFMPEG_PATH in your .env file.\n"
        f"Evaluation details:\n  - {error_details}"
    )
