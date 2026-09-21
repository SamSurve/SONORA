"""Automated Tests for Audio Conversion and Mutagen Tagging."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import AudioFormat
from app.engine.audio_tagger import convert_audio, tag_audio_file


class TestAudioConversionPipeline:
    """Tests for FFmpeg audio transcoding execution."""

    def test_missing_input_file_raises_error(self, tmp_path: Path) -> None:
        missing_input = tmp_path / "nonexistent.opus"
        output_file = tmp_path / "output.mp3"
        with pytest.raises(FileNotFoundError):
            convert_audio(missing_input, output_file, AudioFormat.MP3_320)

    @patch("subprocess.run")
    def test_ffmpeg_command_args_and_no_shell(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        input_file = tmp_path / "input.webm"
        input_file.write_bytes(b"dummy audio data")
        output_file = tmp_path / "output.mp3"

        convert_audio(input_file, output_file, AudioFormat.MP3_320, quality_kbps="320")

        # Verify subprocess.run was called with shell=False
        assert mock_run.called
        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is False
        assert kwargs.get("check") is False

        # Verify command arguments
        cmd = mock_run.call_args[0][0]
        assert "-vn" in cmd
        assert "-c:a" in cmd
        assert "libmp3lame" in cmd
        assert "320k" in cmd

    @patch("subprocess.run")
    def test_flac_conversion_command(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        input_file = tmp_path / "input.opus"
        input_file.write_bytes(b"dummy audio data")
        output_file = tmp_path / "output.flac"

        convert_audio(input_file, output_file, AudioFormat.FLAC)

        cmd = mock_run.call_args[0][0]
        assert "flac" in cmd
        assert "-vn" in cmd

    @patch("subprocess.run")
    def test_wav_conversion_command(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        input_file = tmp_path / "input.opus"
        input_file.write_bytes(b"dummy audio data")
        output_file = tmp_path / "output.wav"

        convert_audio(input_file, output_file, "wav")

        cmd = mock_run.call_args[0][0]
        assert "pcm_s16le" in cmd
        assert "-vn" in cmd

    @patch("app.engine.audio_tagger.get_ffmpeg_path", return_value="ffmpeg")
    @patch("subprocess.run")
    def test_ffmpeg_failure_raises_runtime_error(
        self, mock_run: MagicMock, mock_get_path: MagicMock, tmp_path: Path
    ) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="Corrupt audio stream")

        input_file = tmp_path / "corrupt.opus"
        input_file.write_bytes(b"corrupt")
        output_file = tmp_path / "output.mp3"

        with pytest.raises(RuntimeError, match="FFmpeg conversion failed"):
            convert_audio(input_file, output_file, AudioFormat.MP3_320)


class TestMetadataAndArtworkTagging:
    """Tests for Mutagen metadata tagging across formats."""

    def test_tagging_missing_file_returns_false(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.mp3"
        success = tag_audio_file(missing, title="Test Track")
        assert success is False

    @patch("app.engine.audio_tagger.ID3")
    def test_tag_mp3_metadata_and_artwork(self, mock_id3_cls: MagicMock, tmp_path: Path) -> None:
        mock_id3 = MagicMock()
        mock_id3_cls.return_value = mock_id3

        mp3_file = tmp_path / "test.mp3"
        mp3_file.write_bytes(b"dummy mp3 header")
        artwork = tmp_path / "cover.jpg"
        artwork.write_bytes(b"\xff\xd8\xff\xe0dummy jpeg")

        success = tag_audio_file(
            file_path=mp3_file,
            title="Solaris Chill",
            artist="Auralis Labs",
            album="Ambient Dreams",
            track_number=3,
            artwork_path=artwork,
        )

        assert success is True
        assert mock_id3.add.called
        assert mock_id3.save.called

    @patch("app.engine.audio_tagger.FLAC")
    def test_tag_flac_metadata(self, mock_flac_cls: MagicMock, tmp_path: Path) -> None:
        mock_flac = MagicMock()
        mock_flac_cls.return_value = mock_flac

        flac_file = tmp_path / "test.flac"
        flac_file.write_bytes(b"fLaC dummy")

        success = tag_audio_file(
            file_path=flac_file,
            title="Lossless Container Test",
            artist="Producer",
            track_number=1,
        )

        assert success is True
        assert mock_flac.save.called
