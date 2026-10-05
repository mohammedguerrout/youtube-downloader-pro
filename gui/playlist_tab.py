"""
gui/playlist_tab.py
The "Playlist" tab: paste a playlist URL, pick which videos to
download (all selected by default), and add them all to the queue at
once. Individual video titles are not pre-fetched (that would be slow
for large playlists) — each one fills in on the Queue tab once its own
download actually starts.
"""

import threading

import customtkinter as ctk

from config import COLOR_ERROR, COLOR_OK, COLOR_WORK, DEFAULT_ERROR_MESSAGE, ERROR_MESSAGES
from queue_manager import DownloadJob
from youtube_service import get_playlist_video_urls


class PlaylistTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.loading = False
        self.video_urls = []
        self.checkboxes = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        url_row = ctk.CTkFrame(self, fg_color="transparent")
        url_row.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        url_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            url_row, height=40, font=("bold", 13), corner_radius=10,
            placeholder_text="Paste a YouTube playlist URL...",
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.load_playlist())

        self.load_btn = ctk.CTkButton(url_row, text="📃 Load", width=90, height=40, command=self.load_playlist)
        self.load_btn.grid(row=0, column=1)

        self.title_label = ctk.CTkLabel(self, text="", font=("bold", 15))
        self.title_label.grid(row=1, column=0, padx=20, sticky="w")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        self.select_all_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bottom, text="Select / deselect all", variable=self.select_all_var, command=self._toggle_all
        ).grid(row=0, column=0, sticky="w")

        self.add_btn = ctk.CTkButton(
            bottom, text="➕ Add Selected to Queue", height=42, fg_color=COLOR_OK, hover_color="#207a4c",
            command=self.add_selected, state="disabled",
        )
        self.add_btn.grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------
    def load_playlist(self):
        if self.loading:
            return
        url = self.url_entry.get().strip()
        if not url:
            self.app.set_status("Please enter a playlist URL", COLOR_ERROR)
            return

        self.loading = True
        self.app.set_status("Loading playlist...", COLOR_WORK)
        self.load_btn.configure(state="disabled")
        self.add_btn.configure(state="disabled")
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.checkboxes = []
        threading.Thread(target=self._process_load, args=(url,), daemon=True).start()

    def _process_load(self, url: str):
        try:
            title, urls = get_playlist_video_urls(url, limit=100)
            self.app.ui(self._show_playlist, title, urls)
        except Exception as e:
            from config import logger
            logger.exception("Playlist load failed: %s", e)
            message = ERROR_MESSAGES.get(type(e).__name__, DEFAULT_ERROR_MESSAGE)
            self.app.ui(self.app.set_status, message, COLOR_ERROR)
        finally:
            self.loading = False
            self.app.ui(self.load_btn.configure, state="normal")

    def _show_playlist(self, title, urls):
        self.video_urls = urls
        note = " (showing first 100)" if len(urls) == 100 else ""
        self.title_label.configure(text=f"📃 {title} — {len(urls)} videos{note}")

        for i, video_url in enumerate(urls, start=1):
            var = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(self.list_frame, text=f"Video {i}", variable=var)
            cb.pack(anchor="w", pady=2, padx=5)
            self.checkboxes.append((var, video_url))

        self.add_btn.configure(state="normal" if urls else "disabled")
        self.app.set_status(f"Loaded {len(urls)} videos — select which to download.", COLOR_OK)

    def _toggle_all(self):
        value = self.select_all_var.get()
        for var, _ in self.checkboxes:
            var.set(value)

    # ------------------------------------------------------------------
    def add_selected(self):
        folder = self.app.folder_entry.get().strip()
        if not folder:
            self.app.set_status("Please choose a destination folder in Settings", COLOR_ERROR)
            return

        selected_urls = [url for var, url in self.checkboxes if var.get()]
        if not selected_urls:
            self.app.set_status("No videos selected", COLOR_ERROR)
            return

        for url in selected_urls:
            job = DownloadJob(
                url=url,
                mode=self.app.mode_var.get(),
                quality=self.app.quality_menu.get(),
                folder=folder,
                mp3=bool(self.app.mp3_switch.get()),
                subtitles=bool(self.app.subtitles_switch.get()),
            )
            self.app.queue_manager.add_job(job)

        self.app.set_status(f"Added {len(selected_urls)} videos to queue.", COLOR_OK)
        self.app.go_to_queue_tab()
