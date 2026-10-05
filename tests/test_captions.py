"""
tests/test_captions.py
Tests the caption/subtitle selection and download logic using fakes
modeled on pytubefix's real Caption/CaptionQuery API (captions is
dict-like: iterable, and indexable by language code — see
pytubefix/query.py CaptionQuery and pytubefix/captions.py Caption).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from youtube_service import download_captions, list_captions


class FakeCaption:
    def __init__(self, code, name):
        self.code = code
        self.name = name

    def download(self, title, srt=True, output_path=None, filename_prefix=None):
        # Mirrors pytubefix's real Caption.download() filename convention.
        filename = f"{title} ({self.code}).srt"
        path = os.path.join(output_path, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nFake subtitle\n")
        return path


class FakeCaptionQuery(dict):
    """A dict subclass behaves exactly like pytubefix's CaptionQuery for
    our purposes: iterable (yields values, like CaptionQuery.__iter__
    does) and indexable by code."""

    def __iter__(self):
        return iter(self.values())


class FakeYouTube:
    def __init__(self, captions_dict):
        self.captions = FakeCaptionQuery(captions_dict)


def test_list_captions_returns_all_tracks():
    yt = FakeYouTube({"en": FakeCaption("en", "English"), "fr": FakeCaption("fr", "French")})
    options = list_captions(yt)
    codes = {o.code for o in options}
    assert codes == {"en", "fr"}


def test_list_captions_empty_video_returns_empty_list():
    yt = FakeYouTube({})
    assert list_captions(yt) == []


def test_download_captions_prefers_manual_english(tmp_path):
    yt = FakeYouTube({
        "a.en": FakeCaption("a.en", "English (auto-generated)"),
        "en": FakeCaption("en", "English"),
        "fr": FakeCaption("fr", "French"),
    })
    path = download_captions(yt, "My Video", str(tmp_path))
    assert path is not None
    assert path.endswith("(en).srt")
    assert os.path.exists(path)


def test_download_captions_falls_back_to_auto_generated_english(tmp_path):
    yt = FakeYouTube({"a.en": FakeCaption("a.en", "English (auto-generated)"), "fr": FakeCaption("fr", "French")})
    path = download_captions(yt, "My Video", str(tmp_path))
    assert path.endswith("(a.en).srt")


def test_download_captions_falls_back_to_first_available_language(tmp_path):
    yt = FakeYouTube({"de": FakeCaption("de", "German")})
    path = download_captions(yt, "My Video", str(tmp_path))
    assert path.endswith("(de).srt")


def test_download_captions_returns_none_when_no_captions_exist(tmp_path):
    yt = FakeYouTube({})
    assert download_captions(yt, "My Video", str(tmp_path)) is None
