"""Automated Verification of Prototype Preservation.

Guarantees that pre-existing legacy files (app.py, music_fixer.py, templates/index.html,
and ffmpeg.exe) are strictly unmodified and remain runnable.
"""

import hashlib
from pathlib import Path

EXPECTED_HASHES = {
    "app.py": "1F901CF48C6A250FF2294BA5A663046742410F45640DFA2DF888F9BA9F062D65",
    "music_fixer.py": "39D4B7FA9C4B8A07F4248659230F76A9EAFEF6ED72B4152DA2DF577E7A37F940",
    "templates/index.html": "4A3A6727CBE033AEBA3ED211560FEE30389E4E6A1F88EFE2E7A08A5788FF7EE9",
    "ffmpeg.exe": "BA242553F0FF60AD788069D5D376C1B4F7A2F3A3566416E0ED950CA7920DA5FA",
}


def compute_sha256(file_path: Path) -> str:
    """Calculates SHA256 hex digest for a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


class TestPrototypePreservation:
    """Ensures absolute integrity and runnability of legacy prototype assets."""

    def test_legacy_files_exist(self) -> None:
        for filename in EXPECTED_HASHES:
            target = Path(filename)
            assert target.exists(), f"Legacy file '{filename}' was missing or moved!"
            assert target.is_file(), f"Legacy path '{filename}' is not a regular file!"

    def test_legacy_file_hashes_unmodified(self) -> None:
        for filename, expected_hash in EXPECTED_HASHES.items():
            actual_hash = compute_sha256(Path(filename))
            assert actual_hash == expected_hash, (
                f"STRICT PRESERVATION VIOLATION: '{filename}' hash changed!\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}"
            )

    def test_legacy_downloads_dir_intact(self) -> None:
        downloads_dir = Path("downloads")
        assert downloads_dir.exists()
        assert downloads_dir.is_dir()

    def test_legacy_app_is_runnable(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("legacy_app", "app.py")
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "app")
        routes = [rule.rule for rule in mod.app.url_map.iter_rules()]
        assert "/" in routes
        assert "/download" in routes
