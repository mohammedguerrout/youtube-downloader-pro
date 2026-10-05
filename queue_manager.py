"""
queue_manager.py
A sequential, background download queue. Every download in the app —
whether added from the Download tab, a Search result, or a Playlist —
becomes a DownloadJob appended here. A single worker thread processes
jobs one at a time (simple and predictable; avoids multiple downloads
fighting over bandwidth and disk I/O). The GUI only ever *reads*
`DownloadQueue.jobs` (a thread-safe snapshot) to redraw the Queue tab;
it never touches pytubefix directly.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pytubefix import YouTube

import history
from utils import sanitize_filename
from youtube_service import (
    CancelToken,
    DownloadCancelled,
    NoStreamAvailable,
    ProgressContext,
    download_audio,
    download_video,
)


class JobStatus(Enum):
    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    DONE = "Done"
    ERROR = "Error"
    CANCELLED = "Cancelled"


@dataclass
class DownloadJob:
    url: str
    mode: str                      # "video" | "audio"
    quality: str
    folder: str
    mp3: bool = False
    subtitles: bool = False
    name_hint: str = ""            # optional user-chosen filename (Download tab only)

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""                # filled in once the job starts (real video title)
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    status_text: str = "Waiting in queue..."
    result_path: Optional[str] = None
    error: Optional[str] = None

    cancel_token: CancelToken = field(default_factory=CancelToken)
    progress_ctx: ProgressContext = field(default_factory=ProgressContext)


class DownloadQueue:
    def __init__(self):
        self._jobs: list[DownloadJob] = []
        self._lock = threading.Lock()
        self._pending_ids: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Public, thread-safe API used by the GUI
    # ------------------------------------------------------------------

    def add_job(self, job: DownloadJob) -> None:
        with self._lock:
            self._jobs.append(job)
        self._pending_ids.put(job.id)

    def jobs(self) -> list[DownloadJob]:
        """Returns a shallow snapshot of the current job list, safe to
        iterate from the GUI thread while the worker keeps running."""
        with self._lock:
            return list(self._jobs)

    def cancel_job(self, job_id: str) -> None:
        with self._lock:
            job = next((j for j in self._jobs if j.id == job_id), None)
        if job is None:
            return
        if job.status == JobStatus.PENDING:
            job.status = JobStatus.CANCELLED
            job.status_text = "Cancelled before it started."
        elif job.status == JobStatus.DOWNLOADING:
            job.cancel_token.cancel()

    def clear_finished(self) -> None:
        with self._lock:
            self._jobs = [
                j for j in self._jobs
                if j.status not in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)
            ]

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        while True:
            job_id = self._pending_ids.get()
            with self._lock:
                job = next((j for j in self._jobs if j.id == job_id), None)
            if job is None or job.status == JobStatus.CANCELLED:
                continue
            self._run_job(job)

    def _run_job(self, job: DownloadJob) -> None:
        job.status = JobStatus.DOWNLOADING
        job.status_text = "Connecting..."
        start_time = time.time()

        def on_progress(stream, chunk, bytes_remaining):
            if job.cancel_token.cancelled:
                raise DownloadCancelled("Download cancelled by user.")
            total = job.progress_ctx.total_size
            if total == 0:
                return
            downloaded = total - bytes_remaining
            fraction = downloaded / total
            job.progress = max(0, min(
                100,
                int((job.progress_ctx.phase_start + fraction * job.progress_ctx.phase_weight) * 100),
            ))
            job.status_text = f"{job.progress_ctx.phase_label} — {job.progress}%"

        try:
            yt = YouTube(job.url, on_progress_callback=on_progress)
            job.title = yt.title
            name = sanitize_filename(job.name_hint) if job.name_hint else sanitize_filename(yt.title)

            if job.mode == "audio":
                result = download_audio(
                    yt, name, job.folder, job.progress_ctx, job.cancel_token, convert_mp3=job.mp3
                )
            else:
                result = download_video(
                    yt, job.quality, name, job.folder, job.progress_ctx, job.cancel_token,
                    subtitles=job.subtitles,
                )

            job.result_path = result.path
            job.status = JobStatus.DONE
            job.progress = 100
            if result.has_audio:
                job.status_text = "Done."
            else:
                job.status_text = "Done, but no audio was available for this quality."

            history.add_entry(
                title=job.title,
                path=result.path,
                kind=("mp3" if job.mp3 else "audio") if job.mode == "audio" else "video",
                size=os.path.getsize(result.path) if os.path.exists(result.path) else 0,
            )
            if result.subtitle_path:
                history.add_entry(
                    title=f"{job.title} (subtitles)",
                    path=result.subtitle_path,
                    kind="subtitles",
                    size=os.path.getsize(result.subtitle_path) if os.path.exists(result.subtitle_path) else 0,
                )

        except DownloadCancelled:
            job.status = JobStatus.CANCELLED
            job.status_text = "Cancelled."
        except NoStreamAvailable as e:
            job.status = JobStatus.ERROR
            job.error = str(e)
            job.status_text = str(e)
        except Exception as e:
            job.status = JobStatus.ERROR
            job.error = str(e)
            job.status_text = "An unexpected error occurred — see the log file for details."
            from config import logger
            logger.exception("Queue job failed (%s): %s", job.url, e)
