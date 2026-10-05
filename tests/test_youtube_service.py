"""
tests/test_youtube_service.py
Tests for the stream-selection logic (the exact code that caused the
original "video downloads without sound / doesn't download at all" bug).

These tests don't hit the network. Instead, FakeStream/FakeStreamQuery
faithfully reproduce the relevant parts of pytubefix's real
Stream/StreamQuery API (verified by reading pytubefix's own source,
see query.py: filter(), order_by(), desc(), asc(), first(), last(),
get_highest_resolution(), get_lowest_resolution()), so the selection
functions under test run through the exact same code paths they would
against a real YouTube object.
"""

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from youtube_service import (
    CancelToken,
    DownloadCancelled,
    ffmpeg_available,
    select_adaptive_video_stream,
    select_progressive_stream,
)


# --------------------------------------------------------------- Fakes
@dataclass
class FakeStream:
    resolution: str | None
    progressive: bool
    adaptive: bool
    only_video: bool
    only_audio: bool
    subtype: str
    filesize: int = 1000


class FakeStreamQuery:
    def __init__(self, streams):
        self.streams = list(streams)

    def __len__(self):
        return len(self.streams)

    def filter(self, res=None, progressive=None, adaptive=None, only_video=None,
               only_audio=None, subtype=None, mime_type=None):
        result = self.streams
        if res is not None:
            result = [s for s in result if s.resolution == res]
        if progressive is not None:
            result = [s for s in result if s.progressive == progressive]
        if adaptive is not None:
            result = [s for s in result if s.adaptive == adaptive]
        if only_video is not None:
            result = [s for s in result if s.only_video == only_video]
        if only_audio is not None:
            result = [s for s in result if s.only_audio == only_audio]
        if subtype is not None:
            result = [s for s in result if s.subtype == subtype]
        return FakeStreamQuery(result)

    def order_by(self, attribute_name):
        has_attr = [s for s in self.streams if getattr(s, attribute_name) is not None]
        return FakeStreamQuery(
            sorted(has_attr, key=lambda s: int(getattr(s, attribute_name).rstrip("p")))
        )

    def desc(self):
        return FakeStreamQuery(self.streams[::-1])

    def asc(self):
        return self

    def first(self):
        return self.streams[0] if self.streams else None

    def last(self):
        return self.streams[-1] if self.streams else None

    # Mirrors pytubefix's StreamQuery.get_highest_resolution /
    # get_lowest_resolution exactly (same composition of filter/order_by).
    def get_highest_resolution(self, progressive=True, mime_type=None):
        return self.filter(progressive=progressive, mime_type=mime_type).order_by("resolution").last()

    def get_lowest_resolution(self, progressive=True):
        return self.filter(progressive=progressive, subtype="mp4").order_by("resolution").first()


class FakeYouTube:
    def __init__(self, streams):
        self.streams = FakeStreamQuery(streams)


def _mk(resolution, progressive=False, adaptive=False, only_video=False,
        only_audio=False, subtype="mp4"):
    return FakeStream(resolution, progressive, adaptive, only_video, only_audio, subtype)


# ------------------------------------------------- select_progressive_stream
class TestSelectProgressiveStream:
    def test_finds_highest_progressive_when_only_360p_exists(self):
        """This is exactly the real-world case that caused the original bug:
        a video with no progressive stream above 360p."""
        yt = FakeYouTube([
            _mk("360p", progressive=True),
            _mk("720p", adaptive=True, only_video=True),
            _mk("1080p", adaptive=True, only_video=True),
        ])
        stream = select_progressive_stream(yt, "Highest")
        assert stream is not None
        assert stream.resolution == "360p"

    def test_returns_none_when_no_progressive_stream_exists_at_all(self):
        """Modern 4K-only uploads sometimes have zero progressive streams."""
        yt = FakeYouTube([
            _mk("1080p", adaptive=True, only_video=True),
            _mk("2160p", adaptive=True, only_video=True),
        ])
        assert select_progressive_stream(yt, "Highest") is None
        assert select_progressive_stream(yt, "Lowest") is None

    def test_specific_resolution_lookup(self):
        yt = FakeYouTube([
            _mk("360p", progressive=True),
            _mk("480p", progressive=True),
        ])
        stream = select_progressive_stream(yt, "480p")
        assert stream is not None
        assert stream.resolution == "480p"

    def test_specific_resolution_not_available_returns_none(self):
        yt = FakeYouTube([_mk("360p", progressive=True)])
        assert select_progressive_stream(yt, "1080p") is None


# --------------------------------------------- select_adaptive_video_stream
class TestSelectAdaptiveVideoStream:
    def test_picks_highest_resolution_mp4(self):
        yt = FakeYouTube([
            _mk("360p", progressive=True),
            _mk("720p", adaptive=True, only_video=True, subtype="mp4"),
            _mk("1080p", adaptive=True, only_video=True, subtype="mp4"),
        ])
        stream = select_adaptive_video_stream(yt, "Highest")
        assert stream is not None
        assert stream.resolution == "1080p"

    def test_picks_lowest_resolution(self):
        yt = FakeYouTube([
            _mk("720p", adaptive=True, only_video=True, subtype="mp4"),
            _mk("1080p", adaptive=True, only_video=True, subtype="mp4"),
        ])
        stream = select_adaptive_video_stream(yt, "Lowest")
        assert stream is not None
        assert stream.resolution == "720p"

    def test_exact_resolution_match(self):
        yt = FakeYouTube([
            _mk("720p", adaptive=True, only_video=True, subtype="mp4"),
            _mk("1080p", adaptive=True, only_video=True, subtype="mp4"),
        ])
        stream = select_adaptive_video_stream(yt, "720p")
        assert stream.resolution == "720p"

    def test_falls_back_to_non_mp4_when_no_mp4_adaptive_exists(self):
        """Some videos only expose adaptive video in webm — the selector
        must not simply give up in that case."""
        yt = FakeYouTube([
            _mk("1080p", adaptive=True, only_video=True, subtype="webm"),
        ])
        stream = select_adaptive_video_stream(yt, "Highest")
        assert stream is not None
        assert stream.subtype == "webm"

    def test_returns_none_when_no_adaptive_video_exists_at_all(self):
        yt = FakeYouTube([_mk("360p", progressive=True)])
        assert select_adaptive_video_stream(yt, "Highest") is None


# --------------------------------------------------------- CancelToken
class TestCancelToken:
    def test_not_cancelled_by_default(self):
        token = CancelToken()
        assert not token.cancelled
        token.check()  # should not raise

    def test_cancel_raises_on_check(self):
        token = CancelToken()
        token.cancel()
        assert token.cancelled
        try:
            token.check()
            assert False, "expected DownloadCancelled to be raised"
        except DownloadCancelled:
            pass

    def test_reset_clears_cancellation(self):
        token = CancelToken()
        token.cancel()
        token.reset()
        assert not token.cancelled
        token.check()  # should not raise


def test_ffmpeg_available_returns_bool():
    assert isinstance(ffmpeg_available(), bool)
