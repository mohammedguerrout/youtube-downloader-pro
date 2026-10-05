"""
youtube_service.py
All interaction with pytubefix and ffmpeg lives here. The GUI never
touches pytubefix directly — it only calls the functions and classes
in this module. This separation makes the download logic independently
testable and keeps gui/main_window.py focused purely on presentation.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

import imageio_ffmpeg
from pytubefix import Playlist, YouTube
from pytubefix.contrib.search import Search

from utils import sanitize_filename, unique_path

PROGRESS_CALLBACK = Callable[..., None]  # pytubefix signature: (stream, chunk, bytes_remaining)


# --------------------------------------------------------------- Errors
class NoStreamAvailable(Exception):
    """Raised when YouTube offers no stream matching what was requested."""


class DownloadCancelled(Exception):
    """Raised (by the GUI's progress callback) to abort an in-progress
    download as soon as the user clicks Cancel."""


# ---------------------------------------------------------------- Models
@dataclass
class VideoInfo:
    title: str
    author: str
    length: int
    thumbnail_url: str
    resolutions: list[str] = field(default_factory=list)


@dataclass
class DownloadResult:
    path: str
    has_audio: bool
    size: int
    subtitle_path: Optional[str] = None


@dataclass
class SearchResultItem:
    title: str
    author: str
    length: int
    thumbnail_url: str
    watch_url: str


@dataclass
class CaptionOption:
    code: str
    name: str


# ------------------------------------------------------- Cancellation
class CancelToken:
    """A simple flag shared between the GUI thread (which can request
    cancellation) and the background download thread (which checks it)."""

    def __init__(self):
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def reset(self) -> None:
        self._cancelled = False

    def check(self) -> None:
        if self._cancelled:
            raise DownloadCancelled("Download cancelled by user.")

    @property
    def cancelled(self) -> bool:
        return self._cancelled


# ---------------------------------------------------- Progress reporting
class ProgressContext:
    """Mutable state shared between the download functions below (which
    know which phase of a multi-step download — video/audio/merge — is
    currently running) and the raw pytubefix progress callback defined
    in the GUI (which only sees byte-level progress of whatever stream
    is downloading right now). The GUI's callback reads these fields to
    compute one continuous overall percentage across all phases."""

    def __init__(self):
        self.phase_label = "Downloading"
        self.phase_start = 0.0
        self.phase_weight = 1.0
        self.total_size = 0
        self.phase_start_time = 0.0

    def begin_phase(self, label: str, start: float, weight: float, total_size: int) -> None:
        import time

        self.phase_label = label
        self.phase_start = start
        self.phase_weight = weight
        self.total_size = total_size
        self.phase_start_time = time.time()  # speed is computed per-phase, not across phases


# --------------------------------------------------------- YouTube session
class YouTubeSessionCache:
    """Caches a single pytubefix.YouTube object keyed by URL, so that
    fetching info and then downloading the same video doesn't re-request
    everything from YouTube. Automatically recreates the object if the
    URL changes."""

    def __init__(self, on_progress: PROGRESS_CALLBACK):
        self._on_progress = on_progress
        self._yt: Optional[YouTube] = None
        self._url = ""

    def get(self, url: str) -> YouTube:
        if self._yt is None or self._url != url:
            self._yt = YouTube(url, on_progress_callback=self._on_progress)
            self._url = url
        return self._yt

    def invalidate(self) -> None:
        """Forces the next call to `get()` to create a fresh YouTube
        object, even for the same URL. Useful after a failed download,
        in case the cached object's internal session/cipher has expired."""
        self._yt = None
        self._url = ""


# ------------------------------------------------------------- ffmpeg
#
# ffmpeg is never something the person needs to install manually: the
# `imageio-ffmpeg` package (a normal pip dependency, listed in
# requirements.txt) bundles a small, self-contained ffmpeg binary and
# downloads it automatically the first time it's needed. This is what
# makes high-quality (merged) downloads work out of the box.


def _get_ffmpeg_path() -> Optional[str]:
    """Returns the path to the bundled ffmpeg binary, or None if it
    could not be obtained for any reason (e.g. no internet access on
    first run, or an unsupported platform) — callers must handle None
    by falling back to a lower, always-available quality."""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_available() -> bool:
    """Returns True if the bundled ffmpeg binary is ready to use."""
    return _get_ffmpeg_path() is not None


def merge_audio_video(video_path: str, audio_path: str, output_path: str) -> None:
    """Merges a video-only file and an audio-only file into a single
    MP4 using the bundled ffmpeg binary. The video stream is copied
    as-is (no re-encoding, so this is fast); the audio is re-encoded to
    AAC for MP4 compatibility. Raises RuntimeError with the ffmpeg error
    output if the merge fails."""
    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path is None:
        raise RuntimeError("The bundled ffmpeg binary is not available.")

    command = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path,
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode != 0:
        error_tail = result.stderr.decode(errors="ignore")[-500:]
        raise RuntimeError(f"ffmpeg merge failed: {error_tail}")


# --------------------------------------------------------------- Fetching
def fetch_video_info(yt: YouTube) -> VideoInfo:
    """Retrieves title/author/length/thumbnail and the list of resolutions
    available for this video (across both progressive and adaptive
    streams, since adaptive-only resolutions are still downloadable,
    just via the merge path)."""
    video_streams = yt.streams.filter(type="video")
    resolutions = sorted(
        {s.resolution for s in video_streams if s.resolution},
        key=lambda r: int(r.rstrip("p")),
        reverse=True,
    )
    return VideoInfo(
        title=yt.title,
        author=yt.author,
        length=yt.length,
        thumbnail_url=yt.thumbnail_url,
        resolutions=resolutions,
    )


# ----------------------------------------------------- Stream selection
def select_progressive_stream(yt: YouTube, quality: str):
    """Looks for a single file already containing both video and audio.
    Increasingly rare above 360p on modern YouTube — returns None if
    none exists at the requested quality."""
    if quality == "Highest":
        return yt.streams.get_highest_resolution(progressive=True)
    if quality == "Lowest":
        return yt.streams.get_lowest_resolution(progressive=True)
    return yt.streams.filter(res=quality, progressive=True).first()


def select_adaptive_video_stream(yt: YouTube, quality: str):
    """Selects the best video-only (no audio) stream matching the
    requested quality, to be paired with a separate audio stream and
    merged via ffmpeg."""
    adaptive = yt.streams.filter(adaptive=True, only_video=True, subtype="mp4")
    if len(adaptive) == 0:
        adaptive = yt.streams.filter(adaptive=True, only_video=True)
    if len(adaptive) == 0:
        return None

    if quality == "Highest":
        return adaptive.order_by("resolution").desc().first()
    if quality == "Lowest":
        return adaptive.order_by("resolution").asc().first()

    match = adaptive.filter(res=quality).first()
    if match is not None:
        return match
    return adaptive.order_by("resolution").desc().first()


# -------------------------------------------------------------- Download
def _download_stream(stream, folder: str, filename: str, cancel_token: CancelToken) -> None:
    """Runs stream.download(), and cleans up the partial file if the
    download is interrupted (cancelled or any other error) instead of
    leaving a corrupt, half-written file behind."""
    cancel_token.check()
    try:
        stream.download(filename=filename, output_path=folder)
    except Exception:
        partial_path = os.path.join(folder, filename)
        if os.path.exists(partial_path):
            try:
                os.remove(partial_path)
            except OSError:
                pass
        raise


def download_audio(
    yt: YouTube,
    name: str,
    folder: str,
    progress_ctx: ProgressContext,
    cancel_token: CancelToken,
    convert_mp3: bool = False,
) -> DownloadResult:
    stream = yt.streams.get_audio_only()
    if stream is None:
        raise NoStreamAvailable("No audio stream found for this video.")

    progress_ctx.begin_phase("Audio", 0.0, 0.85 if convert_mp3 else 1.0, stream.filesize)
    final_name = unique_path(folder, name, "m4a")
    _download_stream(stream, folder, final_name, cancel_token)
    m4a_path = os.path.join(folder, final_name)

    if not convert_mp3:
        return DownloadResult(path=m4a_path, has_audio=True, size=stream.filesize)

    cancel_token.check()
    progress_ctx.begin_phase("Converting to MP3", 0.85, 0.15, 1)
    mp3_name = unique_path(folder, name, "mp3")
    mp3_path = os.path.join(folder, mp3_name)
    try:
        convert_to_mp3(m4a_path, mp3_path)
    finally:
        # Keep only the final MP3; the intermediate .m4a served no
        # further purpose once conversion succeeds (or failed, in which
        # case there's nothing useful left behind either way).
        if os.path.exists(m4a_path):
            try:
                os.remove(m4a_path)
            except OSError:
                pass

    size = os.path.getsize(mp3_path) if os.path.exists(mp3_path) else 0
    return DownloadResult(path=mp3_path, has_audio=True, size=size)


def download_video(
    yt: YouTube,
    quality: str,
    name: str,
    folder: str,
    progress_ctx: ProgressContext,
    cancel_token: CancelToken,
    subtitles: bool = False,
) -> DownloadResult:
    result = _download_video_core(yt, quality, name, folder, progress_ctx, cancel_token)

    if subtitles:
        cancel_token.check()
        progress_ctx.begin_phase("Downloading subtitles", 0.98, 0.02, 1)
        try:
            result.subtitle_path = download_captions(yt, name, folder)
        except Exception:
            # Missing/failed subtitles should never fail the whole
            # download — the video itself already succeeded.
            result.subtitle_path = None

    return result


def _download_video_core(
    yt: YouTube,
    quality: str,
    name: str,
    folder: str,
    progress_ctx: ProgressContext,
    cancel_token: CancelToken,
) -> DownloadResult:
    """
    Downloads a video, preferring (in order):
      1. A single progressive file (video+audio combined) at the
         requested quality — fast, no merge needed.
      2. A video-only adaptive stream at the requested quality, merged
         with a separate audio stream via ffmpeg — used whenever (1)
         isn't available, which is the common case above 360p.
      3. If ffmpeg isn't installed, falls back to the best progressive
         stream available (usually 360p) so the result at least has
         sound, rather than silently producing a silent video.
      4. As an absolute last resort (no progressive stream exists at
         all, and no audio track can be found), downloads the video
         without audio and reports `has_audio=False` so the caller can
         warn the user explicitly.
    """
    progressive = select_progressive_stream(yt, quality)
    if progressive is not None:
        progress_ctx.begin_phase("Video", 0.0, 1.0, progressive.filesize)
        final_name = unique_path(folder, name, progressive.subtype or "mp4")
        _download_stream(progressive, folder, final_name, cancel_token)
        return DownloadResult(path=os.path.join(folder, final_name), has_audio=True, size=progressive.filesize)

    video_stream = select_adaptive_video_stream(yt, quality)
    if video_stream is None:
        raise NoStreamAvailable("No downloadable video stream found for this video.")

    if not ffmpeg_available():
        fallback = yt.streams.get_highest_resolution(progressive=True)
        if fallback is not None:
            progress_ctx.begin_phase("Video", 0.0, 1.0, fallback.filesize)
            final_name = unique_path(folder, name, fallback.subtype or "mp4")
            _download_stream(fallback, folder, final_name, cancel_token)
            return DownloadResult(path=os.path.join(folder, final_name), has_audio=True, size=fallback.filesize)
        return _download_silent_video(video_stream, name, folder, progress_ctx, cancel_token)

    audio_stream = yt.streams.get_audio_only()
    if audio_stream is None:
        return _download_silent_video(video_stream, name, folder, progress_ctx, cancel_token)

    return _download_and_merge(video_stream, audio_stream, name, folder, progress_ctx, cancel_token)


def _download_silent_video(video_stream, name, folder, progress_ctx, cancel_token) -> DownloadResult:
    progress_ctx.begin_phase("Video (no audio available)", 0.0, 1.0, video_stream.filesize)
    final_name = unique_path(folder, name, video_stream.subtype or "mp4")
    _download_stream(video_stream, folder, final_name, cancel_token)
    return DownloadResult(path=os.path.join(folder, final_name), has_audio=False, size=video_stream.filesize)


def _download_and_merge(
    video_stream, audio_stream, name, folder, progress_ctx: ProgressContext, cancel_token: CancelToken
) -> DownloadResult:
    temp_video = os.path.join(folder, f".{name}_video.tmp.mp4")
    temp_audio = os.path.join(folder, f".{name}_audio.tmp.m4a")

    try:
        progress_ctx.begin_phase("Video", 0.0, 0.45, video_stream.filesize)
        _download_stream(video_stream, folder, os.path.basename(temp_video), cancel_token)

        progress_ctx.begin_phase("Audio", 0.45, 0.45, audio_stream.filesize)
        _download_stream(audio_stream, folder, os.path.basename(temp_audio), cancel_token)

        cancel_token.check()
        progress_ctx.begin_phase("Merging video and audio", 0.9, 0.1, 1)

        final_name = unique_path(folder, name, "mp4")
        final_path = os.path.join(folder, final_name)
        merge_audio_video(temp_video, temp_audio, final_path)
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        return DownloadResult(path=final_path, has_audio=True, size=size)
    finally:
        for path in (temp_video, temp_audio):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


# ---------------------------------------------------------------- Search
def search_videos(query: str, limit: int = 15) -> list[SearchResultItem]:
    """Searches YouTube directly (no link needed) and returns up to
    `limit` video results with the metadata needed to display them."""
    search = Search(query)
    results = []
    for yt in search.videos[:limit]:
        try:
            results.append(SearchResultItem(
                title=yt.title,
                author=yt.author,
                length=yt.length or 0,
                thumbnail_url=yt.thumbnail_url,
                watch_url=yt.watch_url,
            ))
        except Exception:
            continue  # skip any single malformed result rather than failing the whole search
    return results


# -------------------------------------------------------------- Playlist
def get_playlist_video_urls(url: str, limit: int = 100) -> tuple[str, list[str]]:
    """Returns (playlist_title, [video_url, ...]) for a playlist URL.
    Uses `video_urls` (lightweight, just the URLs) rather than `videos`
    (which would eagerly build a full YouTube object per video and be
    far slower for large playlists); each video's real title is loaded
    later, individually, once its own download job actually starts."""
    playlist = Playlist(url)
    title = playlist.title or "Playlist"
    urls = list(playlist.video_urls)[:limit]
    return title, urls


# -------------------------------------------------------------- Captions
def list_captions(yt: YouTube) -> list[CaptionOption]:
    """Lists the subtitle/caption tracks available for this video."""
    try:
        return [CaptionOption(code=c.code, name=c.name) for c in yt.captions]
    except Exception:
        return []


def download_captions(yt: YouTube, name: str, folder: str) -> Optional[str]:
    """Downloads the best available caption track as an .srt file.
    Prefers English (manually-created 'en', then auto-generated 'a.en'),
    otherwise falls back to whatever track is listed first. Returns the
    saved file path, or None if the video has no captions at all."""
    options = list_captions(yt)
    if not options:
        return None

    preferred_order = ["en", "a.en"]
    chosen_code = next((c for c in preferred_order if any(o.code == c for o in options)), options[0].code)
    caption = yt.captions[chosen_code]

    safe_name = sanitize_filename(name)
    caption.download(title=safe_name, srt=True, output_path=folder)
    # pytubefix appends " (<code>).srt" to whatever title we pass — locate
    # the exact file it just wrote so we can report its real path back.
    expected_suffix = f" ({chosen_code}).srt"
    for fname in os.listdir(folder):
        if fname.startswith(safe_name) and fname.endswith(expected_suffix):
            return os.path.join(folder, fname)
    return None


# --------------------------------------------------------- MP3 conversion
def convert_to_mp3(input_path: str, output_path: str) -> None:
    """Converts an audio file (e.g. the .m4a produced by download_audio)
    to MP3 (192 kbps) using the bundled ffmpeg binary."""
    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path is None:
        raise RuntimeError("The bundled ffmpeg binary is not available.")

    command = [
        ffmpeg_path, "-y",
        "-i", input_path,
        "-vn",
        "-codec:a", "libmp3lame",
        "-b:a", "192k",
        output_path,
    ]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode != 0:
        error_tail = result.stderr.decode(errors="ignore")[-500:]
        raise RuntimeError(f"ffmpeg MP3 conversion failed: {error_tail}")
