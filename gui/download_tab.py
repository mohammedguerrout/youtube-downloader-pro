"""
gui/download_tab.py
The "Download" tab: paste a single YouTube URL, preview its info, then
add it to the shared download queue using the settings configured in
the sidebar.
"""

import threading
import urllib.request
from io import BytesIO
from tkinter import END

import customtkinter as ctk
from PIL import Image

from config import COLOR_ERROR, COLOR_OK, COLOR_WORK, DEFAULT_ERROR_MESSAGE, ERROR_MESSAGES
from queue_manager import DownloadJob
from utils import format_duration, sanitize_filename
from youtube_service import fetch_video_info


class DownloadTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.fetching = False

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="📥 Download a video", font=("bold", 22)).grid(
            row=0, column=0, padx=20, pady=(15, 10), sticky="w"
        )

        url_frame = ctk.CTkFrame(self, fg_color="transparent")
        url_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            url_frame, height=40, font=("bold", 13), corner_radius=10,
            placeholder_text="Paste YouTube URL here...",
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.fetch_info())
        # ملاحظة: لم نعد نربط Ctrl+V هنا بشكل منفصل — أصبح هذا معالَجاً
        # بشكل عام لكل خانات الكتابة في التطبيق من main_window.py
        # (انظر MainApp._global_paste_handler)، لأنه يعمل بشكل موثوق مع
        # كل تخطيطات لوحة المفاتيح (عربية، فرنسية AZERTY، إلخ)، بخلاف
        # الربط بالرمز 'v' وحده الذي يفشل على بعض اللغات.

        ctk.CTkButton(
            url_frame, text="📋", width=40, height=40, fg_color="gray40", hover_color="gray30",
            command=self.paste_from_clipboard,
        ).grid(row=0, column=1, padx=(0, 10))

        self.fetch_btn = ctk.CTkButton(url_frame, text="🔍 Fetch", width=80, height=40, command=self.fetch_info)
        self.fetch_btn.grid(row=0, column=2)

        self.info_frame = ctk.CTkFrame(self, height=100, corner_radius=10, fg_color="transparent")
        self.info_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.info_frame.grid_columnconfigure(1, weight=1)

        self.thumbnail_label = ctk.CTkLabel(
            self.info_frame, text="🎬", font=("Arial", 32), width=160, height=90,
            fg_color="gray30", corner_radius=8,
        )
        self.thumbnail_label.grid(row=0, column=0, padx=(0, 10))

        self.info_label = ctk.CTkLabel(
            self.info_frame, text="Enter a URL and click Fetch", font=("bold", 14),
            wraplength=420, justify="left", anchor="nw",
        )
        self.info_label.grid(row=0, column=1, sticky="nsew")

        self.name_entry = ctk.CTkEntry(
            self, height=36, corner_radius=10,
            placeholder_text="File name (leave empty to use video title)",
        )
        self.name_entry.grid(row=3, column=0, padx=20, pady=8, sticky="ew")

        self.add_btn = ctk.CTkButton(
            self, height=45, text="➕ Add to Queue", font=("bold", 16), corner_radius=10,
            command=self.add_to_queue, fg_color=COLOR_OK, hover_color="#207a4c",
        )
        self.add_btn.grid(row=4, column=0, padx=20, pady=(15, 20), sticky="ew")

        self._last_url = None

    # ------------------------------------------------------------------
    def paste_from_clipboard(self):
        try:
            clipboard_content = self.clipboard_get()
        except Exception:
            return
        if "youtube.com" in clipboard_content or "youtu.be" in clipboard_content:
            self.url_entry.delete(0, END)
            self.url_entry.insert(0, clipboard_content)
            self.fetch_info()

    def fetch_info(self):
        if self.fetching:
            return
        url = self.url_entry.get().strip()
        if not url:
            self.app.set_status("Please enter a URL", COLOR_ERROR)
            return

        self.fetching = True
        self.app.set_status("Fetching info...", COLOR_WORK)
        self.fetch_btn.configure(state="disabled")
        threading.Thread(target=self._process_fetch, args=(url,), daemon=True).start()

    def _process_fetch(self, url: str):
        try:
            yt = self.app.session.get(url)
            info = fetch_video_info(yt)
            try:
                raw_data = urllib.request.urlopen(info.thumbnail_url).read()
                image = Image.open(BytesIO(raw_data))
            except Exception:
                image = None
            self.app.ui(self._show_info, url, info, image)
        except Exception as e:
            self.app.session.invalidate()
            self.app.ui(self._show_error, e)
        finally:
            self.fetching = False
            self.app.ui(self.fetch_btn.configure, state="normal")

    def _show_info(self, url, info, image):
        self._last_url = url
        self.info_label.configure(text=f"{info.title}\n\n👤 {info.author}\n⏱️ {format_duration(info.length)}")

        if image:
            ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=(160, 90))
            self.thumbnail_label.configure(image=ctk_img, text="")
        else:
            self.thumbnail_label.configure(image=None, text="🎬")

        self.name_entry.delete(0, END)
        self.name_entry.insert(0, sanitize_filename(info.title))
        self.app.set_status("Ready — click Add to Queue", COLOR_OK)

    def _show_error(self, exc: Exception):
        from config import logger
        logger.exception("Fetch failed: %s", exc)
        message = ERROR_MESSAGES.get(type(exc).__name__, DEFAULT_ERROR_MESSAGE)
        self.app.set_status(message, COLOR_ERROR)

    # ------------------------------------------------------------------
    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if not url:
            self.app.set_status("Please enter a URL first", COLOR_ERROR)
            return

        folder = self.app.folder_entry.get().strip()
        if not folder:
            self.app.set_status("Please choose a destination folder", COLOR_ERROR)
            return

        job = DownloadJob(
            url=url,
            mode=self.app.mode_var.get(),
            quality=self.app.quality_menu.get(),
            folder=folder,
            mp3=bool(self.app.mp3_switch.get()),
            subtitles=bool(self.app.subtitles_switch.get()),
            name_hint=self.name_entry.get().strip(),
        )
        self.app.queue_manager.add_job(job)
        self.app.set_status("Added to queue.", COLOR_OK)
        self.app.go_to_queue_tab()
