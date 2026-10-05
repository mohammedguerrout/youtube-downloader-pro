"""
tests/test_queue_manager.py
Exercises the real DownloadQueue (its actual background worker thread,
not a reimplementation of its logic) against monkeypatched versions of
YouTube/download_video/download_audio/history.add_entry, so no network
access is needed.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import queue_manager as qm
from youtube_service import DownloadCancelled, DownloadResult


class FakeYouTube:
    def __init__(self, url, on_progress_callback=None):
        self.url = url
        self.title = f"Title for {url}"
        self.on_progress_callback = on_progress_callback


def _wait_for_status(job, status, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status == status:
            return True
        time.sleep(0.01)
    return False


def _wait_while(job, status, timeout=2.0):
    """Waits until the job's status is no longer `status`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.status != status:
            return True
        time.sleep(0.01)
    return False


def test_successful_video_job_reaches_done(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "YouTube", FakeYouTube)

    recorded_history = []
    monkeypatch.setattr(qm.history, "add_entry", lambda **kw: recorded_history.append(kw))

    def fake_download_video(yt, quality, name, folder, progress_ctx, cancel_token, subtitles=False):
        out = os.path.join(folder, f"{name}.mp4")
        with open(out, "wb") as f:
            f.write(b"fake video bytes")
        return DownloadResult(path=out, has_audio=True, size=17)

    monkeypatch.setattr(qm, "download_video", fake_download_video)

    queue_obj = qm.DownloadQueue()
    job = qm.DownloadJob(url="https://youtu.be/fake1", mode="video", quality="Highest", folder=str(tmp_path))
    queue_obj.add_job(job)

    assert _wait_for_status(job, qm.JobStatus.DONE), f"Job did not finish in time, status={job.status}"
    assert job.progress == 100
    assert job.result_path is not None
    assert os.path.exists(job.result_path)
    assert job.title == "Title for https://youtu.be/fake1"
    assert len(recorded_history) == 1
    assert recorded_history[0]["kind"] == "video"


def test_audio_job_with_mp3_records_mp3_kind(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "YouTube", FakeYouTube)
    recorded_history = []
    monkeypatch.setattr(qm.history, "add_entry", lambda **kw: recorded_history.append(kw))

    def fake_download_audio(yt, name, folder, progress_ctx, cancel_token, convert_mp3=False):
        ext = "mp3" if convert_mp3 else "m4a"
        out = os.path.join(folder, f"{name}.{ext}")
        with open(out, "wb") as f:
            f.write(b"fake audio")
        return DownloadResult(path=out, has_audio=True, size=10)

    monkeypatch.setattr(qm, "download_audio", fake_download_audio)

    queue_obj = qm.DownloadQueue()
    job = qm.DownloadJob(url="https://youtu.be/fake2", mode="audio", quality="Highest",
                          folder=str(tmp_path), mp3=True)
    queue_obj.add_job(job)

    assert _wait_for_status(job, qm.JobStatus.DONE)
    assert recorded_history[0]["kind"] == "mp3"
    assert job.result_path.endswith(".mp3")


def test_cancelling_a_running_job_marks_it_cancelled(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "YouTube", FakeYouTube)
    monkeypatch.setattr(qm.history, "add_entry", lambda **kw: None)

    def fake_download_video(yt, quality, name, folder, progress_ctx, cancel_token, subtitles=False):
        # Simulate a slow download that checks for cancellation periodically,
        # exactly like the real _download_stream helper does via on_progress.
        for _ in range(200):
            cancel_token.check()
            time.sleep(0.01)
        raise AssertionError("fake_download_video should have been cancelled before finishing")

    monkeypatch.setattr(qm, "download_video", fake_download_video)

    queue_obj = qm.DownloadQueue()
    job = qm.DownloadJob(url="https://youtu.be/fake3", mode="video", quality="Highest", folder=str(tmp_path))
    queue_obj.add_job(job)

    assert _wait_for_status(job, qm.JobStatus.DOWNLOADING)
    queue_obj.cancel_job(job.id)

    assert _wait_for_status(job, qm.JobStatus.CANCELLED)


def test_cancelling_a_pending_job_skips_it(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "YouTube", FakeYouTube)
    monkeypatch.setattr(qm.history, "add_entry", lambda **kw: None)

    # Block the worker with one slow job first, so the second job stays PENDING.
    def slow_download(yt, quality, name, folder, progress_ctx, cancel_token, subtitles=False):
        for _ in range(100):
            cancel_token.check()
            time.sleep(0.01)
        return DownloadResult(path=os.path.join(folder, "blocker.mp4"), has_audio=True, size=1)

    monkeypatch.setattr(qm, "download_video", slow_download)

    queue_obj = qm.DownloadQueue()
    blocker = qm.DownloadJob(url="https://youtu.be/blocker", mode="video", quality="Highest", folder=str(tmp_path))
    queued = qm.DownloadJob(url="https://youtu.be/queued", mode="video", quality="Highest", folder=str(tmp_path))
    queue_obj.add_job(blocker)
    queue_obj.add_job(queued)

    assert _wait_for_status(blocker, qm.JobStatus.DOWNLOADING)
    assert queued.status == qm.JobStatus.PENDING

    queue_obj.cancel_job(queued.id)
    assert queued.status == qm.JobStatus.CANCELLED

    blocker.cancel_token.cancel()  # let the blocker finish quickly so the test exits fast
    assert _wait_for_status(blocker, qm.JobStatus.CANCELLED)


def test_error_in_one_job_does_not_stop_the_queue(monkeypatch, tmp_path):
    monkeypatch.setattr(qm, "YouTube", FakeYouTube)
    monkeypatch.setattr(qm.history, "add_entry", lambda **kw: None)

    call_count = {"n": 0}

    def flaky_download(yt, quality, name, folder, progress_ctx, cancel_token, subtitles=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated network failure")
        out = os.path.join(folder, f"{name}.mp4")
        with open(out, "wb") as f:
            f.write(b"ok")
        return DownloadResult(path=out, has_audio=True, size=2)

    monkeypatch.setattr(qm, "download_video", flaky_download)

    queue_obj = qm.DownloadQueue()
    failing_job = qm.DownloadJob(url="https://youtu.be/fail", mode="video", quality="Highest", folder=str(tmp_path))
    next_job = qm.DownloadJob(url="https://youtu.be/ok", mode="video", quality="Highest", folder=str(tmp_path))
    queue_obj.add_job(failing_job)
    queue_obj.add_job(next_job)

    assert _wait_for_status(failing_job, qm.JobStatus.ERROR)
    assert failing_job.error is not None

    assert _wait_for_status(next_job, qm.JobStatus.DONE), "the queue must keep processing after a job fails"
