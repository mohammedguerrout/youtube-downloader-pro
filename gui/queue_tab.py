"""
gui/queue_tab.py
The "Queue" tab: a live view of every download job (pending, running,
done, failed, or cancelled), refreshed periodically by MainApp. Each
row offers a Cancel button while the job is still pending or running.
"""

import customtkinter as ctk

from config import COLOR_ERROR, COLOR_OK, COLOR_WORK
from queue_manager import JobStatus

STATUS_COLORS = {
    JobStatus.PENDING: "gray",
    JobStatus.DOWNLOADING: COLOR_WORK,
    JobStatus.DONE: COLOR_OK,
    JobStatus.ERROR: COLOR_ERROR,
    JobStatus.CANCELLED: "gray",
}


class QueueTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._last_signature = None  # avoids needless redraws when nothing changed

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="📥 Download Queue", font=("bold", 22)).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="🧹 Clear finished", width=140, command=self.clear_finished).grid(
            row=0, column=1, sticky="e"
        )

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self._placeholder = ctk.CTkLabel(
            self.list_frame, text="No downloads yet. Add one from the Download, Search or Playlist tab.",
            text_color="gray",
        )
        self._placeholder.pack(pady=30)

    # ------------------------------------------------------------------
    def clear_finished(self):
        self.app.queue_manager.clear_finished()
        self._last_signature = None  # force a redraw
        self.refresh()

    def refresh(self):
        jobs = self.app.queue_manager.jobs()

        # Cheap change-detection so we don't rebuild the whole list 2x/second
        # for nothing when nothing has actually changed.
        signature = tuple((j.id, j.status, j.progress, j.title) for j in jobs)
        if signature == self._last_signature:
            return
        self._last_signature = signature

        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not jobs:
            ctk.CTkLabel(
                self.list_frame, text="No downloads yet. Add one from the Download, Search or Playlist tab.",
                text_color="gray",
            ).pack(pady=30)
            return

        for job in reversed(jobs):  # newest first
            self._build_row(job)

    def _build_row(self, job):
        row = ctk.CTkFrame(self.list_frame, corner_radius=12)
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure(0, weight=1)

        title = job.title or job.url
        kind = {"video": "🎬", "audio": "🎵"}.get(job.mode, "📄")
        ctk.CTkLabel(
            row, text=f"{kind} {title}", font=("bold", 13), anchor="w", wraplength=480,
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 2), sticky="ew")

        status_color = STATUS_COLORS.get(job.status, "gray")
        ctk.CTkLabel(
            row, text=f"{job.status.value} — {job.status_text}", font=("arial", 11), text_color=status_color,
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, padx=12, sticky="ew")

        bar = ctk.CTkProgressBar(row, corner_radius=50)
        bar.set(job.progress / 100)
        bar.grid(row=2, column=0, padx=(12, 8), pady=(6, 10), sticky="ew")

        cancel_btn = ctk.CTkButton(
            row, text="✖", width=32, height=28, fg_color=COLOR_ERROR, hover_color="#a93034",
            command=lambda j=job: self.app.queue_manager.cancel_job(j.id),
        )
        cancel_btn.grid(row=2, column=1, padx=(0, 12), pady=(6, 10))
        if job.status not in (JobStatus.PENDING, JobStatus.DOWNLOADING):
            cancel_btn.configure(state="disabled")
