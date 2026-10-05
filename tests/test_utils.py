"""
tests/test_utils.py
Unit tests for the pure helper functions in utils.py.
Run with: pytest
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import format_duration, format_size, sanitize_filename, unique_path


class TestSanitizeFilename:
    def test_removes_illegal_characters(self):
        assert sanitize_filename('My/Video:Test*?"<>|.mp4') == "MyVideoTest.mp4"

    def test_strips_trailing_dots_and_spaces(self):
        assert sanitize_filename("Video Title...  ") == "Video Title"

    def test_empty_name_falls_back_to_video(self):
        assert sanitize_filename("") == "video"
        assert sanitize_filename("???") == "video"

    def test_truncates_long_names(self):
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        assert len(result) <= 150

    def test_normal_name_is_unchanged(self):
        assert sanitize_filename("My Great Video 2024") == "My Great Video 2024"


class TestUniquePath:
    def test_returns_plain_name_if_not_taken(self, tmp_path):
        result = unique_path(str(tmp_path), "video", "mp4")
        assert result == "video.mp4"

    def test_appends_counter_if_taken(self, tmp_path):
        (tmp_path / "video.mp4").touch()
        result = unique_path(str(tmp_path), "video", "mp4")
        assert result == "video (1).mp4"

    def test_increments_counter_past_multiple_existing(self, tmp_path):
        (tmp_path / "video.mp4").touch()
        (tmp_path / "video (1).mp4").touch()
        (tmp_path / "video (2).mp4").touch()
        result = unique_path(str(tmp_path), "video", "mp4")
        assert result == "video (3).mp4"


class TestFormatDuration:
    def test_under_a_minute(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(125) == "2:05"

    def test_hours_minutes_seconds(self):
        assert format_duration(3725) == "1:02:05"

    def test_zero(self):
        assert format_duration(0) == "0:00"


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500.00 B"

    def test_kilobytes(self):
        assert format_size(2048) == "2.00 KB"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.00 MB"

    def test_gigabytes(self):
        assert format_size(3 * 1024 ** 3) == "3.00 GB"

    def test_terabytes_do_not_return_none(self):
        # Regression test: the original implementation silently returned
        # None for sizes >= 1024 GB instead of formatting as TB.
        result = format_size(2 * 1024 ** 4)
        assert result is not None
        assert "TB" in result
