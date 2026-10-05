"""
gui/search_tab.py
The "Search" tab: search YouTube by keywords (no link needed), browse
results with thumbnails, and add any of them straight to the queue.
"""

import threading
import urllib.request
from io import BytesIO

import customtkinter as ctk
from PIL import Image

from config import COLOR_ERROR, COLOR_OK, COLOR_WORK, DEFAULT_ERROR_MESSAGE, ERROR_MESSAGES
from queue_manager import DownloadJob
from utils import format_duration
from youtube_service import search_videos


class SearchTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.searching = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)

        self.query_entry = ctk.CTkEntry(
            search_row, height=40, font=("bold", 13), corner_radius=10,
            placeholder_text="Search YouTube — e.g. 'lofi hip hop radio'",
        )
        self.query_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.query_entry.bind("<Return>", lambda e: self.run_search())

        self.search_btn = ctk.CTkButton(search_row, text="🔍 Search", width=100, height=40, command=self.run_search)
        self.search_btn.grid(row=0, column=1)

        self.results_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.results_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)

        self._placeholder = ctk.CTkLabel(
            self.results_frame, text="Search results will appear here.", text_color="gray"
        )
        self._placeholder.pack(pady=30)

    # ------------------------------------------------------------------
    def run_search(self):
        if self.searching:
            return
        query = self.query_entry.get().strip()
        if not query:
            self.app.set_status("Type something to search for", COLOR_ERROR)
            return

        self.searching = True
        self.app.set_status("Searching...", COLOR_WORK)
        self.search_btn.configure(state="disabled")
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        threading.Thread(target=self._process_search, args=(query,), daemon=True).start()

    def _process_search(self, query: str):
        try:
            results = search_videos(query, limit=15)
            self.app.ui(self._show_results, results)
        except Exception as e:
            from config import logger
            logger.exception("Search failed: %s", e)
            message = ERROR_MESSAGES.get(type(e).__name__, DEFAULT_ERROR_MESSAGE)
            self.app.ui(self.app.set_status, message, COLOR_ERROR)
        finally:
            self.searching = False
            self.app.ui(self.search_btn.configure, state="normal")

    def _show_results(self, results):
        if not results:
            ctk.CTkLabel(self.results_frame, text="No results found.", text_color="gray").pack(pady=30)
            self.app.set_status("No results found.", COLOR_WORK)
            return

        for item in results:
            self._build_result_row(item)
        self.app.set_status(f"Found {len(results)} results.", COLOR_OK)

    def _build_result_row(self, item):
        row = ctk.CTkFrame(self.results_frame, corner_radius=12)
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure(1, weight=1)

        thumb = ctk.CTkLabel(row, text="🎬", font=("Arial", 24), width=120, height=68, fg_color="gray30", corner_radius=8)
        thumb.grid(row=0, column=0, padx=10, pady=10)

        info = ctk.CTkLabel(
            row,
            text=f"{item.title}\n👤 {item.author}  ⏱️ {format_duration(item.length)}",
            font=("bold", 13), justify="left", anchor="w", wraplength=420,
        )
        info.grid(row=0, column=1, sticky="ew", padx=5)

        ctk.CTkButton(
            row, text="➕ Add", width=90, command=lambda i=item: self._add_result(i)
        ).grid(row=0, column=2, padx=10)

        threading.Thread(target=self._load_thumbnail, args=(item.thumbnail_url, thumb), daemon=True).start()

    def _load_thumbnail(self, url, label):
        try:
            raw_data = urllib.request.urlopen(url).read()
            image = Image.open(BytesIO(raw_data))
            self.app.ui(self._apply_thumbnail, label, image)
        except Exception:
            pass  # a missing thumbnail is cosmetic only

    def _apply_thumbnail(self, label, image):
        ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(120, 68))
        label.configure(image=ctk_img, text="")

    def _add_result(self, item):
        folder = self.app.folder_entry.get().strip()
        if not folder:
            self.app.set_status("Please choose a destination folder in Settings", COLOR_ERROR)
            return

        job = DownloadJob(
            url=item.watch_url,
            mode=self.app.mode_var.get(),
            quality=self.app.quality_menu.get(),
            folder=folder,
            mp3=bool(self.app.mp3_switch.get()),
            subtitles=bool(self.app.subtitles_switch.get()),
        )
        self.app.queue_manager.add_job(job)
        self.app.set_status(f"Added '{item.title}' to queue.", COLOR_OK)
        self.app.go_to_queue_tab()
